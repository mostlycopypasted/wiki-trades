#!/usr/bin/env python3
"""Signal Judge Phase 2 — the live judge.

Design: docs/design/signal-judge.md (revision 11; its "Revision 11 — binding decisions"
section overrides anything above it). Phase 1 (the case store) is scripts/signal_cases.py.

    python3 scripts/signal_judge.py run   [--symbol SYM] [--no-chart] [--dry-run --out DIR] [--force-writer] [--ignore-skip-window]
    python3 scripts/signal_judge.py apply --packet PATH [--verdicts PATH] [--force-writer]
    python3 scripts/signal_judge.py track [--force-writer]
    python3 scripts/signal_judge.py stats [--since YYYY-MM-DD] [--json]

`run` picks fresh TAT alerts (forex 4H; metals, oil and indices 1H), reads their bars and TAT
levels from TradingView in one session, pre-filters them, attaches Binni's precedents and writes a
packet + brief. The slot session then judges the brief inline (reference/judge-protocol.md) and
`apply` validates the verdicts, runs the tracker and appends the day's report section.
Advisory only: nothing here places orders.
"""

import argparse
import contextlib
import datetime as dt
import fcntl
import importlib.util
import io
import json
import math
import os
import re
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import signal_cases as SC  # noqa: E402
from scripts.scan_fake_breakout_setups import bar4h_start  # noqa: E402
from scripts.validate_h4_signals import (  # noqa: E402
    SIGNAL_TIER, TFLOW_PREFIX, cross_pair_consistency, elbow_invalidation, ema_from_bars, find_swings,
    gate_break_of_structure, gate_convincing_close, gate_room_to_target, latest_swing, nearest_level,
    parse_tat_levels, risk_scale_position, tat_bias, triggering_level,
)
from scripts import signal_judge_stats as ST  # noqa: E402

SGT = SC.SGT
NY = SC.NY

RUN_BUDGET_S = 480
SYMBOL_CAP = 24
JUDGE_CAP = 8
MATCH_DELAYED_BY_CROSS = True
STALE_MH = {"1H": 6, "4H": 12}
WINDOW_MH = 12
BAR_S = {"1H": 3600, "4H": 14400}
TF_READS = {"1H": ["60", "240"], "4H": ["240", "D"]}  # signal TF read, higher TF read
WALK_BARS = {"1H": 24, "4H": 120}
RETEST_MAX = {"1H": 12, "4H": 6}
LOCK_WAIT_S = int(os.environ.get("SIGNAL_JUDGE_LOCK_WAIT") or 300)
SESSION_LABEL = {"ahh-access-time": "AHH Access Time", "ahh-session": "AHH Session", "taw-pro": "TAW Pro",
                 "weekly-review": "Weekly Review", "3tt": "3TT", "tar-session": "TAR Session"}
VERDICTS = {"take", "wait_retest", "skip", "no_ruling"}
ICON = {"take": "✅ Take", "wait_retest": "⏳ Wait for retest", "skip": "⛔ Skip", "no_ruling": "❔ No ruling"}
CHECKLIST = ROOT / ".agents" / "skills" / "signal-judge" / "reference" / "doctrine-checklist.md"
TV_SESSION = ROOT / "scripts" / "tv_session.sh"
TV_PASS = ROOT / "scripts" / "tv_judge_pass.mjs"
DAILY_BRIEF_DIR = SC.DAILY_BRIEF_DIR


class Exit(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code, self.msg = code, msg


def log(*a):
    print(*a, file=sys.stderr)


def now_sgt():
    return dt.datetime.now(SGT)


def iso(t):
    return t.astimezone(SGT).isoformat(timespec="seconds") if t else None


def parse_iso(s):
    return dt.datetime.fromisoformat(s) if s else None


# --------------------------------------------------------------------------- dirs, host, locks

def test_dirs():
    d, r = os.environ.get("SIGNAL_JUDGE_DATA_DIR"), os.environ.get("SIGNAL_JUDGE_REPORT_DIR")
    if bool(d) != bool(r):
        raise Exit(6, "set both SIGNAL_JUDGE_DATA_DIR and SIGNAL_JUDGE_REPORT_DIR")
    if d and not os.environ.get("SIGNAL_JUDGE_RUNS_DIR"):
        raise Exit(6, "set SIGNAL_JUDGE_RUNS_DIR with test dirs")
    return bool(d)


def data_dir():
    return Path(os.environ.get("SIGNAL_JUDGE_DATA_DIR") or ROOT / "wiki" / "notes" / "signal-judge")


def report_dir():
    return Path(os.environ.get("SIGNAL_JUDGE_REPORT_DIR") or ROOT / "wiki" / "reports" / "tat_analysis" / "signal_judge")


def runs_dir():
    return SC.runs_dir()


def rel(p):
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def host_name():
    try:
        h = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        h = ""
    return h or socket.gethostname().split(".")[0]


def check_writer(force=False):
    if test_dirs() or force:
        return
    cfg = Path(os.environ.get("SIGNAL_JUDGE_CONFIG") or SC.CONFIG_PATH)
    try:
        writer = json.loads(cfg.read_text()).get("writer_host")
    except Exception:
        writer = None
    h = host_name()
    if not writer or h != writer:
        raise Exit(6, f"not the Signal Judge writer host ({h}); use --dry-run")


@contextlib.contextmanager
def command_lock():
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    fh = open(d / "judge.lock", "a+")
    t0 = time.time()
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() - t0 > LOCK_WAIT_S:
                fh.close()
                raise Exit(4, "another Signal Judge command is running")
            time.sleep(1)
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def log_error(title, body):
    """append_log.py `error` on the real writer host only (never with test dirs)."""
    if os.environ.get("SIGNAL_JUDGE_DATA_DIR") or os.environ.get("SIGNAL_JUDGE_NO_LOG"):
        log(f"(not logged) {title}: {body}")
        return
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "append_log.py"), "--action", "error", "--title", title,
                        "--body", body], cwd=ROOT, stdout=sys.stderr, stderr=sys.stderr, timeout=60)
    except Exception as e:
        log(f"append_log failed: {e}")


class Budget:
    def __init__(self, seconds):
        self.deadline = time.monotonic() + seconds

    def remaining(self):
        return self.deadline - time.monotonic()

    def cap(self, x):
        return max(1, min(x, self.remaining() - 90))


# --------------------------------------------------------------------------- ledger

def key_close(key):
    return parse_iso(key.split("|")[3].replace("#d", ""))


def shard_name(key):
    return "ledger-%s.json" % key_close(key).astimezone(SGT).strftime("%Y-%m")


def months_back(n, ref):
    out, y, m = [], ref.year, ref.month
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def read_shard(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
            raise ValueError("not a ledger shard")
        return d["entries"]
    except Exception as e:
        raise Exit(5, f"ledger shard {path.name} is invalid ({e}); not overwriting it")


def collapse(entries):
    """Two entries sharing a prepass_key (a crash between two shard writes): keep the later run's."""
    best = {}
    for e in entries:
        pk = e.get("prepass_key") or e["key"]
        if pk not in best or (e.get("run_id") or "") >= (best[pk].get("run_id") or ""):
            best[pk] = e
    keep = {id(e) for e in best.values()}
    return [e for e in entries if id(e) in keep]


def load_ledger(months):
    d = data_dir()
    out = []
    for m in months:
        p = d / f"ledger-{m}.json"
        if p.exists():
            out.extend(read_shard(p))
    return collapse(out)


def write_ledger(upserts, deletes=()):
    """Merge by key into the shards (inside the command lock): upserts replace whole entries,
    deletes remove keys. New-key shards are written before old-key removals."""
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    by_shard = {}
    for e in upserts:
        by_shard.setdefault(shard_name(e["key"]), {"up": [], "del": set()})["up"].append(e)
    for k in deletes:
        by_shard.setdefault(shard_name(k), {"up": [], "del": set()})["del"].add(k)
    order = sorted(by_shard, key=lambda n: (0 if by_shard[n]["up"] else 1, n))
    for name in order:
        p = d / name
        cur = read_shard(p) if p.exists() else []
        up = {e["key"]: e for e in by_shard[name]["up"]}
        dels = by_shard[name]["del"] - set(up)
        merged, seen = [], set()
        for e in cur:
            if e["key"] in dels:
                continue
            if e["key"] in up:
                merged.append(up[e["key"]])
                seen.add(e["key"])
            else:
                merged.append(e)
        merged += [e for k, e in up.items() if k not in seen]
        SC.atomic_write(p, json.dumps({"version": 1, "entries": merged}, ensure_ascii=False, indent=0))


# --------------------------------------------------------------------------- yahoo

_YCACHE = {}


def yahoo_bars(ticker, interval="1h", range_=None, period1=None, period2=None, timeout=15):
    """-> (bars, meta). bars = [{"dt" SGT start, open, high, low, close}], 1H bars off the hour dropped."""
    ck = (ticker, interval, range_, period1, period2)
    if ck in _YCACHE:
        return _YCACHE[ck]
    q = {"interval": interval}
    if range_:
        q["range"] = range_
    else:
        q["period1"], q["period2"] = int(period1), int(period2)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?" + urllib.parse.urlencode(q)
    bars, meta = [], None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode())["chart"]["result"][0]
        m = res.get("meta") or {}
        meta = {"price": m.get("regularMarketPrice"), "time": m.get("regularMarketTime")}
        qd = (res.get("indicators") or {}).get("quote", [{}])[0]
        for i, ts in enumerate(res.get("timestamp") or []):
            o, h, l, c = (qd.get(k, [None] * (i + 1))[i] for k in ("open", "high", "low", "close"))
            if None in (o, h, l, c):
                continue
            t = dt.datetime.fromtimestamp(ts, SGT)
            if interval == "1h" and t.minute != 0:
                continue
            bars.append({"dt": t, "open": o, "high": h, "low": l, "close": c})
    except Exception as e:
        log(f"yahoo {ticker} {interval}: {e}")
    out = (bars, meta)
    _YCACHE[ck] = out
    return out


# --------------------------------------------------------------------------- sheet

def fetch_sheet():
    if importlib.util.find_spec("gspread") is None:
        raise Exit(3, f"gspread not importable from {sys.executable}")
    socket.setdefaulttimeout(20)
    rows, status, tfs = SC.fetch_tabs()
    for tab in ("1H", "4H"):
        if status.get(tab) == "ok" and tfs.get(tab):
            log(f"{tab}: Tflow supplement skipped — retrying once in 10 s")
            time.sleep(float(os.environ.get("SIGNAL_JUDGE_TFLOW_RETRY_S", "10")))
            r2, s2, t2 = SC.fetch_tabs()
            if s2.get(tab) == "ok" and not t2.get(tab):
                rows[tab] = r2[tab]
            else:
                status[tab] = "tflow_unavailable"
    return rows, status


# --------------------------------------------------------------------------- bars and features

def to_bars(read):
    out = []
    for b in (read or {}).get("bars") or []:
        try:
            out.append({"dt": dt.datetime.fromtimestamp(int(b["time"]), SGT), "open": float(b["open"]),
                        "high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"])})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda b: b["dt"])
    return out


def bar_closes(bars, T):
    td = dt.timedelta(seconds=T)
    return [min(b["dt"] + td, bars[i + 1]["dt"]) if i + 1 < len(bars) else b["dt"] + td for i, b in enumerate(bars)]


def ticker_of(tv_symbol):
    return str(tv_symbol or "").split(":")[-1].upper()


def validate_read(read, req_tf, tv_symbol, yahoo_meta, check_quote):
    """-> None if the read is usable, else the NO_DATA reason."""
    if not read:
        return "symbol not read"
    st = read.get("state") or {}
    if not str(st.get("symbol", "")).upper().endswith(ticker_of(tv_symbol)):
        return "symbol not confirmed"
    res = str(st.get("resolution", ""))
    if not (res == req_tf or (req_tf == "D" and res == "1D")):
        return "timeframe not confirmed"
    bars = to_bars(read)
    if len(bars) < 21:
        return "bar spacing mismatch"
    gaps = [(bars[i + 1]["dt"] - bars[i]["dt"]).total_seconds() for i in range(len(bars) - 21, len(bars) - 1)]
    med = statistics.median(gaps)
    if req_tf == "D":
        if med < 72000:
            return "bar spacing mismatch"
    elif med != {"60": 3600, "240": 14400}[req_tf]:
        return "bar spacing mismatch"
    if not read.get("tat"):
        return "TAT study not loaded"
    if check_quote and yahoo_meta and yahoo_meta.get("price"):
        last = (read.get("quote") or {}).get("last")
        try:
            if abs(float(last) - float(yahoo_meta["price"])) / float(yahoo_meta["price"]) > 0.03:
                return "quote mismatch"
        except (TypeError, ValueError):
            return "quote mismatch"
    return None


def entry_of(read):
    tat = (read or {}).get("tat")
    return {"tatLabels": {"studies": [tat] if tat else []}, "indicators": (read or {}).get("indicators") or {}}


def labels_stale(read, compare_fp):
    """Python's call on a read whose labels may belong to the previous symbol or timeframe."""
    if not read or not read.get("tat"):
        return False
    if compare_fp is not None and read.get("fingerprint") == compare_fp:
        return True
    lv = parse_tat_levels(entry_of(read), ref=None)
    prices = [x["price"] for x in lv]
    try:
        q = float((read.get("quote") or {}).get("last"))
    except (TypeError, ValueError):
        return False
    if prices and q:
        if abs(statistics.median(prices) - q) / q > 0.10:
            return True
    return False


def htf_bias_of(read):
    for s in ((read or {}).get("indicators") or {}).get("studies", []) or []:
        if str(s.get("name", "")).startswith("TATbyBinniOng"):
            v = s.get("values") or {}
            if "Up Trend" in v and "Down Trend" in v:
                return tat_bias(entry_of(read))
    return None


def daily_brief_entry(sym, run_start, brief_dir=None):
    d = Path(brief_dir or DAILY_BRIEF_DIR)
    files = []
    if d.is_dir():
        for p in d.glob("*.json"):
            try:
                day = dt.date.fromisoformat(p.stem)
            except ValueError:
                continue
            avail = max(dt.datetime.combine(day, dt.time(6, 30), SGT), dt.datetime.fromtimestamp(p.stat().st_mtime, SGT))
            if avail <= run_start and day <= run_start.date():
                files.append((day, p))
    for day, p in sorted(files, reverse=True):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for e in data if isinstance(data, list) else []:
            if SC.canon_instrument(e.get("symbol")) == SC.canon_instrument(sym):
                return {"bias": str(e.get("bias", "")).lower() or None, "age_days": (run_start.date() - day).days}
        return None
    return None


def red_folder(sym, t0, events):
    ccy = set(SC.instrument_currencies(sym))
    end = t0 + dt.timedelta(hours=24)
    return [{"date": e["when"].strftime("%Y-%m-%d"), "time": e["when"].strftime("%H:%M"), "ccy": e["ccy"], "event": e["event"]}
            for e in events if t0 <= e["when"] <= end and e["ccy"] in ccy]


def chart_image(sym, tf, run_start, img_dir=None):
    d = Path(img_dir or ROOT / "wiki" / "images")
    pat = re.compile(r"^(\d{6})-(\d{6})_%s_%s_chart\.png$" % (re.escape(sym.lower()), tf.lower()), re.I)
    best = None
    if d.is_dir():
        for p in d.iterdir():
            m = pat.match(p.name)
            if not m:
                continue
            try:
                t = dt.datetime.strptime(m.group(1) + m.group(2), "%y%m%d%H%M%S").replace(tzinfo=SGT)
            except ValueError:
                continue
            if run_start - dt.timedelta(minutes=45) <= t <= run_start + dt.timedelta(minutes=30) and (best is None or t > best[0]):
                best = (t, p)
    return rel(best[1]) if best else None


def match_signal_bar(a, bars, closes, T):
    """-> (index, matched_by) or (None, None)."""
    lo = a["alert_dt"] - dt.timedelta(seconds=T) - dt.timedelta(hours=6)
    hi = a["alert_dt"] + dt.timedelta(seconds=120)
    cand = [i for i, b in enumerate(bars) if b["dt"] >= lo and closes[i] <= hi]
    if not cand:
        return None, None
    delayed = a.get("delayed") or (a["alert_dt"] - a["nominal_close"]).total_seconds() > 600
    if not delayed:
        for i in reversed(cand):
            if abs((closes[i] - a["nominal_close"]).total_seconds()) <= 60:
                return i, "time"
        return cand[-1], "time_fallback"
    p = a.get("signal_price")
    if MATCH_DELAYED_BY_CROSS and a.get("signal_price_kind") == "level" and p:
        bull = a["direction_tv"] == "Bullish"
        for i in reversed(cand):
            if i == 0:
                continue
            pc, c = bars[i - 1]["close"], bars[i]["close"]
            if (bull and pc <= p < c) or (not bull and pc >= p > c):
                return i, "cross"
    return cand[-1], "time_fallback"


def cross_rule_bar(a, bars, closes, T):
    """Diagnostics only: what the cross rule would pick for an on-time alert."""
    p = a.get("signal_price")
    if a.get("signal_price_kind") != "level" or not p:
        return None
    lo = a["alert_dt"] - dt.timedelta(seconds=T) - dt.timedelta(hours=6)
    hi = a["alert_dt"] + dt.timedelta(seconds=120)
    bull = a["direction_tv"] == "Bullish"
    for i in range(len(bars) - 1, 0, -1):
        if bars[i]["dt"] < lo or closes[i] > hi:
            continue
        pc, c = bars[i - 1]["close"], bars[i]["close"]
        if (bull and pc <= p < c) or (not bull and pc >= p > c):
            return i
    return None


def grid_offset(bars, tf_read, fx):
    if len(bars) < 20:
        return None
    last = bars[-20:]
    if fx and tf_read == "240":
        return 0 if all(bar4h_start(b["dt"]) == b["dt"] for b in last) else None
    mins = [b["dt"].minute for b in last]
    return max(set(mins), key=mins.count)


def market_closed(a, read, read_at, T):
    bars = to_bars(read)
    if not bars or (read_at - bars[-1]["dt"]).total_seconds() > 2 * T:
        return True
    if a["class"] != "fx":
        ny = read_at.astimezone(NY)
        if ny.weekday() < 5 and ny.hour == 17:
            return True
    return False


def weekend_between(t0, t1):
    return SC.market_hours_between(t0, t1) < (t1 - t0).total_seconds() / 3600.0 - 0.01


def is_tracked_class(a):
    return a["class"] in ("fx", "metal", "oil", "index") and a["symbol"] not in SC.UNTRACKED_FX


def laggard(a, context):
    if a["class"] != "fx":
        return False
    c0 = a["bar_close"]
    prior = [x for x in context if x["class"] == "fx" and x["tf"] == "4H" and x["symbol"] != a["symbol"]
             and dt.timedelta(hours=4) <= c0 - x["nominal_close"] <= dt.timedelta(hours=12)]
    if not prior:
        return False
    score, _ = cross_pair_consistency({"clean": a["symbol"], "direction": a["direction_tv"]},
                                      [{"clean": x["symbol"], "direction": x["direction_tv"]} for x in prior])
    return score >= 0.5


def build_features(a, sig_read, htf_read, context, calendar_events, run_start):
    """Levels, SL/TP, features and tags for one alert whose signal bar is a["sig_idx"]."""
    tf = a["tf"]
    T = BAR_S[tf]
    bull = a["direction_tv"] == "Bullish"
    bars = to_bars(sig_read)
    closes = bar_closes(bars, T)
    read_at = dt.datetime.fromtimestamp(sig_read["read_at"] / 1000.0, SGT)
    idx = a["sig_idx"]
    closed = [b for i, b in enumerate(bars) if closes[i] <= read_at or i == idx]
    closed_upto = [b for b in closed]
    sb = bars[idx]
    try:
        price = float((sig_read.get("quote") or {}).get("last"))
    except (TypeError, ValueError):
        price = sb["close"]
    entry_ref = {"time": iso(read_at), "price": price}
    atr = SC.wilder_atr(closed_upto[-60:]) if len(closed_upto) >= 15 else None
    alert = {"symbol": a["tv_symbol"], "clean": a["symbol"], "direction": a["direction_tv"], "signal": a["signal"],
             "base_signal": a["base_signal"], "tflow": bool(a.get("tflow")), "signal_price": a.get("signal_price") or sb["close"],
             "event": a.get("event"), "alert_dt": a["alert_dt"]}
    sig_levels = parse_tat_levels(entry_of(sig_read), ref=price)
    htf_levels = parse_tat_levels(entry_of(htf_read), ref=price) if htf_read else []
    higher = {"1H": {"h4", "d", "w", "m"}, "4H": {"d", "w", "m"}}[tf]
    htf_all = htf_levels + [lv for lv in sig_levels if (lv.get("tf") or "").lower() in higher]
    trig = triggering_level(sig_levels, sb["close"], bull, sb)
    tp = nearest_level(sig_levels, price * (1.0005 if bull else 0.9995), "up" if bull else "down")
    for lv in [x for x in sig_levels if x["kind"] == "TP"]:
        if bull and lv["price"] > price and (tp is None or lv["price"] < tp["price"]):
            tp = lv
        if not bull and lv["price"] < price and (tp is None or lv["price"] > tp["price"]):
            tp = lv
    lookback = 120 if tf == "1H" else 60
    swings = find_swings(bars, idx, lookback=lookback)
    sl = elbow_invalidation(alert, sb, bars, swings)
    age_bars = sum(1 for i in range(idx + 1, len(bars)) if closes[i] <= read_at)

    def lvl(x, with_dist=False):
        if not x:
            return None
        d = {"price": x["price"], "kind": x["kind"], "tf": x.get("tf") or ""}
        if with_dist:
            d["dist_atr"] = round(abs(x["price"] - price) / atr, 2) if atr else None
        return d

    behind = nearest_level(htf_all, price, "down" if bull else "up")
    ahead = nearest_level(htf_all, price, "up" if bull else "down")
    if trig is None:
        cq = {"excursion": None, "close_pos": None, "crossed_on_bar": None}
    else:
        g = gate_convincing_close(alert, sb, trig, contemporaneous=(age_bars <= 1))
        cq = {"excursion": g.get("excursion"), "close_pos": g.get("close_pos"), "crossed_on_bar": g.get("crossed")}
    g = gate_break_of_structure(alert, sb, swings)
    mode = g["mode"] if g.get("pass") else ("counter" if latest_swing(swings, "high" if bull else "low") else "none")
    hs, ls = latest_swing(swings, "high"), latest_swing(swings, "low")
    e20 = ema_from_bars(closed_upto, 20)
    room = gate_room_to_target(alert, trig, tp, price).get("consumed") if (trig and tp) else None
    if a["class"] == "fx":
        sibs = [x for x in context if x["class"] == "fx" and x["tf"] == "4H" and x["nominal_close"] == a["bar_close"]]
        sc, det = cross_pair_consistency({"clean": a["symbol"], "direction": a["direction_tv"]},
                                         [{"clean": x["symbol"], "direction": x["direction_tv"]} for x in sibs])
        cross = {"score": sc, "detail": det}
    else:
        cross = {"score": None, "detail": "not FX"}
    other_tf = None
    otab = "4H" if tf == "1H" else "1H"
    win = dt.timedelta(hours=24 if tf == "1H" else 8)
    cands = [x for x in context if x["symbol"] == a["symbol"] and x["tf"] == otab
             and dt.timedelta(0) <= a["bar_close"] - x["nominal_close"] <= win]
    if cands:
        x = max(cands, key=lambda x: x["nominal_close"])
        other_tf = {"tf": otab, "signal": x["signal"], "direction": x["direction_tv"],
                    "hours_ago": round((a["bar_close"] - x["nominal_close"]).total_seconds() / 3600, 1)}
    hb = htf_bias_of(htf_read)
    db = daily_brief_entry(a["symbol"], run_start)
    rf = red_folder(a["symbol"], read_at, calendar_events)
    lower_upper = None
    if trig and tp:
        lower_upper = (trig["price"], tp["price"]) if bull else (tp["price"], trig["price"])
    tflow = a.get("tflow")
    delay = int((a["alert_dt"] - a["bar_close"]).total_seconds() // 60)
    feats = {
        "close_quality": cq,
        "htf": {"source": "TAT trend 4H" if tf == "1H" else "TAT trend D", "forming": True, "bias": hb, "daily_brief": db},
        "room_consumed": room,
        "structure": {"state": g.get("structure", "Mixed"), "mode": mode,
                      "latest_high": hs["price"] if hs else None, "latest_low": ls["price"] if ls else None},
        "ema20": {"value": e20, "side_ok": (price > e20 if bull else price < e20) if e20 else None,
                  "dist_atr": round(abs(price - e20) / atr, 2) if (e20 and atr) else None},
        "cross_pair": cross,
        "trigger_level": lvl(trig), "tp1_level": lvl(tp),
        "htf_levels": {"behind": lvl(behind, True), "ahead": lvl(ahead, True)},
        "tflow": tflow,
        "other_tf_alert": other_tf,
        "red_folder_24h": rf,
        "risk_scale": risk_scale_position(price, lower_upper[0], lower_upper[1], bull) if lower_upper else None,
        "atr": atr,
        "age_bars": age_bars, "delayed_alert_min": delay if delay > 10 else None,
        "rekeyed_from": None, "matched_by": a.get("matched_by"), "grid_offset_min": a.get("grid_offset_min"),
        "labels_capped": bool((sig_read.get("tat") or {}).get("total_labels", 0) > 500),
        "retried_tf": bool(sig_read.get("retried_tf")), "yahoo_lag_min": a.get("yahoo_lag_min"),
        "wash_lines": None,
    }
    # tags (case vocabulary)
    setup = []
    if tflow:
        setup += ["tflow", "pullback_in_trend"]
    if mode == "trend":
        setup.append("trend_continuation")
    if mode == "reversal":
        setup.append("reversal")
    if cq.get("crossed_on_bar"):
        setup.append("breakout")
    if laggard(a, context):
        setup.append("laggard")
    loc = []
    if tflow and tflow.get("at_zone"):
        loc.append("at_d_zone")
    bd = feats["htf_levels"]["behind"]
    ad = feats["htf_levels"]["ahead"]
    if atr:
        if bd and bd["dist_atr"] is not None and bd["dist_atr"] <= 1.0:
            loc.append("htf_level_behind")
        if ad and ad["dist_atr"] is not None and ad["dist_atr"] <= 1.0:
            loc.append("htf_level_ahead")
        if (ad is None or (ad["dist_atr"] or 0) > 3.0) and "htf_level_ahead" not in loc:
            loc.append("open_space")
        if feats["ema20"]["dist_atr"] is not None and feats["ema20"]["dist_atr"] <= 0.3:
            loc.append("at_ema")
        if not loc:
            loc.append("mid_range")
    elif ad is None:
        loc.append("open_space")
    structure = {"trend": "with_trend", "counter": "counter_trend", "reversal": "transition"}.get(mode, "unspecified")
    want = "bullish" if bull else "bearish"
    if hb:
        htf = "aligned" if hb == want else ("ambiguous" if hb == "neutral" else "opposed")
    elif db and db.get("bias") and db["age_days"] <= 3:
        b = db["bias"]
        htf = "aligned" if b == want else ("opposed" if b in ("bullish", "bearish") else "ambiguous")
    else:
        htf = "unspecified"
    flags = []
    if rf:
        flags.append("news_pending")
    nyt = a["bar_close"].astimezone(NY)
    if nyt.weekday() == 4 and nyt.hour >= 1:
        flags.append("friday")
    if room is not None and room > 0.5:
        flags.append("room_consumed")
    if mode == "counter":
        flags.append("counter_trend")
    if age_bars >= 3:
        flags.append("late_entry")
    tags = {"tf": tf.lower(), "setup": setup, "location": loc, "structure": structure, "htf": htf, "risk_flags": flags}
    extra = ["weekend_gap"] if weekend_between(a["bar_close"], read_at) else []
    return {"features": feats, "tags": tags, "judge_flags": extra, "entry_ref": entry_ref, "sl": sl,
            "tp1": tp["price"] if tp else None, "atr": atr, "signal_close": sb["close"], "read_at": read_at}


def prefilter(sl, tp1, price, bull):
    if sl is None or (bull and sl >= price) or (not bull and sl <= price):
        return "NO_STOP", "no stop on the losing side of entry", None
    risk = abs(price - sl)
    if tp1 is None:
        return "PASS", "OPEN RUN (no level ahead)", None
    rr = abs(tp1 - price) / risk if risk else 0
    if rr < 1.0:
        return "RR_LT_1", f"1:{rr:.2f} from entry {price:g}", round(rr, 2)
    return "PASS", "", round(rr, 2)


def rank_key(a):
    tfl = a.get("tflow") or {}
    rr = a.get("rr")
    return (-(1 if tfl.get("at_zone") else 0), -(1 if a.get("tflow") else 0), -SIGNAL_TIER.get(a["base_signal"], 0),
            a.get("rr_group", 0), -(rr or 0), -a["nominal_close"].timestamp())


# --------------------------------------------------------------------------- run

def new_entry(a, run_id):
    return {
        "key": a["key"], "prepass_key": a["prepass_key"], "run_id": run_id,
        "symbol": a["symbol"], "tv_symbol": a["tv_symbol"], "asset_class": a["class"], "tracked": False,
        "tf": a["tf"], "direction": a["direction_tv"], "signal": a["signal"], "base_signal": a["base_signal"],
        "also_fired": a.get("also_fired", []), "tflow": bool(a.get("tflow")),
        "at_zone": bool((a.get("tflow") or {}).get("at_zone")), "tflow_event": a.get("tflow"),
        "alert_time": iso(a["alert_dt"]), "bar_close": iso(a.get("bar_close") or a["nominal_close"]),
        "signal_close": None, "signal_price": a.get("signal_price"), "signal_price_kind": a.get("signal_price_kind"),
        "event": a.get("event"), "delayed": bool(a.get("delayed")), "parent_key": a.get("parent_key"),
        "entry_ref": None, "sl": None, "tp1": None, "rr": None, "atr": None,
        "price_basis": None, "price_basis_bar": None, "row_times": a.get("row_times", []),
        "pending_since": None, "has_precedents": False,
        "prefilter": None, "prefilter_detail": "", "retryable": False, "attempts": a.get("attempts", 0),
        "tags": {}, "precedent_ids": [], "verdict": None, "retest_level": None, "retest_window_bars": None,
        "judge": None,
        "outcome": {"status": "UNTRACKED", "entry": None, "fill_time": None, "resolved_time": None, "bars": 0,
                    "r": None, "mfe_r": None, "mae_r": None, "reported": False},
    }


def alert_from_entry(e):
    """Rebuild an alert dict from a stored retryable entry (its rows may have left the window)."""
    nc = key_close(e["prepass_key"] or e["key"])
    tfl = e.get("tflow_event")
    return {"key": e["prepass_key"] or e["key"], "prepass_key": e["prepass_key"] or e["key"],
            "parent_key": e.get("parent_key"), "delayed": e.get("delayed", False),
            "symbol": e["symbol"], "tv_symbol": e["tv_symbol"], "class": e["asset_class"], "tf": e["tf"],
            "direction": "long" if e["direction"] == "Bullish" else "short", "direction_tv": e["direction"],
            "signal": e["signal"], "base_signal": e.get("base_signal") or e["signal"].replace(TFLOW_PREFIX, ""),
            "also_fired": e.get("also_fired", []), "event": e.get("event"), "tflow": tfl,
            "nominal_close": nc, "alert_time": parse_iso(e["alert_time"]), "alert_dt": parse_iso(e["alert_time"]),
            "signal_price": e.get("signal_price"), "signal_price_kind": e.get("signal_price_kind"),
            "row_times": e.get("row_times", [])}


def retry_limit(e):
    return 2 if e.get("prefilter_detail") == "no TradingView bar for this alert" else 3


def merge_rows(entry, a):
    """Late rows that turned out to be the same signal: keep their row times and signals.
    Returns True if the entry changed."""
    before = json.dumps([entry.get("row_times"), entry.get("also_fired"), entry.get("signal")])
    seen = {tuple(r) for r in entry.get("row_times", [])}
    entry["row_times"] = entry.get("row_times", []) + [r for r in a.get("row_times", []) if tuple(r) not in seen]
    entry["also_fired"] = sorted((set(entry.get("also_fired", [])) | {a["signal"]} | set(a.get("also_fired", []))) - {entry["signal"]})
    upgradable = entry.get("verdict") == "pending" or entry.get("retryable")
    if upgradable and a.get("tflow") and not entry.get("tflow"):
        entry["also_fired"] = sorted((set(entry["also_fired"]) | {entry["signal"]}) - {a["signal"]})
        entry["signal"], entry["tflow"], entry["tflow_event"] = a["signal"], True, a["tflow"]
        entry["at_zone"] = bool(a["tflow"].get("at_zone"))
    return json.dumps([entry.get("row_times"), entry.get("also_fired"), entry.get("signal")]) != before


def resolve_key(k, recorded, replaced, deletes, by_key):
    """The current entry for key k within one run: this run's recorded entry, else the entry that
    replaced it (following the whole chain, so a replacement that was itself replaced resolves to
    the newest), else the ledger copy unless k is being deleted. None if nothing live remains."""
    hit = next((b for _, b in recorded if b["key"] == k), None)
    if hit is None:
        hit = replaced.get(k)
    if hit is None and k not in deletes:
        hit = by_key.get(k)
    seen = set()
    while hit is not None and id(hit) not in seen:
        seen.add(id(hit))
        nxt = replaced.get(hit["key"])
        if nxt is None or nxt is hit:
            break
        hit = nxt
    return hit


def run_chart_pass(items, budget, run_id, notes):
    """tv_session start -> tv_judge_pass.mjs -> owned stop. -> (out dict | None, skipped_reason)."""
    if budget.remaining() < 300:
        return None, "not enough budget"
    token = f"{run_id}-{os.getpid()}"
    env = dict(os.environ, TV_LOCK_MAX_WAIT_SECS="120", TV_LOCK_FAIL_ON_TIMEOUT="1", TV_LOCK_OWNER=token)
    tmpd = Path(tempfile.gettempdir())
    req, out = tmpd / f"sj_pass_{os.getpid()}_req.json", tmpd / f"sj_pass_{os.getpid()}_out.json"
    procs = {"start": None, "node": None}
    started = False
    reason = None
    result = None

    def kill_groups():
        for p in procs.values():
            if p and p.poll() is None:
                with contextlib.suppress(Exception):
                    os.killpg(p.pid, signal.SIGKILL)

    def do_stop():
        stop_env = dict(os.environ, TV_LOCK_OWNER=token)
        p = subprocess.Popen(["bash", str(TV_SESSION), "stop"], env=stop_env, stdout=sys.stderr, stderr=sys.stderr,
                             start_new_session=True)
        try:
            p.wait(timeout=int(os.environ.get("SIGNAL_JUDGE_STOP_TIMEOUT", "60")))
        except subprocess.TimeoutExpired:
            with contextlib.suppress(Exception):
                os.killpg(p.pid, signal.SIGKILL)
            subprocess.run(["pkill", "-9", "-f", "/Applications/TradingView.app/Contents/MacOS/TradingView"],
                           stdout=sys.stderr, stderr=sys.stderr)
            lock = Path(os.environ.get("TV_LOCK_DIR") or "/tmp/tradingview-desktop-cdp.lock")
            with contextlib.suppress(Exception):
                if f"owner={token}" in (lock / "info").read_text():
                    subprocess.run(["rm", "-rf", str(lock)])
            log_error("Signal Judge — tv_session stop hung", f"run {run_id}: stop timed out; TradingView killed")
            notes.append("tv_session stop hung; TradingView killed")

    def on_signal(signum, frame):
        kill_groups()
        if started:
            do_stop()
        sys.exit(143 if signum == signal.SIGTERM else 130)

    old = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        started = True
        p = subprocess.Popen(["bash", str(TV_SESSION), "start"], env=env, stdout=sys.stderr, stderr=sys.stderr,
                             start_new_session=True)
        procs["start"] = p
        try:
            rc = p.wait(timeout=budget.cap(360))
        except subprocess.TimeoutExpired:
            kill_groups()
            rc = None
        if rc == 75:
            started = False
            return None, "lock busy"
        if rc != 0:
            return None, "start failed"
        req.write_text(json.dumps({"deadline_ms": int((time.time() + budget.cap(300)) * 1000), "items": items}))
        node = subprocess.Popen(["node", str(TV_PASS), str(req), str(out)], stdout=sys.stderr, stderr=sys.stderr,
                                start_new_session=True)
        procs["node"] = node
        deadline = time.time() + budget.cap(300) + 20
        while node.poll() is None:
            if time.time() > deadline or budget.remaining() < 90:
                kill_groups()
                notes.append("chart pass killed at its deadline")
                break
            time.sleep(1)
        try:
            result = json.loads(out.read_text())
        except Exception:
            result = None
            reason = "pass failed"
        if result and result.get("fatal"):
            log(f"chart pass fatal: {result['fatal']}")
            result, reason = None, "pass failed"
    finally:
        if started:
            do_stop()
        for s, h in old.items():
            signal.signal(s, h)
        keep = os.environ.get("SIGNAL_JUDGE_KEEP_PASS")  # debugging: copy the raw pass output here
        if keep and out.exists():
            with contextlib.suppress(Exception):
                Path(keep).write_text(out.read_text())
        for f in (req, out):
            with contextlib.suppress(Exception):
                f.unlink()
    return result, reason


def write_brief(packet, path):
    lines = [f"# Signal Judge brief — run {packet['run_id']} — {len(packet['survivors'])} survivors", ""]
    for s in packet["survivors"]:
        f, t = s["features"], s["tags"]
        rr = f"1:{s['rr']:.2f}" if s.get("rr") else "OPEN RUN"
        lines.append(f"## S{s['n']} — {s['symbol']} {s['tf']} {s['signal']} ({'Bull' if s['direction'] == 'Bullish' else 'Bear'}) — key {s['key']}")
        lines.append(f"- Entry {s['entry_ref']['price']:g} ({s['entry_ref']['time'][11:16]} SGT) · SL {s['sl']:g} · TP1 "
                     f"{s['tp1'] if s['tp1'] is not None else '—'} · R:R {rr} · ATR {s['atr']:.5g} · tracked: {'yes' if s['tracked'] else 'no'}"
                     if s.get("atr") else
                     f"- Entry {s['entry_ref']['price']:g} ({s['entry_ref']['time'][11:16]} SGT) · SL {s['sl']:g} · TP1 "
                     f"{s['tp1'] if s['tp1'] is not None else '—'} · R:R {rr} · tracked: {'yes' if s['tracked'] else 'no'}")
        risks = t["risk_flags"] + s.get("judge_flags", [])
        lines.append(f"- Tags: tf {t['tf']} · setup {', '.join(t['setup']) or '—'} · location {', '.join(t['location']) or '—'} · "
                     f"structure {t['structure']} · htf {t['htf']} · risks {', '.join(risks) or 'none'}")
        cq = f["close_quality"]
        lines.append("- Features:")
        fmt = lambda v: "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))
        lines.append(f"  - close quality: excursion {fmt(cq['excursion'])}, close_pos {fmt(cq['close_pos'])}, crossed on bar {fmt(cq['crossed_on_bar'])}")
        db = f["htf"]["daily_brief"] or {}
        lines.append(f"  - htf ({f['htf']['source']}, forming bar): {fmt(f['htf']['bias'])} · daily brief {fmt(db.get('bias'))} ({fmt(db.get('age_days'))} d old)")
        lines.append(f"  - room consumed {fmt(f['room_consumed'])} · structure {f['structure']['state']} / {f['structure']['mode']} "
                     f"(H {fmt(f['structure']['latest_high'])} L {fmt(f['structure']['latest_low'])}) · EMA20 {fmt(f['ema20']['value'])} side ok {fmt(f['ema20']['side_ok'])} ({fmt(f['ema20']['dist_atr'])} ATR)")
        lines.append(f"  - cross-pair {fmt(f['cross_pair']['score'])} ({f['cross_pair']['detail']}) · trigger {json.dumps(f['trigger_level'])} · TP1 level {json.dumps(f['tp1_level'])}")
        lines.append(f"  - HTF levels: behind {json.dumps(f['htf_levels']['behind'])} · ahead {json.dumps(f['htf_levels']['ahead'])}")
        tf_ = f["tflow"]
        if tf_:
            z = tf_.get("zone")
            lines.append(f"  - Tflow: {'@Zone ' + z['role'] + ' x' + str(z['count']) + ' (' + z['tfs'] + ') ' + str(z['low']) + '–' + str(z['high']) if z else 'no zone'} · D level {tf_.get('d_level')} · {tf_.get('pivot_label')} {tf_.get('pivot')}"[:390])
        lines.append(f"  - other-TF alert {json.dumps(f['other_tf_alert'])} · Red Folder 24 h: "
                     f"{'; '.join(e['date'] + ' ' + e['time'] + ' ' + e['ccy'] + ' ' + e['event'] for e in f['red_folder_24h'])[:200] or 'none'}")
        lines.append(f"  - risk scale {fmt(f['risk_scale'])} · age {f['age_bars']} bars · delay {fmt(f['delayed_alert_min'])} min · labels capped {f['labels_capped']} · matched by {f['matched_by']}")
        lines.append(f"- Chart image: {s['chart_image'] or 'none'}")
        lines.append("### Precedents")
        pr = s["precedents"]
        if not (pr["instrument_recent"] or pr["similar"]):
            lines.append("- None — own analysis required (see the protocol's Own analysis section).")
        for kind, lst in (("recent", pr["instrument_recent"]), ("similar", pr["similar"])):
            for c in lst:
                h = c.get("hindsight") or {}
                hs = h.get("status") or "unscored"
                if h.get("mfe_atr") is not None and h.get("mae_atr") is not None:
                    hs += f" (+{h['mfe_atr']} ATR / −{h['mae_atr']} ATR)"
                tag = "[recent]" if kind == "recent" else f"[similar {c['similarity']:.2f}]"
                qir = {True: "yes", False: "no"}.get(c.get("quote_in_raw"), "unknown")
                q = c.get("quote") or ""
                q = q if len(q) <= 200 else q[:199] + "…"
                lv = (c.get("levels") or "—")[:80]
                lines.append(f"- {tag} {c['id']} · {c['date']} · {c.get('presenter', 'unknown')} · {c['instrument']} {c['tf']} {c['direction']} · "
                             f"{c['verdict']} · cond: {c.get('condition') or '—'} · levels: {lv} · in transcript: {qir} · hindsight {hs} · \"{q}\""[:400])
        lines.append("")
    SC.atomic_write(path, "\n".join(lines) + "\n")


def cmd_run(args):
    run_start = now_sgt()
    if args.now:
        run_start = parse_iso(args.now)
    if not args.ignore_skip_window and SC.market_hours_between(run_start - dt.timedelta(minutes=1), run_start) == 0:
        print("SKIPPED weekend")
        return 10
    if not args.dry_run:
        check_writer(args.force_writer)
    else:
        test_dirs()
    budget = Budget(RUN_BUDGET_S)
    rid = run_start.strftime("%Y-%m-%d_%H%M")
    out_dir = Path(args.out) if args.dry_run else runs_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = contextlib.nullcontext() if args.dry_run else command_lock()
    with lock:  # the run id is chosen under the lock so two runs in one minute can't share it
        run_id, k = rid, 1
        while (out_dir / f"{run_id}_packet.json").exists():
            k += 1
            run_id = f"{rid}_{k}"
        return _run(args, run_start, run_id, out_dir, budget)


def _run(args, run_start, run_id, out_dir, budget):
    notes = []
    months = months_back(2, run_start)
    ledger = load_ledger(months)
    by_key = {e["key"]: e for e in ledger}
    by_pre = {e.get("prepass_key"): e for e in ledger if e.get("prepass_key")}
    aged = []
    if not args.dry_run:
        for e in ledger:
            ps = parse_iso(e.get("pending_since"))
            if e.get("verdict") == "pending" and ps and run_start - ps > dt.timedelta(hours=2):
                e["verdict"] = "unjudged_error"
                e["judge"] = dict(e.get("judge") or {}, error="judge did not run")
                aged.append(e)
        cutoff_old = time.time() - 90 * 86400
        for p in runs_dir().glob("*"):
            if re.search(r"_(packet|verdicts|applied)\.json$|_brief\.md$", p.name) and p.stat().st_mtime < cutoff_old:
                with contextlib.suppress(Exception):
                    p.unlink()

    rows, status = fetch_sheet()
    if all(status.get(t) == "failed" for t in ("1H", "4H")):
        raise Exit(3, "both sheet tabs failed")
    cutoff = SC.market_cutoff(run_start, WINDOW_MH)
    L = SC.load_judged_alerts(rows, cutoff, run_start - dt.timedelta(hours=24))
    alerts, context = L["alerts"], L["context"]
    counts = dict(L["counts"], groups=0, duplicate_delayed=0, already_seen_pre=0, already_seen_post=0, retried=0,
                  stale=0, chart_candidates=0, closed=0, no_data=0, no_stop=0, rr_lt_1=0, pass_=0, judged=0,
                  unjudged_cap=0)
    if args.symbol:
        want = SC.canon_instrument(args.symbol)
        alerts = [a for a in alerts if a["symbol"] == want]

    # retries and already-seen (pre-pass)
    cand, upserts, deletes = [], {}, set()
    present, picked = set(), {}  # picked: ledger entry key -> the sheet alert already retrying it
    for a in alerts:
        e = by_pre.get(a["prepass_key"]) or by_key.get(a["prepass_key"])
        present.add(a["prepass_key"])
        if e is None:
            cand.append(a)
            continue
        if e["key"] in picked:  # a second sheet row for an entry already being retried: fold it in
            p_ = picked[e["key"]]
            seen = {tuple(r) for r in p_["row_times"]}
            p_["row_times"] += [r for r in a.get("row_times", []) if tuple(r) not in seen]
            if a.get("tflow") and not p_.get("tflow"):
                p_["also_fired"] = sorted(set(p_.get("also_fired", [])) | {p_["signal"]})
                for k_ in ("signal", "base_signal", "tflow", "event"):
                    p_[k_] = a.get(k_)
            p_["also_fired"] = sorted((set(p_.get("also_fired", [])) | {a["signal"]} | set(a.get("also_fired", []))) - {p_["signal"]})
            counts["already_seen_pre"] += 1
            continue
        if e.get("retryable") and e.get("attempts", 0) < retry_limit(e):
            a["attempts"] = e.get("attempts", 0)
            a["retry_of"] = e["key"]
            picked[e["key"]] = a
            counts["retried"] += 1
            cand.append(a)
        else:
            counts["already_seen_pre"] += 1
            if merge_rows(e, a):
                upserts[e["key"]] = e
    for e in ledger:
        pk = e.get("prepass_key") or e["key"]
        if e.get("retryable") and pk not in present and e["key"] not in picked and e.get("attempts", 0) < retry_limit(e):
            if args.symbol and e["symbol"] != SC.canon_instrument(args.symbol):
                continue
            a = alert_from_entry(e)
            a["attempts"], a["retry_of"] = e.get("attempts", 0), e["key"]
            counts["retried"] += 1
            cand.append(a)
    counts["groups"] = counts["already_seen_pre"] + len(cand)

    recorded = []  # (alert, entry)
    replaced = {}  # stored key -> the entry recorded in its place this run (its old key is being deleted)

    def absorb_own(target, own):
        """A retry that turned out to be `target`: carry its stored entry's earlier rows, signals and
        Tflow upgrade into target, then delete the stored entry."""
        src = by_key.get(own) if own else None
        if src is not None and src is not target:
            merge_rows(target, {"signal": src["signal"], "also_fired": src.get("also_fired", []),
                                "row_times": src.get("row_times", []),
                                "tflow": src.get("tflow_event") or ({} if src.get("tflow") else None)})
        if own:
            deletes.add(own)
            replaced[own] = target  # a later alert keyed on the old key lands on the absorbing entry
            if upserts.get(own) is src:
                upserts.pop(own, None)

    def lookup(k):
        return resolve_key(k, recorded, replaced, deletes, by_key)

    def record(a, code, detail, retryable, count_attempt=False):
        e = by_key.get(a.get("retry_of")) if a.get("retry_of") else None
        base = new_entry(a, run_id)
        if e:
            base["attempts"] = e.get("attempts", 0)
            # keep what earlier merges added to the stored entry (late rows, a Tflow twin)
            seen = {tuple(r) for r in base["row_times"]}
            base["row_times"] += [r for r in e.get("row_times", []) if tuple(r) not in seen]
            if e.get("tflow") and not base["tflow"]:
                base["signal"], base["tflow"], base["tflow_event"], base["at_zone"] = (
                    e["signal"], True, e.get("tflow_event"), bool(e.get("at_zone")))
            base["also_fired"] = sorted((set(base["also_fired"]) | set(e.get("also_fired", [])) | {e["signal"], a["signal"]})
                                        - {base["signal"]})
        if count_attempt:
            base["attempts"] += 1
        base["prefilter"], base["prefilter_detail"], base["retryable"] = code, detail, retryable
        if retryable and base["attempts"] >= retry_limit({"prefilter_detail": detail}):
            base["retryable"] = False
        if e and e["key"] != base["key"]:
            deletes.add(e["key"])
            replaced[e["key"]] = base
            if upserts.get(e["key"]) is e:  # a stale merge into the old copy must not cancel its delete
                del upserts[e["key"]]
        recorded.append((a, base))
        return base

    # STALE and Tflow-held
    live = []
    for a in cand:
        mh = SC.market_hours_between(a["nominal_close"], run_start)
        if mh > STALE_MH[a["tf"]]:
            counts["stale"] += 1
            record(a, "STALE", f"{mh:.1f} market hours old", False)
            continue
        live.append(a)
    counts["chart_candidates"] = len(live)
    held = [a for a in live if status.get(a["tf"]) == "tflow_unavailable"]
    for a in held:
        record(a, "NO_DATA", "Tflow data unavailable", True)
    live = [a for a in live if status.get(a["tf"]) != "tflow_unavailable"]
    for a in live:
        a["rr_group"], a["rr"] = 0, 0
    live.sort(key=rank_key)
    syms = []
    for a in live:
        if a["tv_symbol"] not in syms:
            syms.append(a["tv_symbol"])
    in_pass = syms[:SYMBOL_CAP]
    capped_syms = set(syms[SYMBOL_CAP:])
    for a in [x for x in live if x["tv_symbol"] in capped_syms]:
        record(a, "NO_DATA", "chart pass cap", True)
    live = [a for a in live if a["tv_symbol"] not in capped_syms]

    # chart pass
    chart, skip_reason = None, None
    if not live:
        skip_reason = "no candidates"
    elif args.no_chart:
        skip_reason = "no-chart"
    elif args.pass_file:
        chart = json.loads(Path(args.pass_file).read_text())
    else:
        items = []
        for sym in in_pass:
            tfs = []
            for a in live:
                if a["tv_symbol"] == sym:
                    for t in TF_READS[a["tf"]]:
                        if t not in tfs:
                            tfs.append(t)
            order = ["60", "240", "D"]
            items.append({"symbol": sym, "timeframes": sorted(tfs, key=order.index)})
        chart, skip_reason = run_chart_pass(items, budget, run_id, notes)
    chart_pass = {"ok": chart is not None, "symbols": len(in_pass) if live else 0, "read_ok": 0, "failed": [],
                  "budget_exceeded": False, "skipped_reason": None if chart is not None else skip_reason}

    # yahoo
    ymeta, ybars = {}, {}
    if chart is not None:
        for sym in in_pass:
            a0 = next(a for a in live if a["tv_symbol"] == sym)
            if not is_tracked_class(a0):
                continue
            if budget.remaining() < 100:
                chart_pass["budget_exceeded"] = True
                ymeta[sym] = "budget"
                continue
            tk = SC.yahoo_ticker(a0["symbol"])
            if not tk:
                continue
            b, m = yahoo_bars(tk, "1h", range_="5d", timeout=min(15, max(1, budget.remaining() - 90)))
            ymeta[sym], ybars[sym] = m, b

    # per alert
    calendar = SC.load_calendar()[1]
    cases = SC.load_cases()
    if not cases:
        notes.append("case store empty or missing: no precedents")
    survivors, filtered, capped, diagnostics = [], [], [], []
    passed = []
    prev_fp_by_sym, sym_order = {}, []
    if chart is not None:
        items = chart.get("items") or {}
        last = None
        for sym in in_pass:
            prev_fp_by_sym[sym] = last
            reads = items.get(sym) or {}
            for t in ("60", "240", "D"):
                if t in reads:
                    last = reads[t].get("fingerprint")
    read_ok_syms = set()
    for a in sorted(live, key=lambda x: bool(x.get("delayed"))):  # parents before their '#d' groups
        sym = a["tv_symbol"]
        if chart is None:
            record(a, "NO_DATA", f"chart pass skipped ({skip_reason})" if skip_reason != "pass failed" else "chart pass failed", True)
            continue
        reads = (chart.get("items") or {}).get(sym)
        if reads is None:
            record(a, "NO_DATA", "run budget exceeded" if chart_pass["budget_exceeded"] or sym in in_pass else "symbol not read", True)
            continue
        sig_tf, htf_tf = TF_READS[a["tf"]]
        sig_read, htf_read = reads.get(sig_tf), reads.get(htf_tf)
        ym = ymeta.get(sym)
        if ym == "budget":
            if a["class"] != "fx":
                record(a, "NO_DATA", "run budget exceeded", True, count_attempt=True)
                continue
            ym = None
        fx = a["class"] == "fx"
        why = validate_read(sig_read, sig_tf, sym, ym, check_quote=bool(ym))
        if not why:
            ordered = [t for t in ("60", "240", "D") if t in reads]
            cmp = prev_fp_by_sym.get(sym) if ordered and ordered[0] == sig_tf else (reads[ordered[0]].get("fingerprint") if ordered else None)
            if labels_stale(sig_read, cmp):
                why = "labels not refreshed"
        if why:
            record(a, "NO_DATA", why, True, count_attempt=True)
            chart_pass["failed"].append({"symbol": sym, "tf": sig_tf, "reason": why})
            continue
        if htf_read is not None and (validate_read(htf_read, htf_tf, sym, None, False) or labels_stale(htf_read, sig_read.get("fingerprint"))):  # incl. TAT not loaded -> bias null
            htf_read = None
        read_ok_syms.add(sym)
        T = BAR_S[a["tf"]]
        bars = to_bars(sig_read)
        closes = bar_closes(bars, T)
        read_at = dt.datetime.fromtimestamp(sig_read["read_at"] / 1000.0, SGT)
        idx, how = match_signal_bar(a, bars, closes, T)
        if idx is None:
            record(a, "NO_DATA", "no TradingView bar for this alert", True, count_attempt=True)
            continue
        a["sig_idx"], a["matched_by"], a["bar_close"] = idx, how, closes[idx]
        a["grid_offset_min"] = grid_offset(bars, sig_tf, fx)
        if args.dry_run and not a.get("delayed") and how == "time":
            ci = cross_rule_bar(a, bars, closes, T)
            diagnostics.append({"key": a["key"], "time_bar_close": iso(closes[idx]),
                                "cross_bar_close": iso(closes[ci]) if ci is not None else None, "agree": ci == idx})
        # re-key
        newkey = "%s|%s|%s|%s" % (a["symbol"], a["tf"], "Bull" if a["direction_tv"] == "Bullish" else "Bear", iso(closes[idx]))
        rekeyed_from = None
        if newkey != a["key"]:
            rekeyed_from = a["key"]
            # The alert's own stored entry (a retry of an entry already re-keyed to newkey) is not a collision.
            own = a.get("retry_of")
            if a.get("parent_key") and newkey == a["parent_key"] and newkey != own:
                parent = lookup(newkey)
                if parent:  # parents are processed first (delayed alerts sort last), so a parent found here is real
                    counts["duplicate_delayed"] += 1
                    merge_rows(parent, a)
                    absorb_own(parent, own)
                    upserts[parent["key"]] = parent
                    continue
            existing = lookup(newkey)
            if existing and existing["key"] != own:
                counts["already_seen_post"] += 1
                merge_rows(existing, a)
                absorb_own(existing, own)
                upserts[existing["key"]] = existing
                continue
            a["key"] = newkey
        if market_closed(a, sig_read, read_at, T):
            e = record(a, "CLOSED", "market closed at read time", True)
            continue
        if ym and ym.get("time"):
            a["yahoo_lag_min"] = int((read_at.timestamp() - ym["time"]) / 60)
        fb = build_features(a, sig_read, htf_read, context, calendar, run_start)
        fb["features"]["rekeyed_from"] = rekeyed_from
        price = fb["entry_ref"]["price"]
        bull = a["direction_tv"] == "Bullish"
        # price basis (metal, oil, index)
        pbasis, pbar = (0.0, None) if fx else (None, None)
        if is_tracked_class(a) and not fx:
            yb = {b["dt"]: b for b in ybars.get(sym, []) if b["dt"] + dt.timedelta(hours=1) <= read_at}
            tvb = to_bars(reads.get("60")) if "60" in reads else []
            off = SC.GRID_OFFSET_MIN.get(a["symbol"], 0)
            for b in reversed([x for x in tvb if x["dt"] + dt.timedelta(hours=1) <= read_at][-6:]):
                ys = (b["dt"] - dt.timedelta(minutes=off)).replace(minute=0, second=0, microsecond=0)
                if ys in yb:
                    pbasis, pbar = yb[ys]["close"] - b["close"], iso(b["dt"])
                    break
            if pbasis is None:
                record(a, "NO_DATA", "no Yahoo price", True, count_attempt=True)
                continue
        code, detail, rr = prefilter(fb["sl"], fb["tp1"], price, bull)
        e = record(a, code, detail, False, count_attempt=True)
        e.update({"entry_ref": fb["entry_ref"], "sl": fb["sl"], "tp1": fb["tp1"], "rr": rr, "atr": fb["atr"],
                  "signal_close": fb["signal_close"], "price_basis": pbasis, "price_basis_bar": pbar,
                  "tags": fb["tags"], "bar_close": iso(a["bar_close"])})
        e["tracked"] = is_tracked_class(a) and code in ("PASS", "RR_LT_1")
        if e["tracked"]:
            e["outcome"]["status"] = "OPEN"
        sig = {"instrument": a["symbol"], "direction": a["direction"], "time": a["bar_close"], "tags": fb["tags"]}
        pr = SC.find_precedents(sig, cases) if cases else {"instrument_recent": [], "similar": []}
        e["precedent_ids"] = [c["id"] for c in pr["instrument_recent"] + pr["similar"]]
        e["has_precedents"] = bool(e["precedent_ids"])
        a["rr"], a["rr_group"] = (rr or 0), (0 if rr is not None else 1)
        if code == "PASS":
            passed.append((a, e, fb, pr))
    chart_pass["read_ok"] = len(read_ok_syms)

    passed.sort(key=lambda x: rank_key(x[0]))
    for n, (a, e, fb, pr) in enumerate(passed, 1):
        if n <= JUDGE_CAP:
            e["verdict"], e["pending_since"] = "pending", iso(run_start if args.now else now_sgt())
            survivors.append({
                "key": e["key"], "n": n, "symbol": e["symbol"], "tv_symbol": e["tv_symbol"], "asset_class": e["asset_class"],
                "tracked": e["tracked"], "tf": e["tf"], "direction": e["direction"], "signal": e["signal"],
                "also_fired": e["also_fired"], "alert_time": e["alert_time"], "bar_close": e["bar_close"],
                "entry_ref": e["entry_ref"], "sl": e["sl"], "tp1": e["tp1"], "rr": e["rr"], "atr": e["atr"],
                "features": fb["features"], "tags": fb["tags"], "judge_flags": fb["judge_flags"],
                "precedents": pr, "has_precedents": e["has_precedents"],
                "chart_image": chart_image(e["symbol"], e["tf"], run_start)})
        else:
            e["verdict"] = "unjudged_cap"
            capped.append({k: e[k] for k in ("key", "symbol", "tf", "direction", "signal", "entry_ref", "sl", "tp1", "rr")})
    for a, e in recorded:
        if e["prefilter"] != "PASS":
            filtered.append({"key": e["key"], "symbol": e["symbol"], "tf": e["tf"], "direction": e["direction"],
                             "signal": e["signal"], "prefilter": e["prefilter"], "detail": e["prefilter_detail"],
                             "retryable": e["retryable"]})
    for a, e in recorded:
        c = e["prefilter"]
        if c == "CLOSED":
            counts["closed"] += 1
        elif c == "NO_DATA":
            counts["no_data"] += 1
        elif c == "NO_STOP":
            counts["no_stop"] += 1
        elif c == "RR_LT_1":
            counts["rr_lt_1"] += 1
        elif c == "PASS":
            counts["pass_"] += 1
    counts["judged"], counts["unjudged_cap"] = len(survivors), len(capped)
    counts["recorded"] = len(recorded)
    counts["by_tf"] = {t: sum(1 for _, e in recorded if e["tf"] == t) for t in ("1H", "4H")}
    counts["pass"] = counts.pop("pass_")

    for a, e in recorded:
        upserts[e["key"]] = e
    for e in aged:
        upserts.setdefault(e["key"], e)
    if not args.dry_run:
        write_ledger(list(upserts.values()), deletes - set(upserts))
    if chart_pass["skipped_reason"] in ("start failed", "not enough budget", "pass failed") or chart_pass["budget_exceeded"]:
        if not args.dry_run:
            log_error("Signal Judge — chart pass skipped", f"run {run_id}: {chart_pass['skipped_reason'] or 'budget exceeded'}")
    if chart_pass["skipped_reason"] == "lock busy" and not args.dry_run:
        prev = sorted([p for p in runs_dir().glob("*_packet.json")], key=lambda p: p.stat().st_mtime)
        try:
            if prev and json.loads(prev[-1].read_text())["chart_pass"].get("skipped_reason") == "lock busy":
                log_error("Signal Judge — TradingView lock busy twice", f"run {run_id}")
        except Exception:
            pass
    for tab in ("1H", "4H"):
        if status.get(tab) == "tflow_unavailable" and not args.dry_run:
            log_error("Signal Judge — Tflow sheet unreadable", f"run {run_id}: {tab} alerts held for the next run")

    packet = {
        "run_id": run_id, "created_at": iso(run_start if args.now else now_sgt()), "dry_run": bool(args.dry_run),
        "data_dir": rel(data_dir()), "report_dir": rel(report_dir()), "runs_dir": rel(runs_dir()),
        "doctrine_checklist": rel(CHECKLIST),
        "brief_path": rel(out_dir / f"{run_id}_brief.md"), "verdicts_path": rel(out_dir / f"{run_id}_verdicts.json"),
        "counts": counts, "chart_pass": chart_pass, "sheet": {t: status.get(t) for t in ("1H", "4H")},
        "grid_mismatch": [{"symbol": a["symbol"], "tf": a["tf"], "expected": SC.GRID_OFFSET_MIN.get(a["symbol"], 0),
                           "observed": a.get("grid_offset_min")}
                          for a, e in recorded if a.get("grid_offset_min") is not None
                          and a["grid_offset_min"] != (0 if a["class"] == "fx" else SC.GRID_OFFSET_MIN.get(a["symbol"], 0))],
        "aged_unjudged": [e["key"] for e in aged], "notes": notes,
        "survivors": survivors, "capped": capped, "filtered": filtered,
    }
    if args.dry_run:
        n = len(diagnostics)
        found = [d for d in diagnostics if d["cross_bar_close"]]
        packet["diagnostics"] = {"cross_rule": diagnostics,
                                 "cross_agree_pct": round(100.0 * sum(d["agree"] for d in diagnostics) / n, 1) if n else None,
                                 "cross_found_pct": round(100.0 * len(found) / n, 1) if n else None,
                                 "cross_agree_when_found_pct": round(100.0 * sum(d["agree"] for d in found) / len(found), 1) if found else None}
    pk = out_dir / f"{run_id}_packet.json"
    write_brief(packet, out_dir / f"{run_id}_brief.md")
    SC.atomic_write(pk, json.dumps(packet, indent=1, ensure_ascii=False, default=str))
    print(f"PACKET {rel(pk)} SURVIVORS {len(survivors)}")
    return 0


# --------------------------------------------------------------------------- apply

def checklist_ids():
    try:
        return set(re.findall(r"\*\*(R\d{2,3})\*\*", CHECKLIST.read_text(encoding="utf-8")))
    except Exception:
        return set()


def validate_verdict(v, s, ids, cklist):
    """-> (verdict dict possibly adjusted, error or None, warning or None)."""
    if v.get("verdict") not in VERDICTS:
        return v, f"verdict {v.get('verdict')!r} not allowed", None
    if v.get("basis") not in ("precedent", "own_analysis"):
        return v, f"basis {v.get('basis')!r} not allowed", None
    if v.get("confidence") not in ("low", "medium", "high"):
        return v, f"confidence {v.get('confidence')!r} not allowed", None
    cc = v.get("controlling_cases") or []
    if not isinstance(cc, list) or len(cc) > 3 or any(c not in ids for c in cc):
        return v, "controlling_cases must be 0-3 ids from this survivor's precedents", None
    for d in v.get("distinguished") or []:
        if not isinstance(d, dict) or d.get("case_id") not in ids:
            return v, "distinguished case_id not in this survivor's precedents", None
    doc = v.get("doctrine") or []
    if not isinstance(doc, list) or any(not re.fullmatch(r"R\d{2,3}", str(r)) or r not in cklist for r in doc):
        return v, "doctrine ids must be R-ids from the checklist", None
    if v["basis"] == "precedent" and not cc:
        return v, "basis precedent needs a controlling case", None
    if v["basis"] == "own_analysis" and (cc or len(doc) < 2):
        return v, "own_analysis needs no controlling case and at least two R-ids", None
    if v["verdict"] == "no_ruling" and not (v.get("question_for_binni") or "").strip():
        return v, "no_ruling needs question_for_binni", None
    r = v.get("reason")
    if not isinstance(r, str) or not (1 <= len(r) <= 400) or "|" in r or "\n" in r:
        return v, "reason must be 1-400 chars with no | or newline", None
    flat = lambda x: re.sub(r"\s+", " ", str(x)).replace("|", "/").strip()
    v = dict(v, dissent=flat(v["dissent"]) if v.get("dissent") else None,
             question_for_binni=flat(v["question_for_binni"]) if v.get("question_for_binni") else None,
             distinguished=[dict(d, why=flat(d.get("why", ""))) for d in v.get("distinguished") or []])
    warn = None
    if v["verdict"] == "wait_retest":
        lvl, win = v.get("retest_level"), v.get("retest_window_bars")
        if not isinstance(win, int) or isinstance(win, bool) or not (1 <= win <= RETEST_MAX[s["tf"]]):
            return v, f"retest_window_bars must be 1-{RETEST_MAX[s['tf']]}", None
        try:
            lvl = float(lvl)
        except (TypeError, ValueError):
            return v, "retest_level must be a number", None
        sl, ent = s["sl"], s["entry_ref"]["price"]
        lo, hi = min(sl, ent), max(sl, ent)
        if not (lo < lvl < hi):
            atr = s.get("atr")
            bull = s["direction"] == "Bullish"
            beyond = (sl - lvl) if bull else (lvl - sl)  # >= 0 when on or past the stop
            snapped = (sl + 0.1 * atr) if (atr and bull) else ((sl - 0.1 * atr) if atr else None)
            if atr and 0 <= beyond < 0.1 * atr and lo < snapped < hi:
                v = dict(v, retest_level=snapped)
                warn = f"retest level {lvl:g} moved to {snapped:g} (within 0.1 ATR of the stop)"
            else:
                return v, "retest_level must lie between SL and entry", None
    elif v.get("retest_level") is not None or v.get("retest_window_bars") is not None:
        return v, "retest fields only for wait_retest", None
    return v, None, warn


def tracker(entries, budget_s, now=None):
    """Walk OPEN tracked entries on Yahoo 1H bars. -> keys resolved."""
    now = now or now_sgt()
    t0 = time.monotonic()
    open_e = [e for e in entries if e.get("tracked") and (e.get("outcome") or {}).get("status") == "OPEN"
              and e.get("verdict") not in ("pending",)]
    by_tk = {}
    for e in open_e:
        tk = SC.yahoo_ticker(e["symbol"])
        if tk:
            by_tk.setdefault(tk, []).append(e)
    resolved = []
    for tk, es in by_tk.items():
        if time.monotonic() - t0 > budget_s:
            break
        oldest = min(parse_iso(e["entry_ref"]["time"]) for e in es)
        bars, _ = yahoo_bars(tk, "1h", period1=(oldest - dt.timedelta(hours=1)).timestamp(), period2=now.timestamp())
        bars = [b for b in bars if b["dt"] + dt.timedelta(hours=1) <= now]
        for e in es:
            if walk(e, bars, now):
                resolved.append(e["key"])
    return resolved


def walk(e, bars, now):
    out = e["outcome"]
    t_ent = parse_iso(e["entry_ref"]["time"])
    first = (t_ent + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    bs = [b for b in bars if b["dt"] >= first]
    basis = e.get("price_basis") or 0.0
    adj = lambda b: {k: b[k] - basis for k in ("open", "high", "low", "close")}
    bull = e["direction"] == "Bullish"
    sl, tp = e["sl"], e["tp1"]
    entry = e["entry_ref"]["price"]
    if e.get("verdict") == "wait_retest":
        lvl, win = e["retest_level"], e["retest_window_bars"] * (1 if e["tf"] == "1H" else 4)
        fill_i = None
        for i, b in enumerate(bs[:win]):
            a = adj(b)
            if a["low"] <= lvl <= a["high"]:
                fill_i = i
                break
        if fill_i is None:
            if len(bs) >= win:
                risk = abs(lvl - sl)
                fav = [adj(b) for b in bs[:win]]
                mfe = max(((x["high"] - entry) if bull else (entry - x["low"])) for x in fav) if fav else 0
                out.update(status="NO_FILL", r=0.0, mfe_r=round(mfe / risk, 2) if risk else None, bars=win,
                           resolved_time=iso(bs[win - 1]["dt"] + dt.timedelta(hours=1)))
                return True
            return _expire_check(e, now)
        entry = lvl
        out["entry"], out["fill_time"] = lvl, iso(bs[fill_i]["dt"])
        bs = bs[fill_i:]
    risk = abs(entry - sl)
    if risk <= 0:
        return False
    n = WALK_BARS[e["tf"]]
    mfe = mae = 0.0
    for i, b in enumerate(bs[:n]):
        a = adj(b)
        fav = (a["high"] - entry) if bull else (entry - a["low"])
        adv = (entry - a["low"]) if bull else (a["high"] - entry)
        mfe, mae = max(mfe, fav), max(mae, adv)
        hit_sl = a["low"] <= sl if bull else a["high"] >= sl
        hit_tp = tp is not None and (a["high"] >= tp if bull else a["low"] <= tp)
        if hit_sl or hit_tp:
            out.update(status="SL_HIT" if hit_sl else "TP1_HIT", r=-1.0 if hit_sl else round(abs(tp - entry) / risk, 2),
                       bars=i + 1, resolved_time=iso(b["dt"] + dt.timedelta(hours=1)),
                       mfe_r=round(mfe / risk, 2), mae_r=round(mae / risk, 2))
            return True
    if len(bs) >= n:
        last = adj(bs[n - 1])["close"]
        r = ((last - entry) if bull else (entry - last)) / risk
        out.update(status="OPEN_RUN_EXPIRED" if tp is None else "EXPIRED", r=round(r, 2), bars=n,
                   resolved_time=iso(bs[n - 1]["dt"] + dt.timedelta(hours=1)), mfe_r=round(mfe / risk, 2),
                   mae_r=round(mae / risk, 2))
        return True
    out["bars"] = len(bs[:n])
    return _expire_check(e, now)


def _expire_check(e, now):
    if now - parse_iso(e["entry_ref"]["time"]) > dt.timedelta(days=10):
        e["outcome"]["status"] = "NO_DATA"
        return True
    return False


def note_link(case, report_path):
    note = ROOT / case["note"]
    try:
        relp = os.path.relpath(note, report_path.parent)
    except ValueError:
        relp = case["note"]
    label = f"{SESSION_LABEL.get(case.get('session_type'), case.get('session_type', 'Session'))} {case['date']} · {case['instrument']}"
    return f"[{label}](<{relp}>)"


def dir_tag(direction):
    return "(🟢 Bull)" if direction == "Bullish" else "(🔴 Bear)"


def fmtp(x):
    return "—" if x is None else f"{x:g}"


def section_text(packet, entries_by_key, resolved, sc, warnings, report_path, cases_by_id, aged_lines):
    created = parse_iso(packet["created_at"])
    hhmm = created.strftime("%H:%M")
    suffix = packet["run_id"].split("_")[2] if packet["run_id"].count("_") == 2 else None
    head = f"[{hhmm} SGT]" + (f" ({suffix})" if suffix else "")
    c = packet["counts"]
    v = {k: 0 for k in VERDICTS}
    bp = {"precedent": 0, "own_analysis": 0}
    unj = 0
    for s in packet["survivors"]:
        e = entries_by_key.get(s["key"]) or {}
        if e.get("verdict") in VERDICTS:
            v[e["verdict"]] += 1
            bp[(e.get("judge") or {}).get("basis", "own_analysis")] += 1
        else:
            unj += 1
    unj += len(packet["capped"])
    L = [f"<!-- signal-judge-run:{packet['run_id']} -->", f"## 🕒 Signal Judge Run — {head}", ""]
    L.append(f"**Run summary:** run `{packet['run_id']}` · {c['rows_in_window']} alerts in window · {c['recorded']} recorded "
             f"(1H {c['by_tf']['1H']} · 4H {c['by_tf']['4H']}) · {c['pass']} passed the pre-filter · "
             f"{v['take'] + v['wait_retest'] + v['skip'] + v['no_ruling']} judged (precedent {bp['precedent']} · own {bp['own_analysis']}) · "
             f"verdicts: take {v['take']} · wait {v['wait_retest']} · skip {v['skip']} · no ruling {v['no_ruling']} · unjudged {unj} · "
             f"{c['out_of_scope'] + c['out_of_tf']} out of scope/TF · chart pass {packet['chart_pass']['read_ok']}/{packet['chart_pass']['symbols']}")
    cp = packet["chart_pass"]
    for t, st in packet["sheet"].items():
        if st == "failed":
            L.append(f"\n⚠️ {t} sheet tab could not be read this run.")
        if st == "tflow_unavailable":
            L.append(f"\n⚠️ Tflow sheet unreadable: {t} alerts held for the next run.")
    if cp.get("skipped_reason") and cp["skipped_reason"] not in ("no candidates",):
        L.append(f"\n⚠️ Chart pass skipped ({cp['skipped_reason']}); those alerts will retry.")
    for g in packet.get("grid_mismatch") or []:
        L.append(f"\n⚠️ Bar grid mismatch: {g['symbol']} {g['tf']} expected :{g['expected']:02d}, observed {g['observed']}.")
    for w in warnings + aged_lines:
        L.append(f"\n⚠️ {w}")
    L.append("")
    L.append(f"### Verdicts — {head}")
    rows = []
    for s in packet["survivors"]:
        e = entries_by_key.get(s["key"]) or {}
        j = e.get("judge") or {}
        verdict = e.get("verdict")
        tflow = s["signal"] + (" @Zone" if (s["features"].get("tflow") or {}).get("at_zone") else "")
        if verdict in VERDICTS:
            vc = ICON[verdict] + (f" @ {fmtp(e.get('retest_level'))}" if verdict == "wait_retest" else "") + f" ({j.get('confidence')})"
            ctrl = [cases_by_id[cid] for cid in [x["id"] for x in j.get("controlling") or []] if cid in cases_by_id]
            basis = "Own analysis" if j.get("basis") == "own_analysis" else (
                "Pauline" if ctrl and all(cc.get("presenter") == "pauline" for cc in ctrl) else "Binni")
            link = "; ".join(note_link(cc, report_path) for cc in ctrl) or "—"
        else:
            vc, basis, link = f"⚠️ Unjudged ({j.get('error') or 'error'})", "", "—"
        rr = f"1:{s['rr']:.2f}" if s.get("rr") else "OPEN RUN"
        rr += "" if s["tracked"] else " (untracked)"
        rows.append(f"| [[{s['symbol']}]] {dir_tag(s['direction'])} | {s['tf']} | {tflow} | {vc} | {basis} | "
                    f"{fmtp(s['entry_ref']['price'])} / {fmtp(s['sl'])} / {fmtp(s['tp1'])} | {rr} | {link} |")
    for s in packet["capped"]:
        rr = f"1:{s['rr']:.2f}" if s.get("rr") else "OPEN RUN"
        rows.append(f"| [[{s['symbol']}]] {dir_tag(s['direction'])} | {s['tf']} | {s['signal']} | ⚠️ Unjudged (cap) |  | "
                    f"{fmtp(s['entry_ref']['price'])} / {fmtp(s['sl'])} / {fmtp(s['tp1'])} | {rr} | — |")
    if rows:
        L += ["| Instrument | TF | Signal | Verdict | Basis | Entry / SL / TP1 | R:R | Controlling precedent |",
              "|---|---|---|---|---|---|---|---|"] + rows
    else:
        L.append("No signals passed the pre-filter this run.")
    judged = [s for s in packet["survivors"] if (entries_by_key.get(s["key"]) or {}).get("verdict") in VERDICTS]
    errs = [s for s in packet["survivors"] if (entries_by_key.get(s["key"]) or {}).get("verdict") == "unjudged_error"]
    if judged or errs:
        L += ["", f"### Opinions — {head}"]
        for s in judged:
            e = entries_by_key[s["key"]]
            j = e["judge"]
            L.append(f"#### {s['symbol']} {s['tf']} {s['signal']} — {ICON[e['verdict']].split(' ', 1)[1]}")
            fol = "; ".join(f"{c['id']} · {c.get('presenter', 'unknown')} · \"{c['quote'][:120]}\" · {c.get('hindsight') or 'unscored'}"
                            for c in j.get("controlling") or []) or "—"
            dis = "; ".join(f"{d['case_id']}: {d['why']}" for d in j.get("distinguished") or []) or "—"
            L.append(f"- **Reason**: {j['reason']} **Followed**: {fol} **Distinguished**: {dis} "
                     f"**Doctrine**: {', '.join(j.get('doctrine') or []) or '—'} **Dissent**: {j.get('dissent') or '—'}")
            if s.get("chart_image"):
                img = os.path.relpath(ROOT / s["chart_image"], report_path.parent)
                L.append(f"- ![{s['symbol']} {s['tf']} Chart Screenshot]({img})")
        for s in errs:
            L.append(f"- {s['symbol']} {s['tf']} {s['signal']}: unjudged — {(entries_by_key[s['key']].get('judge') or {}).get('error')}")
    f = packet["filtered"]
    L += ["", f"### Pre-filter — {head}", f"<details><summary>{len(f)} alerts filtered</summary>", ""]
    if f:
        L += ["| Instrument | TF | Signal | Code | Detail |", "|---|---|---|---|---|"]
        for x in f:
            L.append(f"| [[{x['symbol']}]] {dir_tag(x['direction'])} | {x['tf']} | {x['signal']} | {x['prefilter']} | "
                     f"{(x['detail'] or '').replace('|', '/')}{' (will retry)' if x['retryable'] else ''} |")
    L += ["</details>", "", f"### Resolved Since Last Run — {head}"]
    if resolved:
        L += ["| Instrument | TF | Verdict | Basis | Outcome | R | MFE R |", "|---|---|---|---|---|---|---|"]
        for e in resolved:
            o = e["outcome"]
            b = "Own" if (e.get("judge") or {}).get("basis") == "own_analysis" else ("Binni" if e.get("judge") else "")
            L.append(f"| [[{e['symbol']}]] {dir_tag(e['direction'])} | {e['tf']} | {e.get('verdict') or e['prefilter']} | {b} | "
                     f"{o['status']} | {fmtp(o.get('r'))} | {fmtp(o.get('mfe_r'))} |")
    else:
        L.append("None.")
    qs = [s for s in judged if entries_by_key[s["key"]]["verdict"] == "no_ruling"]
    if qs:
        L += ["", f"### Questions for Binni — {head}"]
        for s in qs:
            L.append(f"- [[{s['symbol']}]] {dir_tag(s['direction'])} {s['tf']} {s['signal']} — {entries_by_key[s['key']]['judge']['question_for_binni']}")
    L += ["", f"### 30-Day Scorecard — {head}", "| Group | Resolved | TP1 % | Avg R | Avg MFE R | No fill |", "|---|---|---|---|---|---|"]
    rows_sc = [(g, r) for g, r in sc["rows"].items() if r["n"]]
    for g, r in rows_sc:
        dash = lambda x: "—" if x is None else x
        L.append(f"| {g} | {r['resolved']} | {dash(r['tp1_pct'])} | {dash(r['avg_r'])} | {dash(r['avg_mfe_r'])} | {r['no_fill']} |")
    if not rows_sc:
        L.append("| — | 0 | — | — | — | 0 |")
    return "\n".join(L) + "\n"


def cmd_apply(args):
    pk = Path(args.packet)
    try:
        packet = json.loads(pk.read_text(encoding="utf-8"))
    except Exception as e:
        raise Exit(2, f"packet unreadable: {e}")
    if packet.get("dry_run"):
        raise Exit(2, "dry-run packet; nothing applied")
    if (packet.get("data_dir"), packet.get("report_dir"), packet.get("runs_dir")) != (rel(data_dir()), rel(report_dir()), rel(runs_dir())):
        raise Exit(2, "packet belongs to another data dir")
    check_writer(args.force_writer)
    applied = pk.with_name(pk.name.replace("_packet.json", "_applied.json"))
    if applied.exists():
        print("already applied")
        return 0
    with command_lock():
        return _apply(args, packet, pk, applied)


def _apply(args, packet, pk, applied):
    if applied.exists():  # a second apply that waited on the lock
        print("already applied")
        return 0
    created = parse_iso(packet["created_at"])
    # survivors' shards plus the tracker's window (OPEN entries are <= 10 days old)
    months = sorted(set(months_back(2, now_sgt()) + [key_close(s["key"]).strftime("%Y-%m") for s in packet["survivors"]]))
    ledger = load_ledger(months)
    by_key = {e["key"]: e for e in ledger}
    warnings = []
    vpath = Path(args.verdicts) if args.verdicts else ROOT / packet["verdicts_path"]
    verdicts, vfile_err = None, None
    if packet["survivors"]:
        try:
            vd = json.loads(vpath.read_text(encoding="utf-8"))
            verdicts = vd.get("verdicts") if isinstance(vd, dict) else None
            if not isinstance(verdicts, list):
                raise ValueError("no verdicts list")
        except Exception as e:
            vfile_err = "judge unavailable"
            log(f"verdicts unreadable: {e}")
    cklist = checklist_ids()
    upd = {}
    cases_by_id = {c["id"]: c for c in SC.load_cases()}
    survivor_keys = {s["key"] for s in packet["survivors"]}
    if verdicts is not None:
        for v in verdicts:
            if isinstance(v, dict) and v.get("key") not in survivor_keys:
                warnings.append(f"verdict for unknown key {v.get('key')} ignored")
    for s in packet["survivors"]:
        e = by_key.get(s["key"])
        if e is None:
            warnings.append(f"{s['key']} not in the ledger")
            continue
        if e.get("verdict") != "pending":
            warnings.append(f"{s['symbol']} {s['tf']} was already {e.get('verdict')}; verdict ignored")
            continue
        ids = {c["id"] for c in s["precedents"]["instrument_recent"] + s["precedents"]["similar"]}
        err, warn, v = None, None, None
        if vfile_err:
            err = vfile_err
        else:
            mine = [x for x in verdicts if isinstance(x, dict) and x.get("key") == s["key"]]
            if not mine:
                err = "no verdict returned"
            elif len(mine) > 1:
                err = "duplicate verdicts"
            else:
                v, err, warn = validate_verdict(mine[0], s, ids, cklist)
        if warn:
            warnings.append(f"{s['symbol']} {s['tf']}: {warn}")
        if err:
            e["verdict"] = "unjudged_error"
            e["judge"] = {"error": err}
        else:
            e["verdict"] = v["verdict"]
            e["retest_level"], e["retest_window_bars"] = v.get("retest_level"), v.get("retest_window_bars")
            ctrl = []
            for cid in v.get("controlling_cases") or []:
                c = cases_by_id.get(cid, {})
                h = (c.get("hindsight") or {}).get("status") or "unscored"
                ctrl.append({"id": cid, "presenter": c.get("presenter"), "verdict": c.get("verdict"),
                             "quote": (c.get("quote") or "")[:200], "hindsight": h})
            e["judge"] = {"basis": v["basis"], "confidence": v["confidence"], "controlling": ctrl,
                          "distinguished": v.get("distinguished") or [], "doctrine": v.get("doctrine") or [],
                          "reason": v["reason"], "dissent": v.get("dissent"), "question_for_binni": v.get("question_for_binni"),
                          "error": None}
        upd[e["key"]] = e
    # tracker
    tb = float(os.environ.get("SIGNAL_JUDGE_TRACK_BUDGET", "150"))
    tracked_keys = tracker(ledger, tb)
    resolved = [e for e in ledger if e.get("tracked") and e["outcome"]["status"] not in ("OPEN", "UNTRACKED")
                and not e["outcome"].get("reported")]
    for e in resolved:
        e["outcome"]["reported"] = True
        upd[e["key"]] = e
    for k in tracked_keys:
        upd[k] = by_key[k]
    write_ledger(list(upd.values()))
    aged_lines = []
    if packet.get("aged_unjudged"):
        names = [f"{by_key[k]['symbol']} {by_key[k]['tf']} {by_key[k]['signal']}" for k in packet["aged_unjudged"] if k in by_key]
        aged_lines.append(f"{len(names)} signals from earlier runs were never judged: {', '.join(names)}")
    sc = ST.scorecard(ledger, now_sgt() - dt.timedelta(days=30))
    rdir = report_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    rpath = rdir / f"{created.strftime('%Y-%m-%d')}-signal-judge.md"
    marker = f"<!-- signal-judge-run:{packet['run_id']} -->"
    text = rpath.read_text(encoding="utf-8") if rpath.exists() else ""
    sec = None
    if marker not in text:
        if not text:
            text = (f"---\ntype: report\ndate: \"{created.strftime('%Y-%m-%d')}\"\n---\n\n"
                    f"# ⚖️ Signal Judge — {created.strftime('%Y-%m-%d')} [{created.strftime('%H:%M')} SGT]\n\n")
        sec = section_text(packet, {e["key"]: e for e in ledger}, resolved, sc, warnings, rpath, cases_by_id, aged_lines)
        text = text.rstrip("\n") + "\n\n" + sec
        from scripts.report_toc import upsert_toc
        SC.atomic_write(rpath, upsert_toc(text))
    SC.atomic_write(applied, json.dumps({"applied_at": iso(now_sgt()), "report": rel(rpath)}))
    if not os.environ.get("SIGNAL_JUDGE_DATA_DIR"):
        src = sec if sec is not None else text[text.index(marker):]
        summary = re.search(r"\*\*Run summary:\*\* (.*)", src)
        body = summary.group(1) if summary else packet["run_id"]
        subprocess.run([sys.executable, str(ROOT / "scripts" / "append_log.py"), "--action", "report", "--title",
                        f"Signal Judge Run — {created.strftime('%Y-%m-%d %H:%M')} SGT", "--body", body],
                       cwd=ROOT, stdout=sys.stderr, stderr=sys.stderr, timeout=60)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "update_weekly_index.py")], cwd=ROOT,
                       stdout=sys.stderr, stderr=sys.stderr, timeout=120)
    if vfile_err and not os.environ.get("SIGNAL_JUDGE_DATA_DIR"):
        log_error("Signal Judge — judge unavailable", f"run {packet['run_id']}: no readable verdicts file")
    print(f"REPORT {rel(rpath)}")
    return 0


def cmd_track(args):
    check_writer(args.force_writer)
    with command_lock():
        ledger = load_ledger(months_back(2, now_sgt()))
        keys = tracker(ledger, float(os.environ.get("SIGNAL_JUDGE_TRACK_BUDGET", "300")))
        write_ledger([e for e in ledger if e["key"] in set(keys)])
    print(f"resolved {len(keys)}")
    return 0


def cmd_stats(args):
    since = dt.datetime.combine(dt.date.fromisoformat(args.since), dt.time(), SGT) if args.since else now_sgt() - dt.timedelta(days=30)
    n = max(2, (now_sgt().year - since.year) * 12 + now_sgt().month - since.month + 2)
    ledger = load_ledger(months_back(n, now_sgt()))
    sc = ST.scorecard(ledger, since)
    hit = ST.precedent_hit_rate(ledger, since)
    if args.json:
        print(json.dumps({"scorecard": sc, "precedents": hit}, indent=1))
        return 0
    print(f"Scorecard since {since.date()} ({sc['window_days']} days)")
    print(f"{'group':<24}{'n':>5}{'resolved':>10}{'TP1 %':>8}{'avg R':>8}{'MFE R':>8}{'no fill':>9}")
    for g, r in sc["rows"].items():
        dash = lambda x: "—" if x is None else x
        print(f"{g:<24}{r['n']:>5}{r['resolved']:>10}{dash(r['tp1_pct']):>8}{dash(r['avg_r']):>8}{dash(r['avg_mfe_r']):>8}{r['no_fill']:>9}")
    print(f"Judged with precedents: {hit['with_precedents_pct']}% · followed a precedent: {hit['followed_pct']}% (n={hit['judged']})")
    return 0


# --------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Signal Judge Phase 2 — the live judge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="pick, chart-read and pre-filter fresh alerts; write packet + brief")
    p.add_argument("--symbol")
    p.add_argument("--no-chart", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out")
    p.add_argument("--force-writer", action="store_true")
    p.add_argument("--ignore-skip-window", action="store_true")
    p.add_argument("--now", help=argparse.SUPPRESS)        # tests: frozen run start (ISO)
    p.add_argument("--pass-file", help=argparse.SUPPRESS)  # tests: a canned tv_judge_pass out.json
    p = sub.add_parser("apply", help="validate verdicts, track, append the report section")
    p.add_argument("--packet", required=True)
    p.add_argument("--verdicts")
    p.add_argument("--force-writer", action="store_true")
    p = sub.add_parser("track", help="resolve OPEN tracked entries")
    p.add_argument("--force-writer", action="store_true")
    p = sub.add_parser("stats", help="30-day scorecard (read-only)")
    p.add_argument("--since")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "run" and args.dry_run and not args.out:
        ap.error("--dry-run requires --out DIR")
    try:
        return {"run": cmd_run, "apply": cmd_apply, "track": cmd_track, "stats": cmd_stats}[args.cmd](args)
    except Exit as e:
        log(e.msg)
        if e.code in (3, 4, 5) and not (args.cmd == "run" and getattr(args, "dry_run", False)):
            log_error(f"Signal Judge {args.cmd} — exit {e.code}", e.msg)
        return e.code
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        log(tb)
        if not (args.cmd == "run" and getattr(args, "dry_run", False)):
            log_error(f"Signal Judge {args.cmd} — unexpected error", tb.strip().splitlines()[-1][:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Signal Judge Phase 1 — the Binni case store.

Every concrete instrument call Binni makes in the session notes becomes one structured
"case" in wiki/notes/signal-judge/cases.jsonl. Cases are scored against what price did
afterwards (hindsight), retrieved as precedents for a signal (find_precedents), and
replayed against recent real 1H/4H TAT alerts (coverage) to decide whether the live
judge (Phase 2) is worth building.

Design: docs/design/signal-cases-phase1.md (revision 3).
Extraction protocol: .agents/skills/signal-judge/reference/case-extraction.md

    python3 scripts/signal_cases.py pending
    python3 scripts/signal_cases.py add --note "wiki/AHH Session Notes/<stem>.md" --file <staged.json>
    python3 scripts/signal_cases.py score [--all]
    python3 scripts/signal_cases.py match --signal <signal.json>
    python3 scripts/signal_cases.py coverage [--days 14] [--json]
    python3 scripts/signal_cases.py stats
"""

import argparse
import contextlib
import datetime as dt
import fcntl
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.validate_h4_signals import (  # noqa: E402
    FX_CCY, SIGNAL_TIER, TFLOW_PREFIX, cross_pair_consistency, is_in_scope,
)

SGT = dt.timezone(dt.timedelta(hours=8))
NY = ZoneInfo("America/New_York")

NOTE_DIRS = [ROOT / "wiki" / "AHH Session Notes", ROOT / "wiki" / "sources"]
STEM_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-(ahh-access-time|ahh-session|taw-pro|weekly-review(?:-binni)?|3tt|tar-session)(?:-.*)?$")
DAILY_BRIEF_DIR = Path.home() / "tradingview-mcp" / "daily_brief"
CALENDAR_NOTE = ROOT / "wiki" / "notes" / "economic-calendar.md"
CONFIG_PATH = ROOT / "scripts" / "signal_judge_config.json"


def cases_dir():
    return Path(os.environ.get("SIGNAL_CASES_DIR") or ROOT / "wiki" / "notes" / "signal-judge")


def runs_dir():
    return Path(os.environ.get("SIGNAL_JUDGE_RUNS_DIR") or ROOT / "scripts" / "signal_judge_runs")


def log(*a):
    print(*a, file=sys.stderr)


def now_sgt():
    return dt.datetime.now(SGT)


# --------------------------------------------------------------------------- symbols

# Copied from dashboard/wiki_data.py:109 (not imported: that module pulls in the dashboard).
DASH_ALIASES = {"JP225": "JPN225", "NIKKEI": "JPN225", "NASDAQ": "NDQ100", "NAS100": "NDQ100", "US100": "NDQ100",
                "SPX": "SPX500", "US500": "SPX500", "SP500": "SPX500", "USOIL": "USOUSD", "WTI": "USOUSD",
                "UKOIL": "UKOUSD", "BRENT": "UKOUSD", "GOLD": "XAUUSD", "SILVER": "XAGUSD", "DOW": "US30",
                "DJI": "US30", "DAX": "GER40", "GER30": "GER40", "USDX": "DXY", "SGP": "STI"}
# Applied after DASH_ALIASES, so these win (e.g. the sheet calls the dollar index USDX).
OVERRIDES = {"NDX": "NDQ100", "NAS100": "NDQ100", "US100": "NDQ100", "NASDAQ": "NDQ100",
             "S&P": "SPX500", "SPX": "SPX500", "US500": "SPX500", "SP500": "SPX500",
             "JP225": "JPN225", "NIKKEI": "JPN225", "NIKKEI225": "JPN225", "N225": "JPN225",
             "RUSSELL": "US2000", "RUT": "US2000", "DXY": "USDX", "USDX": "USDX", "DXYUSD": "USDX",
             "NKY": "JPN225", "NI225": "JPN225", "NQ1!": "NDQ100", "NQ100": "NDQ100", "SPXUSD": "SPX500",
             "FCHI": "FRA40", "HSIINDEX": "HSI", "HKSE": "HSI", "TESLA": "TSLA", "HGUSD": "XCUUSD",
             "COPPER": "XCUUSD", "BITCOIN": "BTCUSD"}

METALS = {"XAUUSD", "XAGUSD"}
INDICES = {"NDQ100", "SPX500", "US30", "US2000", "JPN225"}
UNTRACKED = {"GER40", "HK50", "UK100", "FRA40", "CN50", "USDX", "XAUJPY", "XAUAUD", "XAUGBP"}
UNTRACKED_KIND = {"XAUJPY": "metal", "XAUAUD": "metal", "XAUGBP": "metal"}  # the rest are indices

INDEX_CCY = {"NDQ100": ["USD"], "SPX500": ["USD"], "US30": ["USD"], "US2000": ["USD"], "USDX": ["USD"],
             "JPN225": ["JPY"], "GER40": ["EUR"], "FRA40": ["EUR"], "UK100": ["GBP"], "HK50": ["HKD"],
             "CN50": ["CNY"]}

YAHOO = {"XAUUSD": "GC=F", "XAGUSD": "SI=F", "NDQ100": "NQ=F", "SPX500": "ES=F", "US30": "YM=F",
         "US2000": "RTY=F", "JPN225": "NIY=F"}
CRYPTO_BASES = {"BTC", "ETH", "SOL", "NEAR", "XRP", "ADA", "DOGE", "BNB", "LTC", "AVAX", "DOT", "LINK"}


def canon_instrument(s):
    s = str(s or "").strip().replace("[[", "").replace("]]", "").strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    s = s.upper().replace("/", "").strip()
    s = DASH_ALIASES.get(s, s)
    s = OVERRIDES.get(s, s)
    return s


def is_fx(sym):
    return len(sym) == 6 and sym[:3] in FX_CCY and sym[3:] in FX_CCY and is_in_scope(sym)


def instrument_class(sym):
    sym = canon_instrument(sym)
    if sym in METALS:
        return "metal"
    if sym in INDICES:
        return "index"
    if sym in UNTRACKED:
        return "untracked"
    if is_fx(sym):
        return "fx"
    return "out"


def class_kind(sym):
    """Class used for comparisons: untracked symbols count as their underlying kind."""
    sym = canon_instrument(sym)
    c = instrument_class(sym)
    if c == "untracked":
        return UNTRACKED_KIND.get(sym, "index")
    return c


def instrument_currencies(sym):
    sym = canon_instrument(sym)
    if is_fx(sym):
        return [sym[:3], sym[3:]]
    if sym in METALS:
        return ["USD"]
    if sym in UNTRACKED_KIND:
        return ["USD", sym[3:]]
    if sym in INDEX_CCY:
        return INDEX_CCY[sym]
    if sym.endswith("USD") and sym[:-3] in CRYPTO_BASES:
        return ["USD"]
    return []


def yahoo_ticker(sym, asset_class=None):
    sym = canon_instrument(sym)
    if sym in YAHOO:
        return YAHOO[sym]
    if is_fx(sym):
        return f"{sym}=X"
    if sym.endswith("USD") and sym[:-3] in CRYPTO_BASES:
        return f"{sym[:-3]}-USD"
    return None


# --------------------------------------------------------------------------- vocab

PRESENTERS = {"binni", "pauline", "unknown"}

ENUMS = {
    "asset_class": {"fx", "metal", "index", "crypto", "stock", "commodity"},
    "tf": {"m15", "1h", "4h", "d", "w", "m", "unspecified"},
    "direction": {"long", "short", "neutral"},
    "verdict": {"take", "wait_retest", "conditional", "watch", "skip", "already_moved"},
    "structure": {"with_trend", "counter_trend", "range", "transition", "unspecified"},
    "htf": {"aligned", "opposed", "ambiguous", "unspecified"},
}
LISTS = {
    "setup": {"breakout", "retest", "trend_continuation", "pullback_in_trend", "reversal", "range_bounce",
              "range_break", "trendline_break", "pattern_hs", "pattern_double", "tflow", "laggard", "leader"},
    "location": {"htf_level_behind", "htf_level_ahead", "at_d_zone", "open_space", "mid_range",
                 "at_wash_line", "at_ema"},
    "risk_flags": {"news_pending", "ugly_chart", "friday", "late_entry", "room_consumed", "counter_trend",
                   "intervention_risk"},
}
REQUIRED = ["opportunity_no", "section", "instrument", "asset_class", "tf", "direction", "verdict", "condition",
            "setup", "location", "structure", "htf", "risk_flags", "quote"]
OPTIONAL = {"signal_named": None, "levels": None, "timestamp": None}
KNOWN = set(REQUIRED) | set(OPTIONAL)


# --------------------------------------------------------------------------- notes

def note_stem_info(path):
    stem = Path(path).stem
    m = STEM_RE.match(stem)
    if not m:
        return None
    st = m.group(2)
    if st.startswith("weekly-review"):
        st = "weekly-review"
    return {"stem": stem, "date": m.group(1), "session_type": st}


def all_notes():
    out = []
    for d in NOTE_DIRS:
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            if note_stem_info(p):
                out.append(p)
    return sorted(out, key=lambda p: p.stem, reverse=True)


def rel_note(path):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def norm_text(s):
    s = s.replace("[[", "").replace("]]", "")
    s = re.sub(r"[*_`]", "", s)
    s = (s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
         .replace("…", "...").replace("–", "-").replace("—", "-"))
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def words(s):
    return re.findall(r"[a-z0-9]+", norm_text(s))


def quote_tokens(s):
    """Tokens for the quote-length guard: a number like 1.0850 or 1,234 stays one token, and
    single letters (the e and g of "e.g.") don't count."""
    return [t for t in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", norm_text(s)) if len(t) > 1 or t.isdigit()]


def opportunities(note_text):
    """{number: item text} for the first '## ...Opportunit...' section, or None if absent."""
    lines = note_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and "opportunit" in ln.lower():
            start = i + 1
            break
    if start is None:
        return None
    items, cur = {}, None
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        m = re.match(r"^(\d+)\. ", ln)
        if m:
            cur = int(m.group(1))
            items[cur] = ln
        elif cur is not None:
            items[cur] += "\n" + ln
    return items


def instrument_mentioned(text, instrument):
    t = text.upper()
    names = {instrument} | {k for k, v in list(DASH_ALIASES.items()) + list(OVERRIDES.items())
                            if canon_instrument(v) == instrument or canon_instrument(k) == instrument}
    for n in names:
        if re.search(r"(?<![A-Z0-9])" + re.escape(n.upper()) + r"(?![A-Z0-9])", t):
            return True
    # bracketed raw mention, e.g. [[NASDAQ]]
    for m in re.finditer(r"\[\[([^\]|#]+)", text):
        if canon_instrument(m.group(1)) == instrument:
            return True
    return False


# --------------------------------------------------------------------------- raw transcripts

TYPE_TOKENS = {"ahh-access-time": ["ahh-access-time", "access-time"], "ahh-session": ["ahh-session"],
               "taw-pro": ["taw-pro", "tat-pro"], "weekly-review": ["weekly-review"],
               "3tt": ["3-trade-thoughts", "3tt"], "tar-session": ["tar-session"]}


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    if m:
        for ln in m.group(1).splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def find_raw(note_path, note_text, info):
    fm = frontmatter(note_text)
    raw = fm.get("raw")
    if raw:
        for base in (ROOT, Path(note_path).resolve().parent):
            p = (base / raw).resolve()
            if p.is_file():
                return p
    raw_dir = ROOT / "raw"
    if not raw_dir.is_dir():
        return None
    date = info["date"]
    dates = (date, date.replace("-", ""))
    cands, date_only = [], []
    for p in sorted(raw_dir.rglob("*.md")):
        if "recordings" in p.relative_to(raw_dir).parts:
            continue
        b = re.sub(r"[_ ]", "-", p.name.lower())
        if not any(d in b for d in dates):
            continue
        date_only.append(p)
        if any(tok in b for tok in TYPE_TOKENS[info["session_type"]]):
            cands.append(p)
    if cands:
        return cands[0]
    if len(date_only) == 1:
        return date_only[0]
    return None


def quote_in_raw(quote, raw_words, window=400, step=50, need=0.8):
    q = words(quote)
    if not q:
        return False
    n = len(raw_words)
    starts = range(0, max(1, n - window + step), step) if n > window else [0]
    for s in starts:
        w = raw_words[s:s + window]
        # greedy in-order scan: each quote word is matched at its next occurrence after the
        # previous match; a quote word with no later occurrence is skipped (gaps allowed)
        hit = 0
        j = 0
        for tok in q:
            k = j
            while k < len(w) and w[k] != tok:
                k += 1
            if k < len(w):
                hit += 1
                j = k + 1
        if hit >= need * len(q):
            return True
    return False


# --------------------------------------------------------------------------- store io

@contextlib.contextmanager
def store_lock(timeout=60):
    d = cases_dir()
    d.mkdir(parents=True, exist_ok=True)
    fh = open(d / "cases.lock", "a+")
    t0 = time.time()
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() - t0 > timeout:
                fh.close()
                log("lock timeout on", d / "cases.lock")
                sys.exit(4)
            time.sleep(0.5)
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def load_cases():
    p = cases_dir() / "cases.jsonl"
    out = []
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def load_done():
    p = cases_dir() / "notes_done.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_cases(cases):
    atomic_write(cases_dir() / "cases.jsonl", "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases))


def save_done(done):
    atomic_write(cases_dir() / "notes_done.json", json.dumps(done, indent=1, ensure_ascii=False, sort_keys=True))


def check_writer():
    if os.environ.get("SIGNAL_CASES_DIR"):
        return
    try:
        host = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except Exception:
        host = ""
    if not host:
        import socket
        host = socket.gethostname().split(".")[0]
    try:
        writer = json.loads(CONFIG_PATH.read_text()).get("writer_host")
    except Exception:
        writer = None
    if not writer or host != writer:
        log(f"case store writes run on the Mac mini (writer_host={writer!r}, this host={host!r}); "
            "the staged file is kept")
        sys.exit(6)


# --------------------------------------------------------------------------- add

def validate_case(c, note_norm, opps):
    if not isinstance(c, dict):
        return "not an object"
    for k in REQUIRED:
        if k not in c:
            return f"missing {k}"
    for k, allowed in ENUMS.items():
        if not isinstance(c[k], str) or c[k] not in allowed:
            return f"{k}={c[k]!r} not allowed"
    for k, allowed in LISTS.items():
        if not isinstance(c[k], list):
            return f"{k} must be a list"
        if not all(isinstance(v, str) for v in c[k]):
            return f"{k} items must be strings"
        bad = [v for v in c[k] if v not in allowed]
        if bad:
            return f"{k} has unknown {bad}"
    if not isinstance(c["section"], str) or not c["section"].strip():
        return "section empty"
    if not isinstance(c["quote"], str) or not (1 <= len(c["quote"]) <= 300):
        return "quote must be 1-300 chars"
    if c["verdict"] in ("conditional", "wait_retest") and not (isinstance(c["condition"], str) and c["condition"].strip()):
        return f"condition required for {c['verdict']}"
    if not isinstance(c["instrument"], str):
        return "instrument must be a string"
    if c["condition"] is not None and not isinstance(c["condition"], str):
        return "condition must be a string or null"
    inst = canon_instrument(c["instrument"])
    if not inst:
        return "instrument empty"
    cls = instrument_class(inst)
    if cls != "out":
        want = class_kind(inst)
        if c["asset_class"] != want:
            return f"asset_class {c['asset_class']} but {inst} is {want}"
    on = c["opportunity_no"]
    if on is not None:
        if opps is None:
            return "note has no opportunities section; opportunity_no must be null"
        if not isinstance(on, int) or isinstance(on, bool) or on not in opps:
            return f"opportunity_no {on} not in the note"
        if not instrument_mentioned(opps[on], inst):
            return f"opportunity {on} does not mention {inst}"
    if len(quote_tokens(c["quote"])) < 2:
        return "quote too short to verify (needs 2+ words)"
    if not re.search(r"(?<![a-z0-9])" + re.escape(norm_text(c["quote"])) + r"(?![a-z0-9])", note_norm):
        return "quote not found in note"
    return None


def cmd_add(args):
    note = Path(args.note)
    if not note.is_absolute():
        note = ROOT / note
    info = note_stem_info(note)
    if not info:
        log(f"note name does not match the session-note pattern: {note.name}")
        return 2
    try:
        note_text = note.read_text(encoding="utf-8")
        staged = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if not isinstance(staged, list):
            raise ValueError("staged file is not a JSON array")
    except Exception as e:
        log(f"unreadable: {e}")
        return 2
    check_writer()
    note_norm = norm_text(note_text)
    opps = opportunities(note_text)
    raw_path = find_raw(note, note_text, info)
    raw_words = words(raw_path.read_text(encoding="utf-8", errors="ignore")) if raw_path else None

    if info["stem"] in load_done() and not args.replace:
        log("note already extracted (use --replace)")
        return 1

    accepted, rejects, counters = [], [], {}
    for i, c in enumerate(staged):
        why = validate_case(c, note_norm, opps)
        if why:
            rejects.append({"index": i, "reason": why, "case": c})
            log(f"  reject #{i}: {why}")
            continue
        extra = set(c) - KNOWN - {"note", "date", "session_type", "id"}
        if extra:
            log(f"  #{i}: ignoring unknown keys {sorted(extra)}")
        inst = canon_instrument(c["instrument"])
        counters[inst] = counters.get(inst, 0) + 1
        rec = {"id": f"{info['stem']}-{inst.lower()}-{counters[inst]}", "note": rel_note(note),
               "date": info["date"], "session_type": info["session_type"], "presenter": args.presenter}
        for k in REQUIRED:
            rec[k] = c[k]
        for k, d in OPTIONAL.items():
            rec[k] = c.get(k, d)
        rec["instrument"] = inst
        rec["quote_in_raw"] = quote_in_raw(c["quote"], raw_words) if raw_words is not None else None
        rec["extracted_at"] = now_sgt().isoformat(timespec="seconds")
        rec["hindsight"] = None
        accepted.append(rec)

    rdir = runs_dir()
    rej_path = rdir / f"cases_{info['stem']}.rejects.json"
    if rejects:
        atomic_write(rej_path, json.dumps(rejects, indent=1, ensure_ascii=False))
    elif rej_path.exists():
        rej_path.unlink()

    print(f"added {len(accepted)} of {len(staged)} ({len(rejects)} rejected)")
    if staged and not accepted:
        log("every case was rejected; nothing stored, the note stays as it was")
        return 3
    with store_lock():
        done = load_done()
        if info["stem"] in done and not args.replace:
            log("note already extracted (use --replace)")
            return 1
        cases = load_cases()
        old = {c["id"]: c for c in cases if c.get("note") == rel_note(note)}
        for rec in accepted:
            o = old.get(rec["id"])
            if o and o.get("hindsight") and all(o.get(k) == rec[k] for k in ("instrument", "direction", "verdict")):
                rec["hindsight"] = o["hindsight"]
        cases = [c for c in cases if c.get("note") != rel_note(note)] + accepted
        save_cases(cases)
        done[info["stem"]] = {"note": rel_note(note), "extracted_at": now_sgt().isoformat(timespec="seconds"),
                              "cases": len(accepted), "rejected": len(rejects), "presenter": args.presenter}
        save_done(done)
    return 0


# --------------------------------------------------------------------------- yahoo + score

def yahoo_daily(ticker, start, end):
    """Daily bars with exchange-local dates. Returns (bars, error) with error in
    {None, 'fetch_failed', 'no_bars'}."""
    p1 = int(dt.datetime.combine(start, dt.time(), dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.combine(end, dt.time(), dt.timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
           f"?interval=1d&period1={p1}&period2={p2}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        res = data["chart"]["result"][0]
    except Exception:
        return [], "fetch_failed"
    return parse_yahoo(res)


def parse_yahoo(res):
    meta = res.get("meta") or {}
    tzname = meta.get("exchangeTimezoneName") or "UTC"
    tz = ZoneInfo(tzname)
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c = (q.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c):
            continue
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(tz).date()
        bars.append({"date": d.isoformat(), "open": o, "high": h, "low": l, "close": c})
    if not bars:
        return [], "no_bars"
    return bars, None


def wilder_atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def score_case(case, bars):
    """Returns a hindsight dict, or None if not enough bars after entry yet."""
    after = [i for i, b in enumerate(bars) if b["date"] > case["date"]]
    if not after:
        return None
    ei = after[0]
    before = bars[:ei]
    atr = wilder_atr(before[-40:]) if len(before) >= 15 else None
    if not atr:
        return {"status": "unscored", "reason": "no_bars"}
    window = bars[ei:ei + 10]
    if len(window) < 10:
        return None
    entry = window[0]["open"]
    long = case["direction"] == "long"
    status = "flat"
    mfe = mae = 0.0
    for b in window:
        fav = (b["high"] - entry) if long else (entry - b["low"])
        adv = (entry - b["low"]) if long else (b["high"] - entry)
        mfe, mae = max(mfe, fav), max(mae, adv)
        if status == "flat":
            hit_f, hit_a = fav >= atr, adv >= atr
            if hit_a:
                status = "adverse"
            elif hit_f:
                status = "favourable"
    return {"status": status, "mfe_atr": round(mfe / atr, 2), "mae_atr": round(mae / atr, 2), "reason": None}


def cmd_score(args, fetch=None):
    fetch = fetch or yahoo_daily
    check_writer()
    today = now_sgt().date()
    cases = load_cases()
    todo = []
    for c in cases:
        if c.get("direction") not in ("long", "short"):
            continue
        if dt.date.fromisoformat(c["date"]) + dt.timedelta(days=14) >= today:
            continue
        h = c.get("hindsight")
        if args.all or h is None or (h.get("status") == "unscored" and h.get("reason") in ("fetch_failed", "no_bars")):
            todo.append(c)
    results, cache = {}, {}
    for c in todo:
        ticker = yahoo_ticker(c["instrument"])
        stamp = now_sgt().isoformat(timespec="seconds")
        if not ticker:
            results[c["id"]] = (c, {"status": "unscored", "mfe_atr": None, "mae_atr": None, "horizon_days": 10,
                                    "scored_at": stamp, "reason": "no_ticker"})
            continue
        d0 = dt.date.fromisoformat(c["date"])
        key = (ticker, c["date"])
        if key not in cache:
            cache[key] = fetch(ticker, d0 - dt.timedelta(days=40), d0 + dt.timedelta(days=30))
        bars, err = cache[key]
        if err:
            h = {"status": "unscored", "reason": err}
        else:
            h = score_case(c, bars)
            if h is None:
                continue
        h.setdefault("mfe_atr", None)
        h.setdefault("mae_atr", None)
        h["horizon_days"] = 10
        h["scored_at"] = stamp
        results[c["id"]] = (c, h)
    counts = {}
    with store_lock():
        cases = load_cases()
        for c in cases:
            r = results.get(c["id"])
            if not r:
                continue
            orig, h = r
            if any(orig.get(k) != c.get(k) for k in ("instrument", "direction", "verdict")):
                continue
            old = c.get("hindsight")
            if h["status"] == "unscored" and old and old.get("status") in ("favourable", "adverse", "flat"):
                continue  # a failed refetch never overwrites a real score
            c["hindsight"] = h
            counts[h["status"] if h["status"] != "unscored" else "unscored/" + str(h["reason"])] = \
                counts.get(h["status"] if h["status"] != "unscored" else "unscored/" + str(h["reason"]), 0) + 1
        save_cases(cases)
    print("scored:", json.dumps(counts, sort_keys=True) if counts else "nothing to score")
    return 0


# --------------------------------------------------------------------------- precedents

TF_ORDER = ["m15", "1h", "4h", "d", "w", "m"]


def tf_points(a, b):
    if a == b:
        return 2
    if a in TF_ORDER and b in TF_ORDER and abs(TF_ORDER.index(a) - TF_ORDER.index(b)) == 1:
        return 1
    return 0


def _set(v):
    return set(v or [])


def similarity(sig_tags, sig_kind, sig_ccy, sig_fx, case):
    pts = mx = 0.0
    subst = []
    tf = sig_tags.get("tf")
    if tf and tf != "unspecified":
        mx += 2
        pts += tf_points(tf, case.get("tf"))
    for key in ("setup", "location"):
        s = _set(sig_tags.get(key))
        if s:
            mx += 2 * len(s)
            shared = s & _set(case.get(key))
            pts += 2 * len(shared)
            if shared:
                subst.append(key)
    for key, w in (("structure", 2), ("htf", 1.5)):
        v = sig_tags.get(key)
        if v and v != "unspecified":
            mx += w
            if case.get(key) == v:
                pts += w
                subst.append(key)
    rf = _set(sig_tags.get("risk_flags"))
    if rf:
        mx += len(rf)
        pts += len(rf & _set(case.get("risk_flags")))
    mx += 1
    cinst = canon_instrument(case.get("instrument"))
    ckind = class_kind(cinst) if instrument_class(cinst) != "out" else case.get("asset_class")
    if ckind == sig_kind:
        pts += 1
    if sig_fx:
        mx += 1
        if set(sig_ccy) & set(instrument_currencies(cinst)) and is_fx(cinst):
            pts += 1
    return (pts / mx if mx else 0.0), subst


def find_precedents(signal, cases, top=5, threshold=0.45):
    inst = canon_instrument(signal["instrument"])
    t = signal["time"].astimezone(SGT).date()
    lo = t - dt.timedelta(days=21)
    direction = signal.get("direction")
    eligible = [c for c in cases if dt.date.fromisoformat(c["date"]) < t]
    recent = [c for c in eligible if canon_instrument(c["instrument"]) == inst
              and dt.date.fromisoformat(c["date"]) >= lo]
    recent.sort(key=lambda c: (c["date"], c["id"]), reverse=True)
    recent = recent[:3]
    rid = {c["id"] for c in recent}
    kind = class_kind(inst) if instrument_class(inst) != "out" else None
    ccy = instrument_currencies(inst)
    fx = is_fx(inst)
    sims = []
    for c in eligible:
        if c["id"] in rid:
            continue
        s, subst = similarity(signal.get("tags") or {}, kind, ccy, fx, c)
        if subst and s >= threshold:
            sims.append(dict(c, similarity=round(s, 3), substantive=subst))
    sims.sort(key=lambda c: (c["similarity"], c["date"]), reverse=True)
    sd = lambda c: c.get("direction") == direction and direction in ("long", "short")
    return {"instrument_recent": [dict(c, same_direction=sd(c)) for c in recent],
            "similar": [dict(c, same_direction=sd(c)) for c in sims[:top]]}


# --------------------------------------------------------------------------- alerts / coverage

TFLOW_RE = re.compile(
    r"^Tflow (Bullish|Bearish) Signal(?: @Zone \((Support|Resistance) Zone x(\d+) \(([A-Z,]+)\), "
    r"Zone High: (\d+(?:\.\d+)?), Zone Low: (\d+(?:\.\d+)?)\))?: D Level: (\d+(?:\.\d+)?), (LL|HH): (\d+(?:\.\d+)?)")


def parse_tflow_event(event):
    m = TFLOW_RE.match(str(event or "").strip())
    if not m:
        return {"parse_error": event, "at_zone": False}
    zone = None
    if m.group(2):
        zone = {"role": m.group(2), "count": int(m.group(3)), "tfs": m.group(4),
                "high": float(m.group(5)), "low": float(m.group(6))}
    return {"direction": m.group(1), "at_zone": zone is not None, "zone": zone, "d_level": float(m.group(7)),
            "pivot_label": m.group(8), "pivot": float(m.group(9))}


def parse_alert_time(row):
    d = str(row.get("Date", "")).strip()
    t = str(row.get("Time", "")).strip()
    if not d or not t:
        return None
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return dt.datetime.combine(dt.date.fromisoformat(d), dt.datetime.strptime(t, fmt).time(), SGT)
        except ValueError:
            continue
    return None


def load_alerts(rows_by_tab, since):
    groups, skipped = {}, 0
    for tab, rows in rows_by_tab.items():
        for row in rows or []:
            at = parse_alert_time(row)
            sig = str(row.get("Signal Type", "")).strip()
            direc = str(row.get("Direction", "")).strip()
            if at is None or not sig or direc not in ("Bullish", "Bearish"):
                skipped += 1
                continue
            base = sig[len(TFLOW_PREFIX):] if sig.startswith(TFLOW_PREFIX) else sig
            if base not in SIGNAL_TIER:
                continue
            sym = canon_instrument(row.get("Symbol", ""))
            if instrument_class(sym) == "out":
                continue
            nc = at.replace(minute=0, second=0, microsecond=0)
            if nc < since:
                continue
            d = "long" if direc == "Bullish" else "short"
            k = (sym, tab, d, nc)
            groups.setdefault(k, []).append((sig, base, row, at))
    alerts = []
    for (sym, tab, d, nc), rows in groups.items():
        tfl = [r for r in rows if r[0].startswith(TFLOW_PREFIX)]
        chosen = tfl[0] if tfl else max(rows, key=lambda r: SIGNAL_TIER[r[1]])
        alerts.append({
            "key": f"{sym}|{tab}|{'Bull' if d == 'long' else 'Bear'}|{nc.isoformat()}",
            "symbol": sym, "tv_symbol": chosen[2].get("Symbol", ""), "class": instrument_class(sym), "tf": tab,
            "direction": d, "signal": chosen[0], "also_fired": sorted({r[0] for r in rows} - {chosen[0]}),
            "event": str(chosen[2].get("Event", "")), "tflow": parse_tflow_event(chosen[2].get("Event")) if tfl else None,
            "nominal_close": nc, "alert_time": min(r[3] for r in rows)})
    alerts.sort(key=lambda a: (a["nominal_close"], a["key"]))
    return alerts, skipped


def brief_bias_lookup(brief_dir=None):
    brief_dir = Path(brief_dir or DAILY_BRIEF_DIR)
    files = {}
    if brief_dir.is_dir():
        for p in brief_dir.glob("*.json"):
            try:
                d = dt.date.fromisoformat(p.stem)
            except ValueError:
                continue
            avail = max(dt.datetime.combine(d, dt.time(6, 30), SGT),
                        dt.datetime.fromtimestamp(p.stat().st_mtime, SGT))
            files[d] = (p, avail)
    cache = {}

    def lookup(symbol, when):
        best = None
        for d, (p, avail) in files.items():
            if avail <= when and (when.date() - d).days <= 3 and (best is None or d > best[0]):
                best = (d, p)
        if not best:
            return None
        if best[1] not in cache:
            try:
                cache[best[1]] = {canon_instrument(e.get("symbol")): str(e.get("bias", "")).lower()
                                  for e in json.loads(best[1].read_text())}
            except Exception:
                cache[best[1]] = {}
        return cache[best[1]].get(canon_instrument(symbol))
    return lookup


def load_calendar(path=None):
    path = Path(path or CALENDAR_NOTE)
    weeks, events = [], []
    if not path.exists():
        return weeks, events
    cur = False
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("## "):
            m = re.search(r"(This|Next) Week.*\((\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\)", ln)
            cur = bool(m)
            if m:
                weeks.append((dt.datetime.combine(dt.date.fromisoformat(m.group(2)), dt.time(), SGT),
                              dt.datetime.combine(dt.date.fromisoformat(m.group(3)), dt.time(23, 59), SGT)))
            continue
        if cur and ln.startswith("| 20"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            try:
                when = dt.datetime.combine(dt.date.fromisoformat(cells[0]),
                                           dt.datetime.strptime(cells[1], "%H:%M").time(), SGT)
            except (ValueError, IndexError):
                continue
            events.append({"when": when, "ccy": cells[2].upper(), "event": cells[3]})
    return weeks, events


def alert_tags(a, alerts_by_tab_close, brief, calendar):
    tags = {"tf": a["tf"].lower(), "setup": [], "location": [], "structure": "unspecified", "htf": "unspecified",
            "risk_flags": []}
    if a["signal"].startswith(TFLOW_PREFIX):
        tags["setup"] += ["tflow", "pullback_in_trend"]
    if a["class"] == "fx":
        closes = alerts_by_tab_close[a["tf"]]["closes"]
        idx = closes.index(a["nominal_close"])
        prior_closes = set(closes[max(0, idx - 3):idx])
        prior = [x for x in alerts_by_tab_close[a["tf"]]["alerts"]
                 if x["nominal_close"] in prior_closes and x["class"] == "fx" and x["symbol"] != a["symbol"]]
        if prior:
            bd = lambda d: "Bullish" if d == "long" else "Bearish"
            score, _ = cross_pair_consistency({"clean": a["symbol"], "direction": bd(a["direction"])},
                                              [{"clean": x["symbol"], "direction": bd(x["direction"])} for x in prior])
            if score >= 0.5:
                tags["setup"].append("laggard")
    if a["tflow"] and a["tflow"].get("at_zone"):
        tags["location"].append("at_d_zone")
    bias = brief(a["symbol"], a["nominal_close"]) if brief else None
    if bias:
        b = {"bullish": "long", "bearish": "short"}.get(bias, "neutral")
        tags["htf"] = "aligned" if b == a["direction"] else ("ambiguous" if b == "neutral" else "opposed")
    nyt = a["nominal_close"].astimezone(NY)
    if nyt.weekday() == 4 and nyt.hour >= 1:
        tags["risk_flags"].append("friday")
    weeks, events = calendar
    end = a["nominal_close"] + dt.timedelta(hours=24)
    if any(w0 <= a["nominal_close"] and end <= w1 + dt.timedelta(minutes=1) for w0, w1 in weeks):
        ccy = set(instrument_currencies(a["symbol"]))
        if any(a["nominal_close"] <= e["when"] <= end and e["ccy"] in ccy for e in events):
            tags["risk_flags"].append("news_pending")
    return tags


def fetch_tabs():
    from scripts.fetch_google_sheet import fetch_with_service_account
    rows, status, tflow_skipped = {}, {}, False
    for tab, key in (("1H", "H1"), ("4H", "4H")):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                r = fetch_with_service_account(key)
        except Exception as e:
            r = None
            log(f"{tab} tab failed: {e}")
        out = buf.getvalue()
        if out:
            sys.stderr.write(out)
        if "Tflow supplement skipped" in out:
            tflow_skipped = True
        if not r:
            status[tab] = "failed"
            rows[tab] = []
        else:
            status[tab] = "ok"
            rows[tab] = r
    return rows, status, tflow_skipped


def run_coverage(rows_by_tab, status, tflow_skipped, cases, days, now, brief, calendar):
    since = (now - dt.timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    alerts, skipped = load_alerts(rows_by_tab, since)
    by_tab = {}
    for tab in ("1H", "4H"):
        al = [a for a in alerts if a["tf"] == tab]
        by_tab[tab] = {"alerts": al, "closes": sorted({a["nominal_close"] for a in al})}
    rows = []
    mix = {"setup": 0, "location": 0, "structure": 0, "htf": 0}
    top, tag_seen, tag_matched = {}, {}, {}
    pres_mix = {"instrument_recent": {}, "similar": {}}
    only_htf = 0
    for a in alerts:
        tags = alert_tags(a, by_tab, brief, calendar)
        sig = {"instrument": a["symbol"], "direction": a["direction"], "time": a["nominal_close"], "tags": tags}
        pr = find_precedents(sig, cases)
        rec_ok = len(pr["instrument_recent"]) >= 1
        sim_ok = len(pr["similar"]) >= 2
        rows.append((a, rec_ok, sim_ok))
        for c in pr["instrument_recent"]:
            top.setdefault(c["id"], [0, 0])[0] += 1
            pm = pres_mix["instrument_recent"]
            pm[c.get("presenter", "unknown")] = pm.get(c.get("presenter", "unknown"), 0) + 1
        for c in pr["similar"]:
            top.setdefault(c["id"], [0, 0])[1] += 1
            pm = pres_mix["similar"]
            pm[c.get("presenter", "unknown")] = pm.get(c.get("presenter", "unknown"), 0) + 1
            for k in c["substantive"]:
                mix[k] += 1
        if sim_ok and all(c["substantive"] == ["htf"] for c in pr["similar"]):
            only_htf += 1
        for key in ("setup", "location", "risk_flags"):
            for v in tags[key]:
                tag_seen.setdefault(key, set()).add(v)
                if any(v in (c.get(key) or []) for c in pr["similar"]):
                    tag_matched.setdefault(key, set()).add(v)
        if tags["htf"] != "unspecified":
            tag_seen.setdefault("htf", set()).add(tags["htf"])
            if any(c.get("htf") == tags["htf"] for c in pr["similar"]):
                tag_matched.setdefault("htf", set()).add(tags["htf"])

    def rates(sel):
        n = len(sel)
        if not n:
            return {"n": 0, "instrument_recent_ge1": None, "similar_ge2": None, "either": None}
        pct = lambda k: round(100.0 * k / n, 1)
        return {"n": n, "instrument_recent_ge1": pct(sum(r[1] for r in sel)),
                "similar_ge2": pct(sum(r[2] for r in sel)), "either": pct(sum(r[1] or r[2] for r in sel))}

    case_dates = sorted(c["date"] for c in cases)
    report = {
        "generated_at": now.isoformat(timespec="seconds"), "days": days,
        "alerts_range": {"first": alerts[0]["nominal_close"].isoformat() if alerts else None,
                         "last": alerts[-1]["nominal_close"].isoformat() if alerts else None},
        "sheet": {"1H": status.get("1H"), "4H": status.get("4H"), "tflow_skipped": tflow_skipped},
        "skipped_rows": skipped,
        "alerts": {"total": len(alerts), "by_tab": {t: len(by_tab[t]["alerts"]) for t in by_tab},
                   "by_class": {k: sum(1 for a in alerts if a["class"] == k) for k in ("fx", "metal", "index", "untracked")}},
        "cases": {"total": len(cases), "first_date": case_dates[0] if case_dates else None,
                  "last_date": case_dates[-1] if case_dates else None},
        "rates": rates(rows),
        "rates_by_tab": {t: rates([r for r in rows if r[0]["tf"] == t]) for t in ("1H", "4H")},
        "rates_by_class": {k: rates([r for r in rows if r[0]["class"] == k]) for k in ("fx", "metal", "index", "untracked")},
        "similar_component_mix": mix,
        "similar_only_htf": only_htf,
        "precedent_presenter_mix": pres_mix,
        "top_cases": [{"id": k, "as_recent": v[0], "as_similar": v[1]}
                      for k, v in sorted(top.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), kv[0]))[:10]],
        "never_matched_tags": {k: sorted(tag_seen.get(k, set()) - tag_matched.get(k, set()))
                               for k in ("setup", "location", "htf", "risk_flags")},
        "gate": {"metric": "either", "value": rates(rows)["either"], "recommend_go_at": 60},
    }
    return report


def print_report(r):
    if r["sheet"].get("tflow_skipped"):
        print("WARNING: Tflow supplement skipped — Tflow/@Zone tags are missing from this replay")
    print(f"Coverage replay — {r['days']} days, generated {r['generated_at']}")
    print(f"Sheet: 1H {r['sheet']['1H']}, 4H {r['sheet']['4H']} · skipped rows {r['skipped_rows']}")
    print(f"Alerts: {r['alerts']['total']} ({r['alerts']['by_tab']}) by class {r['alerts']['by_class']}")
    print(f"Alert range: {r['alerts_range']['first']} → {r['alerts_range']['last']}")
    print(f"Cases: {r['cases']['total']} ({r['cases']['first_date']} → {r['cases']['last_date']})")
    fmt = lambda x: "—" if x["n"] == 0 else (f"n={x['n']} recent≥1 {x['instrument_recent_ge1']}% · "
                                               f"similar≥2 {x['similar_ge2']}% · either {x['either']}%")
    print("All:", fmt(r["rates"]))
    for t, v in r["rates_by_tab"].items():
        print(f"  {t}:", fmt(v))
    for k, v in r["rates_by_class"].items():
        print(f"  {k}:", fmt(v))
    print("Similar-match components:", r["similar_component_mix"], "· alerts resting on htf alone:",
          r["similar_only_htf"])
    print("Precedents by presenter:", r["precedent_presenter_mix"])
    print("Top cases:")
    for t in r["top_cases"]:
        print(f"  {t['id']}: recent {t['as_recent']}, similar {t['as_similar']}")
    print("Never-matched tags:", r["never_matched_tags"])
    print(f"GATE: {r['gate']['value']}% (recommend go at >= {r['gate']['recommend_go_at']}%)")


def cmd_coverage(args):
    rows, status, tflow_skipped = fetch_tabs()
    if status.get("1H") == "failed" and status.get("4H") == "failed":
        log("both sheet tabs failed")
        return 3
    r = run_coverage(rows, status, tflow_skipped, load_cases(), args.days, now_sgt(), brief_bias_lookup(),
                     load_calendar())
    if args.json:
        print(json.dumps(r, indent=1))
    else:
        print_report(r)
    return 0


# --------------------------------------------------------------------------- pending / stats / match

def cmd_pending(args):
    done = load_done()
    notes = [p for p in all_notes() if p.stem not in done]
    if args.json:
        print(json.dumps([rel_note(p) for p in notes], indent=1))
    else:
        for p in notes:
            print(rel_note(p))
    return 0


def cmd_stats(args):
    cases, done = load_cases(), load_done()
    pend = [p for p in all_notes() if p.stem not in done]
    out = {"cases": len(cases), "notes_done": len(done), "notes_pending": len(pend),
           "rejected_total": sum(v.get("rejected", 0) for v in done.values())}
    for k in ("presenter", "session_type", "verdict", "tf", "asset_class", "direction"):
        cnt = {}
        for c in cases:
            cnt[c.get(k)] = cnt.get(c.get(k), 0) + 1
        out[k] = dict(sorted(cnt.items(), key=lambda kv: -kv[1]))
    out["quote_in_raw"] = {str(v): sum(1 for c in cases if c.get("quote_in_raw") is v) for v in (True, False, None)}
    hs = {}
    for c in cases:
        h = c.get("hindsight")
        k = "null" if not h else (h["status"] if h["status"] != "unscored" else f"unscored/{h.get('reason')}")
        hs[k] = hs.get(k, 0) + 1
    out["hindsight"] = hs
    out["zero_case_notes"] = sorted(s for s, v in done.items() if v.get("cases") == 0)
    print(json.dumps(out, indent=1))
    return 0


def cmd_match(args):
    sig = json.loads(Path(args.signal).read_text())
    sig["time"] = dt.datetime.fromisoformat(sig["time"])
    if sig["time"].tzinfo is None:
        sig["time"] = sig["time"].replace(tzinfo=SGT)
    print(json.dumps(find_precedents(sig, load_cases(), top=args.top), indent=1, ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Signal Judge Phase 1 — Binni case store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pending", help="session notes not yet extracted")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("add", help="store a note's staged cases")
    p.add_argument("--note", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--replace", action="store_true")
    p.add_argument("--presenter", required=True, choices=sorted(PRESENTERS),
                   help="who presented the session (read the note header): binni, pauline, or unknown")
    p = sub.add_parser("score", help="hindsight-score directional cases")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("match", help="precedents for one signal (debug)")
    p.add_argument("--signal", required=True)
    p.add_argument("--top", type=int, default=5)
    p = sub.add_parser("coverage", help="replay recent alerts against the store")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--json", action="store_true")
    sub.add_parser("stats", help="store counts")
    args = ap.parse_args(argv)
    return {"pending": cmd_pending, "add": cmd_add, "score": cmd_score, "match": cmd_match,
            "coverage": cmd_coverage, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

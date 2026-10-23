#!/usr/bin/env python3
"""
4H Forex Signal Validation — post-signal chart validation scorecard.

A fired 4H TAT alert is NOT a trade. binni_alert_analysis.py buckets alerts by
direction but never reads price, never computes R:R, and never checks whether the
signal bar actually closed convincingly through its level. This script applies the
validation doctrine taught across the AHH / hand-holding / TAW Pro / TAR / weekly
review transcripts in raw/ as explicit gates.

Tier-0 hard gates (any fail => REJECT):
  G1 Closed bar         — the signal's 4H bar must have fully closed (else PENDING CLOSE)
  G2 Convincing close   — body close through the level, not a wick, not marginal
  G3 HTF permission     — Daily/Weekly bias must not oppose
  G4 Room to target     — <=50% of the leg to the next opposing level consumed
  G5 R:R >= 1:1         — TP = next opposing level, SL = elbow-invalidation swing
  G6 Break of structure — with the 4H trend (HH+HL / LH+LL), or the signal bar
                          closed past the latest swing high/low

Tier-1 quality score (0-10) is applied only to survivors; see score_tier1().

See .agents/skills/h4-signal-validation/reference/doctrine.md for the transcript
quote behind every gate.

Usage:
    python3 scripts/validate_h4_signals.py                     # today's 4H alerts
    python3 scripts/validate_h4_signals.py --date 2026-09-19
    python3 scripts/validate_h4_signals.py --symbol GBPUSD
    python3 scripts/validate_h4_signals.py --track             # advance open watches
    python3 scripts/validate_h4_signals.py --stats             # hit-rate by score band
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records
from scripts.scan_drhr_setups import format_price_precision
from scripts.scan_fake_breakout_setups import (
    SGT,
    ANCHOR_4H,
    yahoo_ticker,
    fetch_1h_bars,
    aggregate_4h_bars,
)

WIKI_ROOT = Path(__file__).resolve().parent.parent
MCP_DIR = Path.home() / "tradingview-mcp"
RULES_PATH = MCP_DIR / "rules.json"
DAILY_BRIEF_DIR = MCP_DIR / "daily_brief"
WATCH_FILE = WIKI_ROOT / "scripts" / "h4_signal_watches.json"
REPORT_DIR = WIKI_ROOT / "wiki" / "reports" / "tat_analysis" / "h4_validation"
IMAGE_DIR = WIKI_ROOT / "wiki" / "images"

# --- Scope -------------------------------------------------------------------
# FX pairs + metals only. The transcripts explicitly deprecate H4 for SG/HK single
# stocks ("in Singapore, especially in stocks, the H4 just represent like half a
# day... H4 is not significant" — raw/AHH Sessions/2026-07-21-ahh-access-time.md), and indices
# /crypto/oil are out of the stated scope for this workflow.
MAJORS = {"AUD", "NZD", "GBP", "EUR", "USD", "CAD", "CHF", "JPY"}
EXTRA_FX = {"SGD", "CNH"}
FX_CCY = MAJORS | EXTRA_FX
METALS = {"XAUUSD", "XAGUSD"}

# Signal tiers. Opt* = First Retracement Level Broken (strongest reversal context),
# L* = zone fully broken, S* = zone boundary broken (weakest).
SIGNAL_TIER = {"OptBull": 2, "OptBear": 2, "LBull": 1, "LBear": 1, "SBull": 0, "SBear": 0}
BULL_SIGNALS = {"OptBull", "LBull", "SBull"}
BEAR_SIGNALS = {"OptBear", "LBear", "SBear"}

# 4H bars are anchored at 17:00 SGT, so boundaries fall at 01/05/09/13/17/21 SGT.
# The Telegram alert fires at the close of the bar, i.e. at the boundary itself.
BAR_SECONDS = 4 * 3600

# G2 thresholds — the "convincing close" filter the TAT indicator itself omits
# ("when it fires, it actually doesn't filter how much above the red color line.
# Close." — raw/AHH Sessions/2026-08-26-ahh-access-time.md).
MIN_EXCURSION_FRAC = 0.25   # close must clear the level by >=25% of the bar's range
MIN_CLOSE_POS = 0.60        # close must sit in the top 40% (bull) of the bar's range
MAX_ROOM_CONSUMED = 0.50    # G4: reject if >50% of the leg is already gone
MIN_RR = 1.0                # G5: the only explicit numeric floor in the corpus
DAILY_BRIEF_MAX_AGE_DAYS = 3


def now_sgt():
    return datetime.datetime.now(SGT)


def clean_symbol(symbol):
    return symbol.split(":")[-1].upper()


def is_in_scope(symbol):
    sym = clean_symbol(symbol)
    if sym in METALS:
        return True
    if len(sym) != 6:
        return False
    return sym[:3] in FX_CCY and sym[3:] in FX_CCY


def load_scope_symbols():
    """Full in-scope instrument list from rules.json (FX pairs + metals)."""
    try:
        rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [s for s in rules.get("watchlist", []) if is_in_scope(s)]


# --- Alerts ------------------------------------------------------------------

def parse_alert_dt(row):
    """Sheet 'Date' + 'Time' are SGT wall-clock, e.g. 2026-09-19 + '5:01:00'."""
    try:
        d = datetime.datetime.strptime(str(row.get("Date", "")).strip(), "%Y-%m-%d").date()
    except Exception:
        return None
    raw = str(row.get("Time", "")).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            t = datetime.datetime.strptime(raw, fmt).time()
            return datetime.datetime.combine(d, t, tzinfo=SGT)
        except Exception:
            continue
    return None


def load_h4_alerts(target_date, symbol_filter=None, since=None):
    """In-scope 4H alerts for target_date, newest first."""
    rows = fetch_sheet_records("4H")
    out = []
    for row in rows:
        sym = row.get("Symbol", "")
        if not sym or not is_in_scope(sym):
            continue
        if str(row.get("Date", "")).strip() != target_date:
            continue
        dt = parse_alert_dt(row)
        if dt is None:
            continue
        if since and dt.strftime("%H:%M") < since:
            continue
        if symbol_filter and clean_symbol(symbol_filter) != clean_symbol(sym):
            continue
        signal = str(row.get("Signal Type", "")).strip()
        if signal not in SIGNAL_TIER:
            continue
        try:
            signal_price = float(row.get("Signal Price"))
        except (TypeError, ValueError):
            continue
        out.append({
            "symbol": sym,
            "clean": clean_symbol(sym),
            "name": row.get("Name", ""),
            "direction": "Bullish" if signal in BULL_SIGNALS else "Bearish",
            "signal": signal,
            "signal_price": signal_price,
            "event": str(row.get("Event", "")).strip(),
            "alert_dt": dt,
        })
    out.sort(key=lambda a: a["alert_dt"], reverse=True)
    return out


def signal_bar_window(alert_dt):
    """The 4H bar whose CLOSE produced this alert: [start, close).

    Alerts land a few seconds past the boundary (e.g. 5:01:00 for the 01:00-05:00
    bar), so snap back to the bar that had just closed.
    """
    offset = int((alert_dt - ANCHOR_4H).total_seconds() // BAR_SECONDS)
    boundary = ANCHOR_4H + datetime.timedelta(seconds=offset * BAR_SECONDS)
    # `boundary` is the start of the bar the alert timestamp falls INSIDE; the bar
    # that actually closed is the one before it.
    return boundary - datetime.timedelta(seconds=BAR_SECONDS), boundary


def find_bar(bars, start_dt):
    """Locate the aggregated 4H bar starting at start_dt (tolerance: 1 bar)."""
    for b in bars:
        if abs((b["dt"] - start_dt).total_seconds()) < BAR_SECONDS / 2:
            return b
    return None


# --- TAT level labels --------------------------------------------------------
# Per CLAUDE.md: "MajD/MinD <Price> FiRet m15|h1|h4|D|W|M",
#                "MajD/MinD <Price> Sup|Res m15|h1|h4|D|W", "TP : <Price>".
# Real charts also carry looser variants ("TAD Level 1.33500", "S/R Week"), so the
# parser stays tolerant rather than assuming the documented form.
LEVEL_RE = re.compile(
    r"\b(MajD|MinD)\s+([0-9]+\.?[0-9]*)\s+(FiRet|Sup|Res)\b\s*(m15|h1|h4|D|W|M)?",
    re.IGNORECASE,
)
TP_RE = re.compile(r"\bTP\s*:?\s*([0-9]+\.?[0-9]*)", re.IGNORECASE)
GENERIC_LEVEL_RE = re.compile(r"\b(?:TAD|TAT)\s+Level\s+([0-9]+\.?[0-9]*)", re.IGNORECASE)
WASH_RE = re.compile(r"\b(Day|Wk)\s+(Buy|Sell)\b", re.IGNORECASE)


def parse_tat_levels(entry, ref=None):
    """Extract priced TAT levels from a symbol's TAT pine labels.

    Returns [{price, kind, tf, text}] where kind is Sup|Res|FiRet|TP|Level.
    """
    studies = (entry.get("tatLabels") or {}).get("studies") or [{}]
    labels = []
    for st in studies:
        labels.extend(st.get("labels", []) or [])

    levels = []
    for lab in labels:
        text = (lab.get("text") or "").strip()
        if not text:
            continue
        m = LEVEL_RE.search(text)
        if m:
            levels.append({
                "price": float(m.group(2)),
                "kind": m.group(3).title().replace("Firet", "FiRet"),
                "tf": (m.group(4) or "").lower(),
                "text": text,
            })
            continue

        m = TP_RE.search(text)
        if m:
            levels.append({"price": float(m.group(1)), "kind": "TP", "tf": "", "text": text})
            continue

        m = GENERIC_LEVEL_RE.search(text)
        if m:
            levels.append({"price": float(m.group(1)), "kind": "Level", "tf": "", "text": text})
            continue

        # Wash lines carry no price in their text, and a label's own `price` field is
        # a rendered y-coordinate rather than the plotted price — it comes back as
        # nonsense (an AUDCHF wash label yielded 76775.55 against a ~0.58 pair).
        # Wash-line prices must be read live via data_get_pine_lines instead, so they
        # are deliberately not parsed here.

    # Deduplicate on (price, kind), keeping first occurrence.
    seen = set()
    unique = []
    for lv in levels:
        key = (round(lv["price"], 6), lv["kind"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(lv)

    # Defence in depth: a mis-parsed label must never reach a gate. Anything more
    # than 25% away from the chart's own last price is not a level on this chart.
    ref = ref or reference_price(entry)
    if ref:
        unique = [lv for lv in unique if 0.75 * ref <= lv["price"] <= 1.25 * ref]
    return unique


def reference_price(entry):
    quote = entry.get("quote") or {}
    for key in ("last", "close", "price"):
        val = quote.get(key)
        if val:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def triggering_level(levels, price, bull, bar=None, eps_frac=0.0005):
    """The level the signal broke.

    Preferred definition: the level the bar's BODY crossed — it opened on one side
    and closed on the other. When a bar clears several stacked levels, the topmost
    cleared one (bull) is the meaningful reference: it is the line the close has to
    be convincingly beyond.

    If the body crossed nothing, fall back to the nearest level at or behind the
    close. Near-equality counts as behind, because TAT reports a signal AT its level
    so the close frequently sits right on it.
    """
    eps = abs(price) * eps_frac

    if bar is not None:
        lo, hi = min(bar["open"], bar["close"]), max(bar["open"], bar["close"])
        crossed = [lv for lv in levels if lo <= lv["price"] <= hi]
        if crossed:
            return max(crossed, key=lambda lv: lv["price"]) if bull \
                else min(crossed, key=lambda lv: lv["price"])

    if bull:
        pool = [lv for lv in levels if lv["price"] <= price + eps]
    else:
        pool = [lv for lv in levels if lv["price"] >= price - eps]
    if not pool:
        return None
    return min(pool, key=lambda lv: abs(lv["price"] - price))


def nearest_level(levels, price, side, kinds=None):
    """Nearest level strictly above ('up') or below ('down') price."""
    pool = [lv for lv in levels if not kinds or lv["kind"] in kinds]
    if side == "up":
        cands = [lv for lv in pool if lv["price"] > price]
        return min(cands, key=lambda lv: lv["price"] - price) if cands else None
    cands = [lv for lv in pool if lv["price"] < price]
    return min(cands, key=lambda lv: price - lv["price"]) if cands else None


# --- Live chart pass ---------------------------------------------------------

SWING_LOOKBACK_BARS = 60  # ~10 trading days of 4H bars


def find_swings(bars, upto_idx, lookback=SWING_LOOKBACK_BARS):
    """Pivot highs and lows in the bars BEFORE upto_idx, oldest -> newest.

    Computed from bar data, not TradingView's ZigZag labels: the labels' prices are
    rendered coordinates (GBPUSD returned six identical `LH @1.35`), so they cannot
    be trusted for structure either. A pivot is an extreme with two bars on each
    side that do not exceed it. Each pivot is tagged against the previous pivot of
    the same kind: highs as HH/LH, lows as HL/LL (the first of each kind is untagged).
    """
    window = bars[max(0, upto_idx - lookback):upto_idx]
    swings = []
    last_high = last_low = None
    for i in range(2, len(window) - 2):
        b = window[i]
        nbrs = (window[i - 2], window[i - 1], window[i + 1], window[i + 2])
        if all(n["high"] < b["high"] for n in nbrs):
            tag = None if last_high is None else ("HH" if b["high"] > last_high else "LH")
            swings.append({"kind": "high", "tag": tag, "price": b["high"], "dt": b["dt"]})
            last_high = b["high"]
        if all(n["low"] > b["low"] for n in nbrs):
            tag = None if last_low is None else ("HL" if b["low"] > last_low else "LL")
            swings.append({"kind": "low", "tag": tag, "price": b["low"], "dt": b["dt"]})
            last_low = b["low"]
    return swings


def latest_swing(swings, kind):
    for sw in reversed(swings):
        if sw["kind"] == kind:
            return sw
    return None


def structure_from_swings(swings):
    """Per wiki/concepts/market-structure.md: an uptrend needs BOTH a Higher High and
    a Higher Low; a downtrend needs BOTH a Lower High and a Lower Low. Anything else
    (e.g. HH + LL, or only one tagged swing) is Mixed.
    """
    hi = latest_swing(swings, "high")
    lo = latest_swing(swings, "low")
    h, l = (hi or {}).get("tag"), (lo or {}).get("tag")
    if h == "HH" and l == "HL":
        return "Bullish"
    if h == "LH" and l == "LL":
        return "Bearish"
    return "Mixed"


def bar_index(bars, bar):
    if bar is None:
        return None
    return next((i for i, b in enumerate(bars) if b["dt"] == bar["dt"]), None)


def tat_bias(entry):
    """TAT trend bar. NOTE: 'Down Trend' is plotted as 1.0 when active, not -1.0 —
    matches scripts/build_daily_bias.py (the code that actually runs). The
    h4-chart-scanner / daily-chart-scanner SKILL.md files say -1.0 and are wrong.
    """
    for study in (entry.get("indicators") or {}).get("studies", []) or []:
        if str(study.get("name", "")).startswith("TATbyBinniOngv2"):
            values = study.get("values", {}) or {}
            up = float(values.get("Up Trend", 0) or 0)
            down = float(values.get("Down Trend", 0) or 0)
            if up == 1.0:
                return "bullish"
            if down == 1.0:
                return "bearish"
            return "neutral"
    return "neutral"


def ema_values(entry):
    """Fast EMA (20/21) from the chart's own study values, when one is plotted."""
    for study in (entry.get("indicators") or {}).get("studies", []) or []:
        name = str(study.get("name", ""))
        if "EMA" not in name.upper() and "Moving Average" not in name:
            continue
        for key, val in (study.get("values", {}) or {}).items():
            if re.search(r"\b(20|21)\b", str(key)):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None


def ema_from_bars(bars, period=20, upto_dt=None):
    """EMA of 4H closes, computed locally.

    The live charts carry no EMA study, so reading one off the chart returns None
    and the 1+1 factor could never score. The mentor's own set is 20/34/55
    ("I'm using 20, 34, 55" — raw/AHH Sessions/2026-07-08-taw-pro.md); 20 is the fast line the
    1+1 rule refers to. Computing it from the same Yahoo bars used elsewhere keeps
    the factor live without depending on the user's chart layout.
    """
    closes = [b["close"] for b in bars if upto_dt is None or b["dt"] <= upto_dt]
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def run_tv_pass(symbols, timeframe, timeout_ms=600000):
    """Scan `symbols` at `timeframe` via the tv brief CLI, inside the CDP lock.

    Follows the Batch TradingView Session Rule: one tv_session.sh start, the scan,
    one tv_session.sh stop. Returns {clean_symbol: entry}.
    """
    if not symbols:
        return {}

    rules = {
        "watchlist": list(symbols),
        "default_timeframe": str(timeframe),
        "default_layout": "1x1",
    }
    # The CLI refuses a rules path outside the MCP project dir, so the temp rules
    # file lives there (same convention as scratch/run_4h_brief.mjs's temp_*_rules.json).
    tmp_rules = MCP_DIR / f"h4val_rules_{timeframe}_{os.getpid()}.json"
    tmp_rules.write_text(json.dumps(rules), encoding="utf-8")

    dump = Path(tempfile.gettempdir()) / f"h4val_brief_{timeframe}_{os.getpid()}.json"
    cmd = (
        f"cd {MCP_DIR} && node src/cli/index.js brief "
        f"--timeout-ms {timeout_ms} -r ./{tmp_rules.name} > {dump}"
    )
    try:
        subprocess.run(["bash", "-c", cmd], check=True, timeout=timeout_ms / 1000 + 120)
        from scripts.build_daily_bias import load_brief_json
        data = load_brief_json(str(dump))
    except Exception as exc:
        print(f"  ⚠️  {timeframe} chart pass failed: {exc}", file=sys.stderr)
        return {}
    finally:
        for p in (tmp_rules, dump):
            try:
                os.unlink(p)
            except OSError:
                pass

    return {clean_symbol(e["symbol"]): e for e in data.get("symbols_scanned", []) if e.get("symbol")}


def tv_session(action):
    try:
        subprocess.run(
            ["bash", str(WIKI_ROOT / "scripts" / "tv_session.sh"), action],
            check=True, timeout=700,
        )
        return True
    except Exception as exc:
        print(f"  ⚠️  tv_session.sh {action} failed: {exc}", file=sys.stderr)
        return False


# --- Higher-timeframe permission (G3) ----------------------------------------

def load_daily_brief(target_date):
    """Daily bias map, with an explicit staleness age in days.

    Returns (map, source_date, age_days). The caller must treat a stale brief as
    UNVERIFIED rather than silently trusting it — build_daily_bias.py's own
    docstring warns the fallback "can be days stale", and on this machine the
    directory has not been written since 2026-08-13.
    """
    want = DAILY_BRIEF_DIR / f"{target_date}.json"
    path = want
    if not path.exists():
        candidates = sorted(
            p for p in DAILY_BRIEF_DIR.glob("*.json") if not p.name.startswith("test")
        )
        if not candidates:
            return {}, None, None
        path = candidates[-1]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, None, None

    try:
        src = datetime.datetime.strptime(path.stem, "%Y-%m-%d").date()
        tgt = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
        age = (tgt - src).days
    except Exception:
        src, age = None, None

    return {clean_symbol(i["symbol"]): i for i in data if i.get("symbol")}, src, age


# --- Tier-0 hard gates -------------------------------------------------------

def gate_closed_bar(alert, ref_time):
    """G1 — the signal's 4H bar must have fully closed.

    "the four hour still hasn't closed yet and it still hasn't closed below the two
    lows... pending a closure" — raw/AHH Sessions/2026-08-25-ahh-access-time.md. A forming bar is
    PENDING, not a reject: the mentor waits it out rather than ruling it out.
    """
    start, close = signal_bar_window(alert["alert_dt"])
    closed = ref_time >= close
    return {
        "gate": "G1 Closed bar",
        "pass": closed,
        "pending": not closed,
        "detail": (
            f"signal bar {start:%d %b %H:%M}–{close:%H:%M} SGT "
            + ("closed" if closed else f"still forming (closes {close:%H:%M})")
        ),
        "bar_start": start,
        "bar_close": close,
    }


def gate_convincing_close(alert, bar, trigger_level, contemporaneous=True):
    """G2 — body close through the level, not a wick, not marginal.

    "Whatever you see, could be a solid bar at the end of the four hour, it can just
    be a long tail. Then it's as if like nothing happened" and "it actually doesn't
    filter how much above the red color line. Close" — raw/AHH Sessions/2026-08-26-ahh-access-time.md.
    """
    if bar is None:
        return {"gate": "G2 Convincing close", "pass": False, "detail": "no 4H bar data available"}
    if trigger_level is None:
        return {
            "gate": "G2 Convincing close",
            "pass": False,
            "detail": "no TAT level found on the broken side — cannot measure the close",
        }

    bull = alert["direction"] == "Bullish"
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return {"gate": "G2 Convincing close", "pass": False, "detail": "degenerate bar (zero range)"}

    lvl = trigger_level["price"]
    beyond = (bar["close"] - lvl) if bull else (lvl - bar["close"])
    excursion = beyond / rng
    close_pos = (bar["close"] - bar["low"]) / rng
    if not bull:
        close_pos = 1.0 - close_pos

    # The bar must actually have traded through the level. If the level sits outside
    # the bar's range the break happened earlier and this is a continuation print,
    # not a breakout close. Only enforced when the labels are contemporaneous with
    # the signal (a same-day run) — on a historical replay the live labels postdate
    # the signal and may have moved, so it degrades to a flag.
    crossed = bar["low"] <= lvl <= bar["high"]

    checks = {
        "closed through": beyond > 0,
        "excursion": excursion >= MIN_EXCURSION_FRAC,
        "body not wick": close_pos >= MIN_CLOSE_POS,
    }
    if contemporaneous:
        checks["broke on this bar"] = crossed

    ok = all(checks.values())
    fails = [k for k, v in checks.items() if not v]
    result = {
        "gate": "G2 Convincing close",
        "pass": ok,
        "detail": (
            f"close {bar['close']:.5f} vs level {lvl:.5f} — "
            f"excursion {excursion * 100:.0f}% of range (need {MIN_EXCURSION_FRAC * 100:.0f}%), "
            f"close at {close_pos * 100:.0f}% of range (need {MIN_CLOSE_POS * 100:.0f}%)"
            + ("" if ok else f" — FAILED: {', '.join(fails)}")
        ),
        "excursion": excursion,
        "close_pos": close_pos,
        "crossed": crossed,
    }
    if not contemporaneous and not crossed:
        result["flag"] = "LEVEL DRIFT"
        result["detail"] += " — level sits outside the signal bar (labels read after the fact)"
    return result


def gate_htf_permission(alert, daily_entry, brief_age, weekly_bias=None):
    """G3 — Daily/Weekly must not oppose.

    "if in the day and the week is ambiguous to me, then I probably wouldn't"
    — raw/AHH Sessions/2026-07-20-ahh-session.md.
    """
    want = "bullish" if alert["direction"] == "Bullish" else "bearish"
    opposite = "bearish" if want == "bullish" else "bullish"

    if weekly_bias and weekly_bias == opposite:
        return {
            "gate": "G3 HTF permission",
            "pass": False,
            "detail": f"Weekly bias {weekly_bias} opposes the {alert['direction']} 4H signal",
        }

    if not daily_entry:
        return {
            "gate": "G3 HTF permission",
            "pass": True,
            "flag": "UNVERIFIED",
            "detail": "no Daily bias available — HTF permission unverified, score capped",
        }

    if brief_age is not None and brief_age > DAILY_BRIEF_MAX_AGE_DAYS:
        return {
            "gate": "G3 HTF permission",
            "pass": True,
            "flag": "UNVERIFIED",
            "detail": (
                f"Daily brief is {brief_age}d stale (>{DAILY_BRIEF_MAX_AGE_DAYS}d) — "
                "treated as unverified, score capped"
            ),
        }

    bias = (daily_entry.get("bias") or "neutral").lower()
    structure = daily_entry.get("structure", "?")
    if bias == opposite:
        return {
            "gate": "G3 HTF permission",
            "pass": False,
            "detail": f"Daily bias {bias} opposes the {alert['direction']} 4H signal (structure {structure})",
        }
    if bias == "neutral":
        return {
            "gate": "G3 HTF permission",
            "pass": True,
            "flag": "AMBIGUOUS",
            "detail": f"Daily bias neutral (structure {structure}) — permitted but capped at ⭐",
        }
    return {
        "gate": "G3 HTF permission",
        "pass": True,
        "detail": f"Daily bias {bias} agrees (structure {structure})",
    }


def gate_room_to_target(alert, trigger_level, target_level, price=None):
    """G4 — at most 50% of the leg to the next opposing level may already be gone.

    "maybe 50% of the distance already chopped off" — raw/AHH Sessions/2026-07-22-ahh-access-time.md.
    The mirror case is a bonus: "the gap is very, very wide between this H4 levels
    until the next support very far" — raw/AHH Sessions/2026-09-02-ahh-access-time.md.
    """
    if trigger_level is None:
        return {"gate": "G4 Room to target", "pass": False, "detail": "no reference level to measure the leg from"}
    if target_level is None:
        return {
            "gate": "G4 Room to target",
            "pass": True,
            "flag": "OPEN RUN",
            "detail": "no opposing TAT level ahead — open road, full room",
            "consumed": 0.0,
        }

    price = alert["signal_price"] if price is None else price
    leg = abs(target_level["price"] - trigger_level["price"])
    if leg <= 0:
        return {"gate": "G4 Room to target", "pass": False, "detail": "degenerate leg (levels coincide)"}

    consumed = abs(price - trigger_level["price"]) / leg
    ok = consumed <= MAX_ROOM_CONSUMED
    return {
        "gate": "G4 Room to target",
        "pass": ok,
        "detail": (
            f"{consumed * 100:.0f}% of the leg {trigger_level['price']:.5f}→{target_level['price']:.5f} "
            f"already consumed at signal (limit {MAX_ROOM_CONSUMED * 100:.0f}%)"
        ),
        "consumed": consumed,
    }


def gate_break_of_structure(alert, bar, swings):
    """G6 — the signal must go WITH the 4H structure, or have broken it.

    Per wiki/concepts/market-structure.md a trend "remains structurally intact" until
    price closes past its latest Lower High (downtrend) / Higher Low (uptrend). So a
    bull signal is valid only if the 4H is already an uptrend (HH + HL), or the
    signal bar closed above the latest swing high — the break of structure. The
    transcripts say the same: "This horizontal support are still not broken yet.
    That means I don't have a break of structure yet... So I need to see a break of
    structure" — raw/AHH Sessions/2026-08-05-ahh-access-time.md.
    """
    gate = "G6 Break of structure"
    if bar is None:
        return {"gate": gate, "pass": False, "detail": "no 4H bar data available"}

    bull = alert["direction"] == "Bullish"
    structure = structure_from_swings(swings)
    want = "Bullish" if bull else "Bearish"
    if structure == want:
        hi, lo = latest_swing(swings, "high"), latest_swing(swings, "low")
        return {
            "gate": gate, "pass": True, "structure": structure, "mode": "trend",
            "detail": f"with-trend — 4H {structure.lower()} structure intact "
                      f"(latest {hi['tag']} {hi['price']:.5f} / {lo['tag']} {lo['price']:.5f})",
        }

    ref = latest_swing(swings, "high" if bull else "low")
    if ref is None:
        return {"gate": gate, "pass": False, "structure": structure,
                "detail": "no 4H swing found in the lookback — structure unreadable"}

    name = ref["tag"] or ("swing high" if bull else "swing low")
    broke = bar["close"] > ref["price"] if bull else bar["close"] < ref["price"]
    if broke:
        return {
            "gate": gate, "pass": True, "structure": structure, "mode": "reversal",
            "detail": f"break of structure — close {bar['close']:.5f} "
                      f"{'above' if bull else 'below'} latest {name} {ref['price']:.5f} "
                      f"(4H structure was {structure.lower()})",
        }
    return {
        "gate": gate, "pass": False, "structure": structure,
        "detail": f"counter-structure — 4H is {structure.lower()} and the latest {name} "
                  f"{ref['price']:.5f} is unbroken (close {bar['close']:.5f})",
    }


def elbow_invalidation(alert, bar, bars, swings=None):
    """SL — the swing the elbow confirmed.

    "until that this low is broken, then the elbow will be made invalid"
    — raw/AHH Sessions/2026-07-14-ahh-access-time.md, and the Structure Breakdown Alert in
    wiki/concepts/market-structure.md (a close past the latest Higher Low /
    Lower High invalidates). Take the latest swing low (bull) / high (bear) or the
    signal bar's own extreme, whichever is further from entry.
    """
    if bar is None:
        return None
    bull = alert["direction"] == "Bullish"
    bar_extreme = bar["low"] if bull else bar["high"]
    sw = latest_swing(swings or [], "low" if bull else "high")
    swing = sw["price"] if sw else None
    if swing is None:
        idx = bar_index(bars, bar)
        window = bars[max(0, idx - 10):idx] if idx else []
        if window:
            swing = min(b["low"] for b in window) if bull else max(b["high"] for b in window)

    cands = [c for c in (bar_extreme, swing) if c is not None]
    if not cands:
        return None
    return min(cands) if bull else max(cands)


def gate_risk_reward(alert, target_level, sl, price=None):
    """G5 — R:R >= 1:1, the only explicit numeric floor in the corpus
    (raw/AHH Sessions/2026-08-12-ahh-access-time.md)."""
    if sl is None:
        return {"gate": "G5 R:R", "pass": False, "detail": "no invalidation swing found — cannot place a stop"}
    if target_level is None:
        return {
            "gate": "G5 R:R",
            "pass": True,
            "flag": "OPEN RUN",
            "detail": "no opposing level ahead — reward unbounded, R:R not computable",
            "rr": None,
        }

    entry = alert["signal_price"] if price is None else price
    bull = alert["direction"] == "Bullish"
    risk = (entry - sl) if bull else (sl - entry)
    reward = (target_level["price"] - entry) if bull else (entry - target_level["price"])

    if risk <= 0:
        return {"gate": "G5 R:R", "pass": False, "detail": f"stop {sl:.5f} is on the wrong side of entry {entry:.5f}"}
    if reward <= 0:
        return {"gate": "G5 R:R", "pass": False, "detail": "target is behind entry — no reward left"}

    rr = reward / risk
    return {
        "gate": "G5 R:R",
        "pass": rr >= MIN_RR,
        "detail": f"1:{rr:.2f} at signal price (entry {entry:.5f} / SL {sl:.5f} / TP {target_level['price']:.5f})",
        "rr": rr,
        "sl": sl,
        "tp": target_level["price"],
    }


# --- Tier-1 quality score ----------------------------------------------------

def cross_pair_consistency(alert, all_alerts):
    """Day A / B / C — do the driving currency's sibling pairs agree?

    "when I see this kind of scenario where only one Forex pair gets a signal with
    no very obvious consistency across the board... I will filter this fella out"
    — raw/AHH Sessions/2026-07-09-tar-session.md.
    """
    sym = alert["clean"]
    if sym in METALS or len(sym) != 6:
        return 0.5, "not a cross-pair (metals) — consistency not assessable"

    base, quote = sym[:3], sym[3:]
    bull = alert["direction"] == "Bullish"
    base_agree = quote_agree = False

    for other in all_alerts:
        osym = other["clean"]
        if osym == sym or len(osym) != 6:
            continue
        obull = other["direction"] == "Bullish"
        # base strong in this signal == base strong in the sibling
        if osym[:3] == base and obull == bull:
            base_agree = True
        if osym[3:] == base and obull != bull:
            base_agree = True
        if osym[3:] == quote and obull == bull:
            quote_agree = True
        if osym[:3] == quote and obull != bull:
            quote_agree = True

    if base_agree and quote_agree:
        return 1.0, f"Day A — both {base} and {quote} siblings confirm"
    if base_agree or quote_agree:
        return 0.5, f"Day B — only {base if base_agree else quote} siblings confirm"
    return 0.0, "Day C — lone ranger, no sibling pair confirms (front-runner until the next 4H bar)"


def score_tier1(alert, ctx):
    """0–10 quality score, applied only to signals that clear every hard gate."""
    rows = []

    tier = SIGNAL_TIER.get(alert["signal"], 0)
    rows.append(("Signal tier", tier, 2, f"`{alert['signal']}` — {alert['event']}"))

    # G6 already rejects counter-structure signals, so survivors are either
    # with-trend (the trend is confirmed) or a fresh break of structure (first
    # break, the new trend's 4 points not yet in place).
    structure = ctx.get("structure_4h", "Mixed")
    if ctx.get("structure_mode") == "trend":
        rows.append(("4H structure", 2, 2, f"with-trend — {structure} (HH+HL / LH+LL intact)"))
    else:
        rows.append(("4H structure", 1, 2,
                     f"fresh break of structure out of a {structure.lower()} 4H — new trend unconfirmed"))

    last_broken = ctx.get("last_level_behind")
    rows.append(("Last level broken", 1 if last_broken else 0, 1,
                 "nearest opposing 4H level is behind price" if last_broken
                 else "the last opposing 4H level is still unbroken"))

    wash = ctx.get("wash_ok")
    # Named for what it actually measures: the opening-bar break half of the rule.
    # The wash-line half needs data_get_pine_lines (agent-side MCP), not available here.
    rows.append(("Opening-bar break", 1 if wash else 0, 1, ctx.get("wash_detail", "not confirmed")))

    ema_ok = ctx.get("ema_ok")
    rows.append(("1+1 (20/21 EMA)", 1 if ema_ok else 0, 1, ctx.get("ema_detail", "EMA not available")))

    conf = ctx.get("mtf_confluence")
    rows.append(("Multi-TF level confluence", 1 if conf else 0, 1,
                 ctx.get("confluence_detail", "no D/H1 level near the broken 4H level")))

    xp, xp_detail = ctx.get("xpair", (0.0, ""))
    rows.append(("Cross-pair consistency", xp, 1, xp_detail))

    rr = ctx.get("rr")
    rr_pts = 1 if (rr is not None and rr >= 3.0) else 0
    rows.append(("R:R ≥ 3:1", rr_pts, 1, f"1:{rr:.2f}" if rr is not None else "open run"))

    total = sum(r[1] for r in rows)

    # HTF ambiguity caps the score at the ⭐ band regardless of the other factors —
    # the mentor stands down when the Daily is unclear, whatever the setup looks like.
    cap_note = None
    if ctx.get("htf_flag") in ("AMBIGUOUS", "UNVERIFIED"):
        if total > 4.5:
            cap_note = f"capped from {total:.1f} — HTF {ctx['htf_flag']}"
            total = 4.5

    return total, rows, cap_note


def score_band(score):
    if score >= 8:
        return "⭐⭐⭐", "Take"
    if score >= 5:
        return "⭐⭐", "Take reduced size / require retest"
    if score >= 3:
        return "⭐", "Watch only"
    return "—", "Skip"


# --- Per-signal evaluation ---------------------------------------------------

def risk_scale_position(price, lower, upper, bull):
    """Bini's 1-to-10 scale: 1 = support bottom, 10 = resistance top."""
    if lower is None or upper is None or upper <= lower:
        return None
    frac = (price - lower) / (upper - lower)
    frac = max(0.0, min(1.0, frac))
    pos = 1 + frac * 9
    return pos if bull else 11 - pos


def evaluate_alert(alert, chart4h, chartd1, daily_map, brief_age, all_alerts, ref_time,
                   contemporaneous=True):
    bull = alert["direction"] == "Bullish"
    sym = alert["clean"]
    price = alert["signal_price"]

    entry4h = chart4h.get(sym, {})
    bars = aggregate_4h_bars(fetch_1h_bars(alert["symbol"], "30d"))
    g1 = gate_closed_bar(alert, ref_time)
    bar = find_bar(bars, g1["bar_start"])

    # Guard against the symbol-switch race: TradingView can report a symbol's name
    # while still serving the previous symbol's labels and quote. Cross-check the
    # chart's quote against the independent Yahoo close; if they disagree by more
    # than 3%, the chart data belongs to another instrument and must not be used.
    chart_mismatch = None
    chart_px = reference_price(entry4h)
    yahoo_px = bars[-1]["close"] if bars else None
    if entry4h and chart_px and yahoo_px and abs(chart_px - yahoo_px) / yahoo_px > 0.03:
        chart_mismatch = f"chart quote {chart_px:g} vs market {yahoo_px:g} — chart served another symbol"
        entry4h = {}

    levels = parse_tat_levels(entry4h, ref=yahoo_px)
    idx = bar_index(bars, bar)
    swings = find_swings(bars, idx) if idx is not None else []

    # Anchor level selection on the signal bar's CLOSE, not the sheet's "Signal
    # Price". The sheet reports the price of the TAT level itself, which can sit
    # well away from where the bar actually closed (GBPUSD 2026-09-19: sheet 1.34284
    # vs bar close 1.33946). G2 asks whether the bar CLOSED through a level, so the
    # close is the only correct anchor.
    price = bar["close"] if bar else alert["signal_price"]

    # The level the signal broke sits at or behind price; the next opposing level is
    # strictly ahead of it.
    trigger_level = triggering_level(levels, price, bull, bar)
    eps = abs(price) * 0.0005
    if bull:
        ahead = [lv for lv in levels if lv["price"] > price + eps]
        target_level = min(ahead, key=lambda lv: lv["price"]) if ahead else None
    else:
        ahead = [lv for lv in levels if lv["price"] < price - eps]
        target_level = max(ahead, key=lambda lv: lv["price"]) if ahead else None

    # A `TP :` label, when present and on the correct side, is the chart's own target.
    tp_labels = [lv for lv in levels if lv["kind"] == "TP"]
    for tp in tp_labels:
        if bull and tp["price"] > price and (target_level is None or tp["price"] < target_level["price"]):
            target_level = tp
        if not bull and tp["price"] < price and (target_level is None or tp["price"] > target_level["price"]):
            target_level = tp

    daily_entry = daily_map.get(sym)
    g2 = gate_convincing_close(alert, bar, trigger_level, contemporaneous)
    if chart_mismatch:
        g2 = {"gate": "G2 Convincing close", "pass": False,
              "detail": f"chart data rejected ({chart_mismatch}) — re-run for this symbol"}
    g3 = gate_htf_permission(alert, daily_entry, brief_age)
    g4 = gate_room_to_target(alert, trigger_level, target_level, price)
    sl = elbow_invalidation(alert, bar, bars, swings)
    g5 = gate_risk_reward(alert, target_level, sl, price)
    g6 = gate_break_of_structure(alert, bar, swings)

    gates = [g1, g2, g3, g4, g5, g6]

    if g1.get("pending"):
        verdict = "PENDING CLOSE"
    elif all(g.get("pass") for g in gates):
        verdict = "VALID"
    else:
        verdict = "REJECT"

    result = {
        "alert": alert,
        "gates": gates,
        "verdict": verdict,
        "bar": bar,
        "levels": levels,
        "trigger_level": trigger_level,
        "target_level": target_level,
        "sl": sl,
        "rr": g5.get("rr"),
        "failed": [g["gate"] for g in gates if not g.get("pass")],
        "flags": [g["flag"] for g in gates if g.get("flag")],
    }

    if verdict != "VALID":
        return result

    # --- Tier-1 context ---
    ema = ema_values(entry4h)
    ema_src = "chart study"
    if ema is None and bar is not None:
        ema = ema_from_bars(bars, 20, upto_dt=bar["dt"])
        ema_src = "EMA20 computed from 4H closes"
    ema_ok = None
    ema_detail = "no EMA available"
    if ema is not None and bar is not None:
        ema_ok = bar["close"] > ema if bull else bar["close"] < ema
        side = "above" if bull else "below"
        wrong = "below" if bull else "above"
        ema_detail = (
            f"close {bar['close']:.5f} {side if ema_ok else wrong} EMA {ema:.5f} ({ema_src})"
        )

    # Opening-bar + wash-line confirmation: the day's first 4H bar, then a later bar
    # closing beyond its extreme ("H4 close above opening bar high").
    wash_ok, wash_detail = False, "no opening-bar break confirmed"
    if bar is not None:
        day_bars = [b for b in bars if b["dt"].date() == g1["bar_start"].date()]
        if day_bars:
            opening = day_bars[0]
            if opening["dt"] != bar["dt"]:
                broke = bar["close"] > opening["high"] if bull else bar["close"] < opening["low"]
                wash_ok = broke
                wash_detail = (
                    f"4H close {bar['close']:.5f} {'above' if bull else 'below'} opening-bar "
                    f"{'high' if bull else 'low'} {opening['high'] if bull else opening['low']:.5f}"
                    if broke else "signal bar did not clear the opening bar's extreme"
                )
            else:
                wash_detail = "signal bar IS the day's opening bar — no prior extreme to clear"

    # Multi-timeframe level confluence: a D1 level near the broken 4H level.
    confluence, confluence_detail = False, "no Daily level near the broken 4H level"
    if trigger_level and chartd1.get(sym):
        d1_levels = parse_tat_levels(chartd1[sym], ref=price)
        tol = abs(trigger_level["price"]) * 0.0015  # ~15 pips on a 1.0000 pair
        near = [lv for lv in d1_levels if abs(lv["price"] - trigger_level["price"]) <= tol]
        if near:
            confluence = True
            confluence_detail = (
                f"Daily {near[0]['kind']} at {near[0]['price']:.5f} stacks on the broken "
                f"4H level {trigger_level['price']:.5f}"
            )

    ctx = {
        "structure_4h": g6.get("structure", "Mixed"),
        "structure_mode": g6.get("mode"),
        "last_level_behind": trigger_level is not None,
        "wash_ok": wash_ok,
        "wash_detail": wash_detail,
        "ema_ok": ema_ok,
        "ema_detail": ema_detail,
        "mtf_confluence": confluence,
        "confluence_detail": confluence_detail,
        "xpair": cross_pair_consistency(alert, all_alerts),
        "rr": g5.get("rr"),
        "htf_flag": g3.get("flag"),
    }
    score, rows, cap_note = score_tier1(alert, ctx)
    stars, action = score_band(score)

    lower = trigger_level["price"] if bull else (target_level["price"] if target_level else None)
    upper = (target_level["price"] if target_level else None) if bull else trigger_level["price"]

    result.update({
        "score": score,
        "score_rows": rows,
        "cap_note": cap_note,
        "stars": stars,
        "action": action,
        "ctx": ctx,
        "risk_scale": risk_scale_position(price, lower, upper, bull),
    })
    return result


# --- Report rendering --------------------------------------------------------

def dir_tag(alert):
    return f"[[{alert['clean']}]] (🟢 Bull)" if alert["direction"] == "Bullish" else f"[[{alert['clean']}]] (🔴 Bear)"


def fmt(val, symbol):
    return format_price_precision(val, symbol) if val is not None else "N/A"


def render_scorecard(res):
    a = res["alert"]
    sym = a["clean"]
    bull = a["direction"] == "Bullish"
    out = [f"#### {res['stars']} {dir_tag(a)} — `{a['signal']}` @ {a['alert_dt']:%H:%M} SGT — **{res['score']:.1f}/10** · {res['action']}", ""]
    if res.get("cap_note"):
        out += [f"> ⚠️ {res['cap_note']}", ""]

    out += ["| Gate | Result | Detail |", "| :--- | :--- | :--- |"]
    for g in res["gates"]:
        mark = "✅" if g.get("pass") else "❌"
        if g.get("flag"):
            mark = f"⚠️ {g['flag']}"
        out.append(f"| {g['gate']} | {mark} | {g['detail']} |")
    out.append("")

    out += ["| Quality factor | Score | Basis |", "| :--- | :--- | :--- |"]
    for name, pts, maxp, detail in res["score_rows"]:
        out.append(f"| {name} | {pts:g} / {maxp} | {detail} |")
    out += ["", f"**Total: {res['score']:.1f} / 10 — {res['stars']} {res['action']}**", ""]

    tl, tgt = res["trigger_level"], res["target_level"]
    rs = res.get("risk_scale")
    out += [
        "**Execution plan** (chart-read — entry is on the retest, never the signal bar):",
        "",
        f"- **Entry** — wait for an H1/M15 retest of the broken 4H level at **{fmt(tl['price'] if tl else None, sym)}**. Do not enter at market on the signal bar.",
        f"- **SL** — elbow invalidation at **{fmt(res['sl'], sym)}** (a close beyond this voids the signal).",
        f"- **TP1** — next opposing 4H level at **{fmt(tgt['price'] if tgt else None, sym)}**" + (f" (`{tgt['text']}`)" if tgt else " — open run, trail instead") + ".",
        "- **TP2** — the next Daily level beyond TP1; clear level by level.",
        f"- **R:R at signal price** — {'1:%.2f' % res['rr'] if res.get('rr') else 'open run'}; the retest entry improves on this.",
    ]
    if rs is not None:
        out.append(f"- **Risk scale** — entry sits at **{rs:.1f}/10** ({'1 = support bottom' if bull else '1 = resistance top'}); 1–2 is optimal.")
    out += [
        "- **Size note** — reduce if an opposing 4H level sits in the path.",
        "",
        "**Chart-read narrative:** _pending_",
        "",
        "**Event risk:** _pending_",
        "",
    ]
    return out


def render_run(results, target_date, run_time, daily_src, brief_age, is_rerun):
    valid = [r for r in results if r["verdict"] == "VALID"]
    pending = [r for r in results if r["verdict"] == "PENDING CLOSE"]
    rejected = [r for r in results if r["verdict"] == "REJECT"]
    valid.sort(key=lambda r: r.get("score", 0), reverse=True)

    head = (f"## 🕒 Validation Re-Run — [{run_time:%H:%M} SGT]" if is_rerun
            else f"# 🎯 4H Forex Signal Validation — {target_date} [{run_time:%H:%M} SGT]")
    out = [head, ""]

    out += [
        f"**Scanned:** {len(results)} in-scope 4H alerts (FX pairs + metals) · "
        f"**Valid:** {len(valid)} · **Pending close:** {len(pending)} · **Rejected:** {len(rejected)}",
        "",
    ]

    if brief_age is None:
        out += ["> ⚠️ **No Daily bias available** — G3 (HTF permission) ran UNVERIFIED for every signal and all scores are capped at 4.5.", ""]
    elif brief_age > DAILY_BRIEF_MAX_AGE_DAYS:
        out += [f"> ⚠️ **Daily brief is {brief_age} days stale** (`{daily_src}.json`) — G3 ran UNVERIFIED and all scores are capped at 4.5. Re-run `build_daily_bias.py` for a real HTF gate.", ""]
    else:
        out += [f"_Daily bias source: `~/tradingview-mcp/daily_brief/{daily_src}.json` ({brief_age}d old)._", ""]

    out += ["---", "", f"### ✅ Validated Signals — {len(valid)}", ""]
    if not valid:
        out += ["_No signal cleared all five hard gates this run._", ""]
    else:
        for r in valid:
            out += render_scorecard(r)

    if pending:
        out += ["---", "", f"### ⏳ Pending 4H Close — {len(pending)}", "",
                "| Symbol | Signal | Fired | Bar closes |", "| :--- | :--- | :--- | :--- |"]
        for r in pending:
            a = r["alert"]
            out.append(f"| {dir_tag(a)} | `{a['signal']}` | {a['alert_dt']:%H:%M} | {r['gates'][0]['bar_close']:%H:%M} SGT |")
        out.append("")

    out += ["---", "", f"### ❌ Rejected — {len(rejected)}", ""]
    if not rejected:
        out += ["_Nothing rejected this run._", ""]
    else:
        out += ["| Symbol | Signal | Fired | Failed gates | Why |", "| :--- | :--- | :--- | :--- | :--- |"]
        for r in sorted(rejected, key=lambda r: r["alert"]["alert_dt"], reverse=True):
            a = r["alert"]
            failed = [g for g in r["gates"] if not g.get("pass")]
            names = ", ".join(f"**{g['gate']}**" for g in failed) or "?"
            why = "<br>".join(f"{g['gate'].split()[0]}: {g['detail']}" for g in failed)
            out.append(f"| {dir_tag(a)} | `{a['signal']}` | {a['alert_dt']:%H:%M} | {names} | {why} |")
        out.append("")

    out += ["---", "", f"### 📸 Chart Screenshots — [{run_time:%H:%M} SGT]", "",
            "_pending — capture via `tv_session.sh start` → `capture_tv_chart.sh <SYM> 4h` → `tv_session.sh stop`, then embed and verify at least one with Read._", ""]

    out += ["---", "", "**Technical Trading Rules Applied This Run:**", "",
            "1. A tail through a level is not a break — only a solid body close counts (G2).",
            "2. The TAT alert does not filter how far past the level it closed; G2 applies that filter manually.",
            "3. Daily/Weekly must give permission before a 4H signal is actionable (G3).",
            "4. If >50% of the leg to the next opposing level is already consumed, skip it (G4).",
            "5. Entry is on the retest, never the signal bar; SL is the elbow-invalidation swing.",
            "6. A trend stays intact until price closes past its latest swing — no break of structure, no counter-trend signal (G6).",
            ""]
    return out


def write_report(lines, target_date):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{target_date}-h4-forex-validation.md"
    body = "\n".join(lines) + "\n"
    if path.exists():
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n---\n\n" + body)
    else:
        path.write_text(body, encoding="utf-8")
    return path


# --- Outcome tracking --------------------------------------------------------

DEFAULT_WATCH_BARS = 30  # ~5 trading days of 4H bars


def load_watches():
    if not WATCH_FILE.exists():
        return {"config": {"default_watch_bars": DEFAULT_WATCH_BARS}, "watches": []}
    try:
        return json.loads(WATCH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"config": {"default_watch_bars": DEFAULT_WATCH_BARS}, "watches": []}


def save_watches(state):
    WATCH_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def watch_key(res):
    a = res["alert"]
    return f"{a['clean']}|{a['signal']}|{a['alert_dt'].isoformat()}"


def persist_watches(results, state):
    """Persist both VALID and REJECTED signals.

    Rejects are tracked but never entered: without them you can only measure how
    good the takes were, never whether the rejects were right to reject.
    """
    existing = {w["key"] for w in state["watches"]}
    added = 0
    for res in results:
        if res["verdict"] == "PENDING CLOSE":
            continue
        key = watch_key(res)
        if key in existing:
            continue
        a = res["alert"]
        tgt = res["target_level"]
        state["watches"].append({
            "key": key,
            "symbol": a["clean"],
            "tv_symbol": a["symbol"],
            "direction": a["direction"],
            "signal_name": a["signal"],
            "signal_time": a["alert_dt"].isoformat(),
            "signal_price": a["signal_price"],
            "verdict": res["verdict"],
            "rejected": res["verdict"] == "REJECT",
            "failed_gates": res["failed"],
            "score": res.get("score"),
            "stars": res.get("stars"),
            "entry_zone": res["trigger_level"]["price"] if res["trigger_level"] else None,
            "sl": res["sl"],
            "tp1": tgt["price"] if tgt else None,
            "rr_at_signal": res.get("rr"),
            "watch_bars": DEFAULT_WATCH_BARS,
            "bars_tracked": [],
            "outcome": "OPEN",
        })
        added += 1
    return added


def track_watches(state):
    """Advance every OPEN watch against closed 4H bars since its signal."""
    open_watches = [w for w in state["watches"] if w.get("outcome") == "OPEN"]
    if not open_watches:
        print("No open watches to advance.")
        return 0

    by_symbol = {}
    for w in open_watches:
        by_symbol.setdefault(w["tv_symbol"], []).append(w)

    closed = 0
    for tv_sym, watches in by_symbol.items():
        bars = aggregate_4h_bars(fetch_1h_bars(tv_sym, "60d"))
        if not bars:
            print(f"  ⚠️  {clean_symbol(tv_sym)}: no bar data, skipped")
            continue
        for w in watches:
            # Alerts land a minute or so past the boundary (e.g. 05:01), so compare
            # against the close of the signal bar, not the raw alert timestamp —
            # otherwise the first bar after the signal is skipped.
            sig_dt = datetime.datetime.fromisoformat(w["signal_time"])
            _, sig_close = signal_bar_window(sig_dt)
            after = [b for b in bars if b["dt"] >= sig_close]
            bull = w["direction"] == "Bullish"
            tracked = []
            outcome = "OPEN"
            for i, b in enumerate(after[: w.get("watch_bars", DEFAULT_WATCH_BARS)], start=1):
                note = ""
                if w.get("sl") is not None:
                    # Structure Breakdown Alert (wiki/concepts/market-structure.md):
                    # a CLOSE past the swing invalidates the trade idea. A wick
                    # through it still fills a resting stop, so it is a loss too,
                    # but recorded separately — it is the case a mental stop on
                    # the close would have survived.
                    closed_past = b["close"] <= w["sl"] if bull else b["close"] >= w["sl"]
                    wicked = b["low"] <= w["sl"] if bull else b["high"] >= w["sl"]
                    if closed_past:
                        outcome, note = "INVALIDATED", "4H close through the swing — structure broken"
                    elif wicked:
                        outcome, note = "SL_HIT", "wick took out the stop; close held"
                if outcome == "OPEN" and w.get("tp1") is not None:
                    hit_tp = b["high"] >= w["tp1"] if bull else b["low"] <= w["tp1"]
                    if hit_tp:
                        outcome, note = "TP1_HIT", "first target reached"
                tracked.append({
                    "bar": i,
                    "dt": b["dt"].isoformat(),
                    "close": b["close"],
                    "note": note,
                })
                if outcome != "OPEN":
                    break
            if outcome == "OPEN" and len(after) >= w.get("watch_bars", DEFAULT_WATCH_BARS):
                outcome = "EXPIRED"
            w["bars_tracked"] = tracked
            w["outcome"] = outcome
            if outcome != "OPEN":
                closed += 1
                print(f"  {clean_symbol(tv_sym):<8} {w['signal_name']:<8} → {outcome} after {len(tracked)} bars")
    return closed


def report_stats(state):
    """Hit-rate by score band — does the scorecard actually separate winners?"""
    done = [w for w in state["watches"]
            if w.get("outcome") in ("TP1_HIT", "SL_HIT", "INVALIDATED", "EXPIRED")]
    if not done:
        print("No resolved watches yet. Run --track after a few 4H bars have closed.")
        return

    def bucket(w):
        if w.get("rejected"):
            return "REJECTED (not taken)"
        s = w.get("score")
        if s is None:
            return "unscored"
        return score_band(s)[0]

    order = ["⭐⭐⭐", "⭐⭐", "⭐", "—", "unscored", "REJECTED (not taken)"]
    groups = {}
    for w in done:
        groups.setdefault(bucket(w), []).append(w)

    print(f"\n{'Band':<22} {'N':>4} {'TP1':>5} {'Inv':>4} {'Wick':>5} {'Exp':>4} {'Hit%':>7}")
    print("-" * 56)
    for band in order:
        ws = groups.get(band)
        if not ws:
            continue
        tp = sum(1 for w in ws if w["outcome"] == "TP1_HIT")
        inv = sum(1 for w in ws if w["outcome"] == "INVALIDATED")
        wick = sum(1 for w in ws if w["outcome"] == "SL_HIT")
        ex = sum(1 for w in ws if w["outcome"] == "EXPIRED")
        decided = tp + inv + wick
        rate = f"{tp / decided * 100:.0f}%" if decided else "n/a"
        print(f"{band:<22} {len(ws):>4} {tp:>5} {inv:>4} {wick:>5} {ex:>4} {rate:>7}")
    print()
    print("Inv = 4H close through the stop swing; Wick = stop filled but the close held.")
    print("A band ranking that is not monotonic means the Tier-1 weights need")
    print("re-fitting — not that the signals are untradeable.")


# --- Entry point -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validate fired 4H TAT forex signals against the transcript doctrine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today SGT)")
    parser.add_argument("--symbol", default=None, help="Validate a single symbol only")
    parser.add_argument("--since", default=None, help="Only alerts at/after HH:MM SGT")
    parser.add_argument("--min-score", type=float, default=None, help="Only report signals scoring >= N")
    parser.add_argument("--no-watch", action="store_true", help="Do not persist watches")
    parser.add_argument("--no-chart", action="store_true", help="Skip the live TradingView pass (gates needing on-chart levels will fail)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of writing a report")
    parser.add_argument("--track", action="store_true", help="Advance open watches and exit")
    parser.add_argument("--stats", action="store_true", help="Print hit-rate by score band and exit")
    args = parser.parse_args()

    if args.track:
        state = load_watches()
        closed = track_watches(state)
        save_watches(state)
        print(f"\n✅ Tracking pass complete — {closed} watch(es) resolved. State: {WATCH_FILE}")
        return

    if args.stats:
        report_stats(load_watches())
        return

    run_time = now_sgt()
    target_date = args.date or run_time.strftime("%Y-%m-%d")

    print(f"🎯 4H Forex Signal Validation — {target_date} [{run_time:%H:%M} SGT]")
    alerts = load_h4_alerts(target_date, args.symbol, args.since)
    if not alerts:
        print(f"No in-scope 4H alerts for {target_date}.")
        return
    print(f"   {len(alerts)} in-scope alert(s) across {len({a['clean'] for a in alerts})} symbol(s)")

    daily_map, daily_src, brief_age = load_daily_brief(target_date)
    if brief_age is None:
        print("   ⚠️  No Daily bias available — G3 will run UNVERIFIED")
    elif brief_age > DAILY_BRIEF_MAX_AGE_DAYS:
        print(f"   ⚠️  Daily brief {daily_src} is {brief_age}d stale — G3 will run UNVERIFIED")

    # One TradingView session for the whole batch, scoped to the firing symbols only
    # (typically a handful, not the full 37-instrument watchlist).
    chart4h, chartd1 = {}, {}
    firing = sorted({a["symbol"] for a in alerts})
    if not args.no_chart:
        print(f"   Opening TradingView session for {len(firing)} symbol(s)...")
        if tv_session("start"):
            try:
                chart4h = run_tv_pass(firing, "240")
                print(f"   4H chart pass: {len(chart4h)}/{len(firing)} symbols")
                chartd1 = run_tv_pass(firing, "D")
                print(f"   D1 chart pass: {len(chartd1)}/{len(firing)} symbols")
            finally:
                tv_session("stop")
    else:
        print("   --no-chart: skipping the live TradingView pass")

    # On a same-day run the live pine labels are contemporaneous with the signal, so
    # G2 can enforce that the break happened on the signal bar. On a historical
    # replay they postdate it and may have moved, so that sub-check degrades to a flag.
    contemporaneous = (target_date == run_time.strftime("%Y-%m-%d"))
    results = [
        evaluate_alert(a, chart4h, chartd1, daily_map, brief_age, alerts, run_time,
                       contemporaneous)
        for a in alerts
    ]

    if args.min_score is not None:
        results = [
            r for r in results
            if r["verdict"] != "VALID" or (r.get("score") or 0) >= args.min_score
        ]

    if args.json:
        print(json.dumps([{
            "symbol": r["alert"]["clean"],
            "direction": r["alert"]["direction"],
            "signal": r["alert"]["signal"],
            "fired": r["alert"]["alert_dt"].isoformat(),
            "verdict": r["verdict"],
            "score": r.get("score"),
            "stars": r.get("stars"),
            "failed_gates": r["failed"],
            "rr": r.get("rr"),
            "sl": r["sl"],
            "tp1": r["target_level"]["price"] if r["target_level"] else None,
        } for r in results], indent=2))
        return

    is_rerun = (REPORT_DIR / f"{target_date}-h4-forex-validation.md").exists()
    lines = render_run(results, target_date, run_time, daily_src, brief_age, is_rerun)
    path = write_report(lines, target_date)

    if not args.no_watch:
        state = load_watches()
        added = persist_watches(results, state)
        save_watches(state)
        print(f"   {added} new watch(es) persisted to {WATCH_FILE.name}")

    valid = sum(1 for r in results if r["verdict"] == "VALID")
    pend = sum(1 for r in results if r["verdict"] == "PENDING CLOSE")
    rej = sum(1 for r in results if r["verdict"] == "REJECT")
    print(f"\n✅ {valid} valid · ⏳ {pend} pending · ❌ {rej} rejected")
    print(f"📄 {path}")
    print("\nNext: fill the _pending_ narrative cells, capture screenshots, and verify one with Read.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Daily Signals scanner — the data layer for the `daily-signal-tracker` skill (v3.0.0,
retitled "Daily Signals").

Pulls the three Daily-timeframe signal sources out of Binni's Google Sheet, normalizes
their two different schemas into one row shape, applies the 05:01 SGT date window
(Asian stocks offset one day back), dedupes, and emits JSON for the agent to screenshot
and report on.

Sources (see scripts/fetch_google_sheet.py GIDS):
    Forex              gid 462165474  tab "Forex D"     fires 05:00-05:01 SGT
    TradingView Stocks gid 520189562  tab "bats"        fires 04:01 SGT
    Yahoo Stocks       gid 1875176436 tab "Bull Daily"  + gid 1088333741 "Bear Daily"

Deliberately out of scope: Weekly state, 1H/4H confluence, multi-day watch tracking.
This is a once-daily snapshot. The pre-2026-09-23 watch machinery in
scripts/daily_signal_watches.json is frozen, not used here.

Usage:
    python3 scripts/scan_daily_signals.py --dry-run
    python3 scripts/scan_daily_signals.py --date 2026-09-23 --dry-run
    python3 scripts/scan_daily_signals.py --json
    python3 scripts/scan_daily_signals.py --json --commit        # updates the seen-set
    python3 scripts/scan_daily_signals.py --backfill-from 2026-09-21 --dry-run
"""

import sys
import json
import time
import contextlib
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records

SGT = timezone(timedelta(hours=8))
SEEN_FILE = Path(__file__).resolve().parent / "daily_signal_seen.json"
SEEN_RETENTION_DAYS = 45

# Broker prefixes seen on the Forex D tab for the same instrument. EIGHTCAP is the
# wiki's canonical quote source (CLAUDE.md "Continuous Trade Monitoring" protocol).
BROKER_PREFERENCE = ["EIGHTCAP", "FOREXCOM", "FUSIONMARKETS", "CXM", "BLACKBULL", "OANDA"]

SOURCES = [
    # (source key, report label, sheet tab key, schema)
    ("forex", "Forex", "FOREX_D", "tv"),
    ("tv_stocks", "TradingView Stocks", "BATS", "tv"),
    ("yahoo_stocks", "Yahoo Stocks", "BULL_DAILY", "yahoo"),
    ("yahoo_stocks", "Yahoo Stocks", "BEAR_DAILY", "yahoo"),
]


# ---------------------------------------------------------------- normalization

def normalize_date(raw):
    """Handle the sheet's mixed DD/MM/YYYY and YYYY-MM-DD formats in one column.

    Same logic as scan_stock_alerts.normalize_date; duplicated here so this script
    has no import-time dependency on that module's argparse/main path.
    """
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3:
            day, month, year = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            return f"{year}-{month}-{day}"
    return raw


def direction_from_signal(signal):
    """The Yahoo tabs carry no Direction column — derive it from the signal name."""
    sig = str(signal or "").upper()
    if "BULL" in sig:
        return "Bullish"
    if "BEAR" in sig:
        return "Bearish"
    return "Neutral"


def market_for_symbol(symbol):
    """Classify a raw sheet symbol into a market.

    Extends scan_stock_alerts.market_for_symbol with the bare-numeric case: the sheet
    intermittently drops the .HK suffix and Google coerces the ticker to an integer
    (823, 2706, 386), which the original mapper silently classified as US.
    """
    sym = str(symbol or "").strip().upper()
    if ":" in sym:
        prefix = sym.split(":", 1)[0]
        return "FX" if prefix not in ("BATS", "NASDAQ", "NYSE", "AMEX") else "US"
    if sym.endswith(".SI"):
        return "SGX"
    if sym.endswith(".HK"):
        return "HKEX"
    if sym.isdigit():
        return "HKEX"
    return "US"


def to_tv_symbol(symbol, market):
    """Resolve a raw sheet symbol to the exchange-qualified TradingView symbol.

    HKEX single stocks must use HKEX:<code> — the desktop app rejects HSI:<code>
    ("This symbol doesn't exist"); see equity-news-finder/SKILL.md.
    """
    sym = str(symbol or "").strip()
    if ":" in sym:
        return sym.upper()
    upper = sym.upper()
    if market == "SGX":
        return "SGX:" + upper[:-3]
    if market == "HKEX":
        code = upper[:-3] if upper.endswith(".HK") else upper
        code = code.lstrip("0") or "0"
        return "HKEX:" + code
    return upper


def image_slug(tv_symbol, market):
    """Filename stem for the Timestamped Image Naming Standard.

    Forex/US drop the prefix (gbpusd, chkp); SGX/HKEX keep the exchange so an SGX
    code can never collide with a US ticker (sgx_s71, hkex_823).
    """
    sym = tv_symbol.upper()
    code = sym.split(":", 1)[1] if ":" in sym else sym
    code = "".join(ch for ch in code if ch.isalnum()).lower()
    if market in ("SGX", "HKEX"):
        return f"{market.lower()}_{code}"
    return code


def is_asian(market):
    return market in ("SGX", "HKEX")


# ---------------------------------------------------------------- row building

def build_rows(source_key, source_label, tab_key, schema):
    records = fetch_sheet_records(tab_key)
    rows = []
    for r in records:
        if schema == "tv":
            date = normalize_date(r.get("Date"))
            symbol_raw = str(r.get("Symbol") or "").strip()
            signal = str(r.get("Signal Type") or "").strip()
            name = str(r.get("Name") or "").strip()
            direction = str(r.get("Direction") or "").strip() or direction_from_signal(signal)
            tm = str(r.get("Time") or "").strip()
            sector = ""
            sub_sector = ""
            event = str(r.get("Event") or "").strip()
        else:
            date = normalize_date(r.get("Date & Time"))
            symbol_raw = str(r.get("Yahoo Symbol") or "").strip()
            signal = str(r.get("Signal") or "").strip()
            name = str(r.get("Stock Name") or "").strip()
            direction = direction_from_signal(signal)
            tm = ""
            sector = str(r.get("Sector") or "Unclassified").strip() or "Unclassified"
            sub_sector = str(r.get("Sub-Sector") or "").strip()
            event = ""
        if not date or not symbol_raw or not signal:
            continue
        market = market_for_symbol(symbol_raw)
        tv = to_tv_symbol(symbol_raw, market)
        rows.append({
            "source": source_key,
            "source_label": source_label,
            "date": date,
            "time": tm,
            "symbol_raw": symbol_raw,
            "tv_symbol": tv,
            "instrument": tv.split(":", 1)[1] if ":" in tv else tv,
            "name": name,
            "direction": direction,
            "signal": signal,
            "price": r.get("Signal Price"),
            "sector": sector,
            "sub_sector": sub_sector,
            "event": event,
            "market": market,
            "subject": str(r.get("Subject") or "").strip(),
            "image_slug": image_slug(tv, market),
        })
    return rows


def dedupe(rows):
    """Collapse exact repeats and cross-broker prints of the same instrument.

    The sheet duplicates rows (a long-known bug, see wiki/hot.md), and the Forex tab
    carries the same pair from several brokers (EIGHTCAP:GBPCHF and
    FUSIONMARKETS:GBPCHF both printed 2026-09-23). One instrument, one chart.
    """
    best = {}
    for r in rows:
        key = (r["source"], r["date"], r["instrument"], r["signal"], r["direction"])
        prev = best.get(key)
        if prev is None:
            best[key] = r
            continue
        def rank(row):
            prefix = row["tv_symbol"].split(":", 1)[0] if ":" in row["tv_symbol"] else ""
            return BROKER_PREFERENCE.index(prefix) if prefix in BROKER_PREFERENCE else len(BROKER_PREFERENCE)
        if rank(r) < rank(prev):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r["source"], r["date"], r["instrument"]))


# ---------------------------------------------------------------- seen-set

def load_seen():
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except json.JSONDecodeError:
            print(f"❌ {SEEN_FILE} is not valid JSON — refusing to silently recreate it.", file=sys.stderr)
            sys.exit(1)
    return {"watermark": None, "last_run": None, "seen": []}


def seen_key(row):
    return f"{row['source']}|{row['date']}|{row['instrument']}|{row['signal']}"


def save_seen(state, rows, run_date):
    keys = set(state.get("seen", []))
    keys.update(seen_key(r) for r in rows)
    cutoff = (datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=SEEN_RETENTION_DAYS)).strftime("%Y-%m-%d")
    keys = {k for k in keys if k.split("|")[1] >= cutoff}
    state["seen"] = sorted(keys)
    state["watermark"] = run_date
    state["last_run"] = datetime.now(SGT).isoformat(timespec="seconds")
    SEEN_FILE.write_text(json.dumps(state, indent=2) + "\n")


# ---------------------------------------------------------------- windowing

def in_window(row, run_date, start_date):
    """Asian stocks close 17:00 SGT — after that day's 05:01 run — so their signals
    are first visible to the NEXT morning's run and sit one calendar day back."""
    d = row["date"]
    if is_asian(row["market"]):
        return shift(start_date, -1) <= d <= shift(run_date, -1)
    return start_date <= d <= run_date


def shift(date_str, days):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- main

def collect(run_date, start_date, forex_retry=False):
    rows = []
    for source_key, source_label, tab_key, schema in SOURCES:
        rows.extend(build_rows(source_key, source_label, tab_key, schema))
    rows = dedupe(rows)
    windowed = [r for r in rows if in_window(r, run_date, start_date)]

    # 05:01 race guard: Forex alerts write at 05:01:02-05:01:04, seconds after the run
    # starts. An empty Forex window this early means "not yet", not "nothing today".
    if forex_retry and not any(r["source"] == "forex" for r in windowed):
        now = datetime.now(SGT)
        if now.strftime("%Y-%m-%d") == run_date and now.hour == 5 and now.minute < 2:
            print("⏳ No Forex rows yet and it is before 05:02 SGT — waiting 90s for the alert write, then refetching once.", file=sys.stderr)
            time.sleep(90)
            return collect(run_date, start_date, forex_retry=False)
    return windowed


def capture_list(rows):
    """Unique charts to screenshot.

    An instrument can legitimately appear several times in one run: two signals on the
    same name (GEN OptBear + SBear), or the same ETF on both the bats tab and the Yahoo
    tabs (SOXS, XOP, YANG, BAI, BOTZ, QTUM, SOXL all printed on both 2026-09-23). The
    report keeps every row under its own source section, but they share one chart.
    """
    best = {}
    for r in rows:
        key = (r["market"], r["instrument"])
        prev = best.get(key)
        # Prefer the exchange-qualified form (BATS:SOXS) over the bare Yahoo ticker.
        if prev is None or (":" in r["tv_symbol"] and ":" not in prev["tv_symbol"]):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r["market"], r["instrument"]))


def main():
    parser = argparse.ArgumentParser(description="Daily Signals scanner (Forex D + bats + Bull/Bear Daily)")
    parser.add_argument("--date", help="Run date YYYY-MM-DD in SGT (default: today)")
    parser.add_argument("--backfill-from", help="Sweep from this date instead of the stored watermark")
    parser.add_argument("--dry-run", action="store_true", help="Print a summary only; never touch the seen-set")
    parser.add_argument("--json", action="store_true", help="Emit the full normalized rows as JSON")
    parser.add_argument("--commit", action="store_true", help="Record these rows in the seen-set")
    parser.add_argument("--all", action="store_true", help="Ignore the seen-set (show everything in the window)")
    parser.add_argument("--no-retry", action="store_true", help="Skip the 05:01 Forex race guard")
    parser.add_argument("--capture-list", action="store_true", help="Emit 'TV_SYMBOL IMAGE_SLUG' lines, one per unique chart to screenshot")
    args = parser.parse_args()

    run_date = args.date or datetime.now(SGT).strftime("%Y-%m-%d")
    state = load_seen()
    start_date = args.backfill_from or state.get("watermark") or run_date
    if start_date > run_date:
        start_date = run_date

    # fetch_sheet_records() chatters on stdout; that is diagnostic output, and it must
    # not contaminate --json or --capture-list payloads.
    with contextlib.redirect_stdout(sys.stderr):
        rows = collect(run_date, start_date, forex_retry=not args.no_retry)

    known = set() if args.all else set(state.get("seen", []))
    fresh = [r for r in rows if seen_key(r) not in known]

    if args.capture_list:
        for r in capture_list(fresh):
            print(f"{r['tv_symbol']} {r['image_slug']}")
        return

    if args.json:
        print(json.dumps({
            "run_date": run_date,
            "window_start": start_date,
            "asian_window": [shift(start_date, -1), shift(run_date, -1)],
            "total_in_window": len(rows),
            "new": len(fresh),
            "unique_charts": len(capture_list(fresh)),
            "rows": fresh,
            "captures": capture_list(fresh),
        }, indent=2))
    else:
        print("=" * 72)
        print(f"📅 Daily Signals — run date {run_date} (window from {start_date})")
        print(f"   Asian stocks window: {shift(start_date, -1)} .. {shift(run_date, -1)}")
        print("=" * 72)
        by_source = defaultdict(list)
        for r in fresh:
            by_source[r["source_label"]].append(r)
        for label in ("Forex", "TradingView Stocks", "Yahoo Stocks"):
            group = by_source.get(label, [])
            bulls = sum(1 for r in group if r["direction"] == "Bullish")
            bears = sum(1 for r in group if r["direction"] == "Bearish")
            print(f"\n## {label} — {len(group)} new ({bulls} Bull / {bears} Bear)")
            for r in sorted(group, key=lambda x: (x["direction"], x["instrument"])):
                arrow = "🟢" if r["direction"] == "Bullish" else "🔴"
                mkt = f" [{r['market']}]" if r["market"] not in ("FX",) else ""
                dt = f" {r['date']}" + (f" {r['time']}" if r["time"] else "")
                print(f"   {arrow} {r['tv_symbol']:<22} {r['signal']:<8} @ {r['price']}{mkt}{dt}")
        print(f"\nTotal in window: {len(rows)} | new this run: {len(fresh)} | unique charts to capture: {len(capture_list(fresh))}")

    if args.commit and not args.dry_run:
        save_seen(state, rows, run_date)
        print(f"\n💾 Seen-set updated: {len(state['seen'])} keys, watermark {run_date}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pulls Binni's Bull Daily / Bear Daily Stock Alert tabs (Google Sheet gids
1875176436 / 1088333741 — see scripts/fetch_google_sheet.py) and clusters
them by the Sector / Sub-Sector fields already tagged in the sheet itself,
rather than by currency-cross theme (which is what binni_alert_analysis.py's
existing clustering does for forex/metals/crypto).

Covers US (bare ticker, e.g. NVDA), SGX (.SI suffix, e.g. D05.SI), and HKEX
(.HK suffix, e.g. 0823.HK) equities and options in one pass, since the sheet
mixes all three under "Yahoo Symbol".

The sheet's own duplication bug (seen repeatedly on the H1/4H forex tabs —
see wiki/hot.md) is guarded against here too: rows are deduped on
(date, symbol, signal, price) before counting.

Usage:
    python3 scripts/scan_stock_alerts.py
    python3 scripts/scan_stock_alerts.py --date 2026-07-31
    python3 scripts/scan_stock_alerts.py --market sgx
"""

import sys
import argparse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_google_sheet import fetch_sheet_records


def normalize_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3:
            day, month, year = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            return f"{year}-{month}-{day}"
    return raw


def get_direction(signal):
    sig = (signal or "").upper()
    if "BULL" in sig:
        return "Bullish"
    if "BEAR" in sig:
        return "Bearish"
    return "Neutral"


def market_for_symbol(symbol):
    sym = (symbol or "").upper()
    if sym.endswith(".SI"):
        return "SGX"
    if sym.endswith(".HK"):
        return "HKEX"
    return "US"


def fetch_deduped(tab, bias_label):
    records = fetch_sheet_records(tab)
    seen = set()
    rows = []
    for r in records:
        date = normalize_date(r.get("Date & Time"))
        symbol = str(r.get("Yahoo Symbol") or "").strip()
        signal = str(r.get("Signal") or "").strip()
        price = r.get("Signal Price")
        if not date or not symbol or not signal:
            continue
        key = (date, symbol, signal, price)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "date": date,
            "symbol": symbol,
            "name": str(r.get("Stock Name") or "").strip(),
            "signal": signal,
            "price": price,
            "sector": str(r.get("Sector") or "Unclassified").strip() or "Unclassified",
            "sub_sector": str(r.get("Sub-Sector") or "").strip(),
            "subject": str(r.get("Subject") or "").strip(),
            "direction": get_direction(signal),
            "bias_tab": bias_label,
            "market": market_for_symbol(symbol),
        })
    return rows


def latest_date(rows):
    dates = sorted(set(r["date"] for r in rows), reverse=True)
    return dates[0] if dates else None


def main():
    parser = argparse.ArgumentParser(description="Binni's Bull/Bear Daily Stock Alert sector scan")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: latest date present)")
    parser.add_argument("--market", choices=["us", "sgx", "hkex", "all"], default="all",
                         help="Filter to one market (default: all)")
    args = parser.parse_args()

    bull_rows = fetch_deduped("BULL_DAILY", "Bull")
    bear_rows = fetch_deduped("BEAR_DAILY", "Bear")
    all_rows = bull_rows + bear_rows

    target_date = args.date or latest_date(all_rows)
    if not target_date:
        print("No stock alert data found.")
        return

    day_rows = [r for r in all_rows if r["date"] == target_date]
    if args.market != "all":
        market_name = {"us": "US", "sgx": "SGX", "hkex": "HKEX"}[args.market]
        day_rows = [r for r in day_rows if r["market"] == market_name]

    if not day_rows:
        print(f"No stock alerts found for {target_date} (market={args.market}).")
        return

    bullish = [r for r in day_rows if r["direction"] == "Bullish"]
    bearish = [r for r in day_rows if r["direction"] == "Bearish"]
    total = len(day_rows)
    bull_pct = 100 * len(bullish) / total if total else 0

    print(f"# Stock Alert Sector Scan — {target_date}")
    print()
    sentiment = "Bullish" if len(bullish) >= len(bearish) else "Bearish"
    print(f"**Overall sentiment**: {sentiment} ({len(bullish)} Bullish vs {len(bearish)} Bearish out of {total} total, {bull_pct:.1f}% Bullish)")
    print()

    by_sector = defaultdict(list)
    for r in day_rows:
        by_sector[r["sector"]].append(r)

    print("## Sector Breakdown")
    print()
    for sector in sorted(by_sector, key=lambda s: -len(by_sector[s])):
        rows = by_sector[sector]
        b = sum(1 for r in rows if r["direction"] == "Bullish")
        be = sum(1 for r in rows if r["direction"] == "Bearish")
        lean = "Bullish" if b > be else ("Bearish" if be > b else "Mixed")
        print(f"- **{sector}** ({len(rows)} alerts): {b} Bullish / {be} Bearish — leans {lean}")
        for r in rows:
            print(f"  - {r['direction']} `{r['signal']}` [[{r['symbol']}]] {r['name']} ({r['market']}, {r['sub_sector']}) @ {r['price']}")
    print()

    by_symbol = defaultdict(list)
    for r in day_rows:
        by_symbol[r["symbol"]].append(r)
    multi = {sym: rows for sym, rows in by_symbol.items() if len(rows) > 1}
    if multi:
        print("## Multi-Signal Symbols (Same-Day Double/Triple Confirmation)")
        print()
        for sym, rows in multi.items():
            signals = ", ".join(f"`{r['signal']}` ({r['direction']})" for r in rows)
            print(f"- [[{sym}]] {rows[0]['name']}: {signals}")
        print()


if __name__ == "__main__":
    main()

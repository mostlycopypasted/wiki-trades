#!/usr/bin/env python3
"""Render the current TAT signal state for a JSON watchlist as a markdown table.

Reads the per-symbol scan that generate_daily_brief.py already produces
(~/tradingview-mcp/daily_brief/{date}.json, written by build_daily_bias.py) and
filters it down to the instruments listed in a watchlist JSON file, preserving
the watchlist's own ordering.

IMPORTANT — this is a *snapshot*, not a fresh-signal feed. The TAT labels read by
the live scan carry only `text` and `price`, with no timestamp, so the `alert`
field is the last signal printed on the chart, whenever that happened. New Daily
signals are the Daily Signals skill's job (scripts/scan_daily_signals.py).

Usage:
    python3 scripts/watchlist_signals.py [--date YYYY-MM-DD] [--watchlist PATH]
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from binni_alert_analysis import normalize_symbol, get_direction_from_signal  # noqa: E402

BRIEF_DIR = Path.home() / "tradingview-mcp" / "daily_brief"
DEFAULT_WATCHLIST = Path.home() / "tradingview-mcp" / "forex_list.json"

DIRECTION_LABEL = {
    "Bullish": "🟢 Bull",
    "Bearish": "🔴 Bear",
    "Neutral": "⚪ Neutral",
}
NO_DATA_LABEL = "⚠️ No data"


def load_watchlist(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["watchlist"] if isinstance(data, dict) else data


def resolve_scan(date_str):
    """Return (records, date_used). Falls back to the newest scan on disk.

    generate_daily_brief.py skips build_daily_bias.py when the `tv brief` scan
    times out, so today's file can legitimately be absent. Falling back silently
    would present stale data as today's, hence date_used is reported back.
    """
    wanted = BRIEF_DIR / f"{date_str}.json"
    if wanted.exists():
        return json.loads(wanted.read_text(encoding="utf-8")), date_str
    available = sorted(BRIEF_DIR.glob("*.json"))
    if not available:
        return [], None
    newest = available[-1]
    return json.loads(newest.read_text(encoding="utf-8")), newest.stem


def build_table(watchlist, records, date_used, requested_date):
    by_symbol = {r["symbol"]: r for r in records}
    rows = []
    skipped = []
    counts = {"Bullish": 0, "Bearish": 0, "Neutral": 0}

    for raw in watchlist:
        entry = by_symbol.get(raw)
        # A symbol TradingView could not resolve still comes back in the scan, but
        # with a null quote — build_daily_bias.py then records price 0 and an empty
        # alert. Without the price check that lands in the table as a real-looking
        # "Squeeze / Neutral" row (this is what SGX:UMS did on 2026-09-23).
        if entry is None or not entry.get("price"):
            # Every watchlist instrument gets a row, so the table is a complete
            # picture of the list. A missing entry is an unresolvable ticker (typo)
            # or one the scan did not cover — shown as a gap, never dropped.
            skipped.append(raw)
            rows.append(
                f"| {len(rows) + 1} | [[{normalize_symbol(raw)}]] | `—` | "
                f"{NO_DATA_LABEL} | — | — | — |"
            )
            continue
        alert = (entry.get("alert") or "").strip()
        direction = get_direction_from_signal(alert) if alert else "Neutral"
        counts[direction] += 1
        rows.append(
            f"| {len(rows) + 1} | [[{normalize_symbol(raw)}]] | `{alert or '—'}` | "
            f"{DIRECTION_LABEL[direction]} | {entry.get('structure') or '—'} | "
            f"{(entry.get('bias') or '—').capitalize()} | `{entry.get('price')}` |"
        )

    out = []
    if not rows:
        return f"❌ No watchlist instruments found in the Daily scan for {requested_date}."

    if date_used != requested_date:
        out.append(
            f"⚠️ No Daily scan for {requested_date} — showing the most recent scan, **{date_used}**.\n"
        )
    tally = (f"**{counts['Bullish']} 🟢 Bull / {counts['Bearish']} 🔴 Bear / "
             f"{counts['Neutral']} ⚪ Neutral")
    if skipped:
        tally += f" / {len(skipped)} ⚠️ No data"
    out.append(f"{tally}** of {len(rows)} instruments (Daily scan {date_used}).\n")
    out.append("| # | Instrument | Signal | Direction | Structure | TAT Bias | Price |")
    out.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    out.extend(rows)
    if skipped:
        out.append(
            "\n⚠️ **No scan data for " + str(len(skipped)) + " watchlist "
            + ("entry" if len(skipped) == 1 else "entries") + ":** "
            + ", ".join(f"`{s}`" for s in skipped)
            + " — check for a typo or an unsupported ticker."
        )
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Watchlist TAT signal snapshot")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"),
                        help="Daily scan date to read (YYYY-MM-DD, default today)")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST),
                        help="Watchlist JSON file (default ~/tradingview-mcp/forex_list.json)")
    args = parser.parse_args()

    watchlist = load_watchlist(args.watchlist)
    records, date_used = resolve_scan(args.date)
    if date_used is None:
        print(f"❌ No Daily scan files found in {BRIEF_DIR}.")
        return
    print(build_table(watchlist, records, date_used, args.date))


if __name__ == "__main__":
    main()

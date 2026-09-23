#!/usr/bin/env python3
"""Render the Daily chart state for a JSON watchlist.

Reads the per-symbol scan that generate_daily_brief.py already produces
(~/tradingview-mcp/daily_brief/{date}.json, written by build_daily_bias.py) for
the instruments listed in a watchlist JSON file, preserving the watchlist's own
ordering.

Two output modes:
  --capture (used by the Daily Brief): batch-captures one Daily chart per
      instrument and emits a gallery of embedded screenshots.
  default: emits a markdown summary table instead, for ad hoc use.

IMPORTANT — the TAT labels read by the live scan carry only `text` and `price`,
with no timestamp, so the `alert` field is the last signal printed on the chart,
whenever that happened. New Daily signals are the Daily Signals skill's job
(scripts/scan_daily_signals.py).

Usage:
    python3 scripts/watchlist_signals.py [--date YYYY-MM-DD] [--watchlist PATH] [--capture]
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

WIKI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from binni_alert_analysis import normalize_symbol, get_direction_from_signal  # noqa: E402

BRIEF_DIR = Path.home() / "tradingview-mcp" / "daily_brief"
DEFAULT_WATCHLIST = Path.home() / "tradingview-mcp" / "forex_list.json"
IMAGE_DIR = WIKI_ROOT / "wiki" / "images"

DIRECTION_LABEL = {
    "Bullish": "🟢 Bull",
    "Bearish": "🔴 Bear",
    "Neutral": "⚪ Neutral",
}
DIRECTION_EMOJI = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "⚪"}
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


def build_entries(watchlist, records):
    """One entry per watchlist instrument, in watchlist order.

    A symbol TradingView could not resolve still comes back in the scan, but with
    a null quote — build_daily_bias.py then records price 0 and an empty alert.
    Without the price check that lands in the report as a real-looking
    "Squeeze / Neutral" row (this is what SGX:UMS did on 2026-09-23).
    """
    by_symbol = {r["symbol"]: r for r in records}
    entries = []
    for raw in watchlist:
        rec = by_symbol.get(raw)
        ok = rec is not None and bool(rec.get("price"))
        alert = (rec.get("alert") or "").strip() if rec else ""
        entries.append({
            "raw": raw,
            "ticker": normalize_symbol(raw),
            "has_data": ok,
            "alert": alert,
            "direction": get_direction_from_signal(alert) if (ok and alert) else "Neutral",
            "structure": rec.get("structure") if ok else None,
            "bias": rec.get("bias") if ok else None,
            "price": rec.get("price") if ok else None,
            "image": None,
        })
    return entries


def capture_charts(entries):
    """Batch-capture one Daily chart per instrument.

    Follows the Batch TradingView Session Rule: open the session once, capture
    every symbol inside it, close once — never one session per screenshot.
    """
    session = WIKI_ROOT / "scripts/tv_session.sh"
    capture = WIKI_ROOT / "scripts/capture_tv_chart.sh"
    targets = [e for e in entries if e["has_data"]]
    print(f"📸 Capturing {len(targets)} Daily charts in one TradingView session...", file=sys.stderr)

    subprocess.run(["bash", str(session), "start"], cwd=WIKI_ROOT, check=False)
    try:
        for n, e in enumerate(targets, 1):
            ts = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            name = f"{ts}_{e['ticker'].lower()}_D_chart"
            subprocess.run(["bash", str(capture), e["raw"], "D", name],
                           cwd=WIKI_ROOT, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Trust the file on disk, not the script's exit code: capture_tv_chart.sh
            # swallows a timed-out capture and still returns 0.
            if (IMAGE_DIR / f"{name}.png").exists():
                e["image"] = f"../../images/{name}.png"
            else:
                print(f"  ⚠️ no image for {e['ticker']}", file=sys.stderr)
            if n % 10 == 0:
                print(f"  …{n}/{len(targets)}", file=sys.stderr)
    finally:
        subprocess.run(["bash", str(session), "stop"], cwd=WIKI_ROOT, check=False)


def summary_line(entries, date_used, skipped):
    counts = {"Bullish": 0, "Bearish": 0, "Neutral": 0}
    for e in entries:
        if e["has_data"]:
            counts[e["direction"]] += 1
    tally = (f"**{counts['Bullish']} 🟢 Bull / {counts['Bearish']} 🔴 Bear / "
             f"{counts['Neutral']} ⚪ Neutral")
    if skipped:
        tally += f" / {len(skipped)} ⚠️ No data"
    return f"{tally}** of {len(entries)} instruments (Daily scan {date_used})."


def render_gallery(entries, date_used, skipped):
    out = [summary_line(entries, date_used, skipped), ""]
    missing = []
    for e in entries:
        if not e["has_data"]:
            continue
        # Headings and image alt text carry plain ticker text only — no wikilinks,
        # nested brackets or backticks (CommonMark/Obsidian break on them).
        out.append(f"### {DIRECTION_EMOJI[e['direction']]} {e['ticker']} — Daily")
        out.append("")
        out.append(
            f"[[{e['ticker']}]] ({DIRECTION_LABEL[e['direction']]}) · Signal `{e['alert'] or '—'}` · "
            f"Structure {e['structure'] or '—'} · TAT Bias {(e['bias'] or '—').capitalize()} · "
            f"Price `{e['price']}`"
        )
        out.append("")
        if e["image"]:
            out.append(f"![{e['ticker']} Daily Chart]({e['image']})")
        else:
            out.append("_Screenshot capture failed for this instrument._")
            missing.append(e["ticker"])
        out.append("")
    notes = []
    if skipped:
        notes.append(
            "⚠️ **No scan data for " + str(len(skipped)) + " watchlist "
            + ("entry" if len(skipped) == 1 else "entries") + ":** "
            + ", ".join(f"`{s}`" for s in skipped)
            + " — check for a typo or an unsupported ticker.")
    if missing:
        notes.append(
            "⚠️ **No screenshot captured for " + str(len(missing)) + ":** "
            + ", ".join(f"`{m}`" for m in missing) + ".")
    return "\n".join(out + notes)


def render_table(entries, date_used, skipped):
    out = [summary_line(entries, date_used, skipped), ""]
    out.append("| # | Instrument | Signal | Direction | Structure | TAT Bias | Price |")
    out.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for i, e in enumerate(entries, 1):
        if e["has_data"]:
            out.append(
                f"| {i} | [[{e['ticker']}]] | `{e['alert'] or '—'}` | {DIRECTION_LABEL[e['direction']]} | "
                f"{e['structure'] or '—'} | {(e['bias'] or '—').capitalize()} | `{e['price']}` |")
        else:
            out.append(f"| {i} | [[{e['ticker']}]] | `—` | {NO_DATA_LABEL} | — | — | — |")
    if skipped:
        out.append(
            "\n⚠️ **No scan data for " + str(len(skipped)) + " watchlist "
            + ("entry" if len(skipped) == 1 else "entries") + ":** "
            + ", ".join(f"`{s}`" for s in skipped)
            + " — check for a typo or an unsupported ticker.")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Watchlist Daily chart snapshot")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"),
                        help="Daily scan date to read (YYYY-MM-DD, default today)")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST),
                        help="Watchlist JSON file (default ~/tradingview-mcp/forex_list.json)")
    parser.add_argument("--capture", action="store_true",
                        help="Capture a Daily chart per instrument and emit an embedded gallery")
    args = parser.parse_args()

    watchlist = load_watchlist(args.watchlist)
    records, date_used = resolve_scan(args.date)
    if date_used is None:
        print(f"❌ No Daily scan files found in {BRIEF_DIR}.")
        return

    entries = build_entries(watchlist, records)
    skipped = [e["raw"] for e in entries if not e["has_data"]]
    if not entries:
        print(f"❌ No watchlist instruments found in the Daily scan for {args.date}.")
        return

    header = []
    if date_used != args.date:
        header.append(f"⚠️ No Daily scan for {args.date} — showing the most recent scan, **{date_used}**.\n")

    if args.capture:
        capture_charts(entries)
        body = render_gallery(entries, date_used, skipped)
    else:
        body = render_table(entries, date_used, skipped)
    print("\n".join(header + [body]))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Batch-capture one chart screenshot per symbol in a watchlist JSON file, at a
given timeframe, and emit a ready-to-paste markdown section.

Generic sibling to scripts/watchlist_signals.py: that script joins a watchlist
against the Daily Brief's Daily-only signal/bias scan and renders a gallery with
signal/structure/bias captions. This script has no signal/bias dependency — it
just captures a chart per watchlist symbol at --timeframe, for workflows (e.g.
the My-Watchlist 4H Screenshot Rule, see AGENTS.md) that need a plain screenshot
sweep of a watchlist rather than a signal-state gallery.

Usage:
    python3 scripts/capture_watchlist_charts.py --watchlist ~/tradingview-mcp/my_watchlist.json --timeframe 4H
    python3 scripts/capture_watchlist_charts.py --watchlist ~/tradingview-mcp/my_watchlist.json --timeframe 4H --heading "My-Watchlist 4H Chart Screenshots"
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

WIKI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from binni_alert_analysis import normalize_symbol  # noqa: E402

IMAGE_DIR = WIKI_ROOT / "wiki" / "images"


def load_watchlist(path):
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return data["watchlist"] if isinstance(data, dict) else data


def capture_charts(watchlist, timeframe):
    """Batch-capture one chart per watchlist symbol.

    Follows the Batch TradingView Session Rule: open the session once, capture
    every symbol inside it, close once — never one session per screenshot.
    """
    session = WIKI_ROOT / "scripts/tv_session.sh"
    capture = WIKI_ROOT / "scripts/capture_tv_chart.sh"
    results = []
    print(f"📸 Capturing {len(watchlist)} {timeframe} charts in one TradingView session...", file=sys.stderr)

    subprocess.run(["bash", str(session), "start"], cwd=WIKI_ROOT, check=False)
    try:
        for n, raw in enumerate(watchlist, 1):
            ticker = normalize_symbol(raw)
            ts = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            name = f"{ts}_{ticker.lower()}_{timeframe.lower()}_chart"
            subprocess.run(["bash", str(capture), raw, timeframe, name],
                           cwd=WIKI_ROOT, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Trust the file on disk, not the script's exit code: capture_tv_chart.sh
            # swallows a timed-out capture and still returns 0.
            image = f"../../images/{name}.png" if (IMAGE_DIR / f"{name}.png").exists() else None
            if image is None:
                print(f"  ⚠️ no image for {ticker}", file=sys.stderr)
            results.append({"raw": raw, "ticker": ticker, "image": image})
            if n % 10 == 0:
                print(f"  …{n}/{len(watchlist)}", file=sys.stderr)
    finally:
        subprocess.run(["bash", str(session), "stop"], cwd=WIKI_ROOT, check=False)
    return results


def render_section(results, timeframe, heading):
    captured = [r for r in results if r["image"]]
    missing = [r["ticker"] for r in results if not r["image"]]

    out = [f"## 📸 {heading}", ""]
    out.append(f"**{len(captured)} of {len(results)}** {timeframe} charts captured.")
    out.append("")
    for r in captured:
        # Plain ticker text only in alt text / headings — no wikilinks, nested
        # brackets, or backticks (CommonMark/Obsidian break on them).
        out.append(f"[[{r['ticker']}]] (see screenshot below)")
        out.append("")
        out.append(f"![{r['ticker']} {timeframe} Chart Screenshot]({r['image']})")
        out.append("")
    if missing:
        out.append(
            "⚠️ **No screenshot captured for " + str(len(missing)) + ":** "
            + ", ".join(f"`{m}`" for m in missing) + ".")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Batch-capture a chart screenshot per watchlist symbol")
    parser.add_argument("--watchlist", required=True,
                        help='Watchlist JSON file (a {"watchlist": [...]} object or a bare array)')
    parser.add_argument("--timeframe", required=True,
                        help="Timeframe to pass to capture_tv_chart.sh (e.g. 4H, 60, D)")
    parser.add_argument("--heading", default=None,
                        help="Section heading (default: '<Watchlist name> <Timeframe> Chart Screenshots')")
    args = parser.parse_args()

    watchlist = load_watchlist(args.watchlist)
    if not watchlist:
        print(f"❌ No symbols found in {args.watchlist}.")
        return

    heading = args.heading or f"{Path(args.watchlist).stem.replace('_', ' ').title()} {args.timeframe} Chart Screenshots"
    results = capture_charts(watchlist, args.timeframe)
    print(render_section(results, args.timeframe, heading))


if __name__ == "__main__":
    main()

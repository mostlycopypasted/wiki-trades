#!/usr/bin/env python3
"""Batch-capture new alert symbols for a specified timeframe.
Follows the Batch TradingView Session Rule:
Starts tv_session.sh once, captures charts sequentially, stops tv_session.sh once.

Usage:
    python3 scripts/batch_capture_alerts.py --timeframe 1H --symbols EURUSD GBPUSD ...
    python3 scripts/batch_capture_alerts.py --timeframe 4H --symbols EURUSD GBPUSD ...
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

WIKI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from binni_alert_analysis import normalize_symbol

IMAGE_DIR = WIKI_ROOT / "wiki" / "images"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", required=True, help="Timeframe (e.g. 1H, 4H)")
    parser.add_argument("--symbols", nargs="+", required=True, help="List of symbols")
    args = parser.parse_args()

    tf = args.timeframe
    session = WIKI_ROOT / "scripts/tv_session.sh"
    capture = WIKI_ROOT / "scripts/capture_tv_chart.sh"
    results = []

    print(f"🚀 Starting TradingView batch session for {len(args.symbols)} {tf} charts...", file=sys.stderr)
    subprocess.run(["bash", str(session), "start"], cwd=WIKI_ROOT, check=False)

    try:
        for n, raw in enumerate(args.symbols, 1):
            ticker = normalize_symbol(raw)
            ts = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            name = f"{ts}_{ticker.lower()}_{tf.lower()}_chart"
            subprocess.run(
                ["bash", str(capture), raw, tf, name],
                cwd=WIKI_ROOT,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            image_path = IMAGE_DIR / f"{name}.png"
            image_rel = f"../../images/{name}.png" if image_path.exists() else None
            if image_rel is None:
                print(f"  ⚠️ No image generated for {ticker}", file=sys.stderr)
            else:
                print(f"  ✅ [{n}/{len(args.symbols)}] Captured {ticker}: {name}.png", file=sys.stderr)
            results.append({"raw": raw, "ticker": ticker, "image": image_rel})
    finally:
        print(f"🛑 Stopping TradingView session for {tf} batch...", file=sys.stderr)
        subprocess.run(["bash", str(session), "stop"], cwd=WIKI_ROOT, check=False)

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()

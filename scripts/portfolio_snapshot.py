#!/usr/bin/env python3
"""Daily chart snapshot of the long-term portfolio.

Captures one Daily chart per holding in ~/tradingview-mcp/portfolio.json (one
batched TradingView session, via capture_watchlist_charts.py) and appends a
'## 🕒 [HH:MM SGT]' section to wiki/reports/portfolio/YYMMDD-portfolio.md
(one file per day; same-day reruns append). The dashboard's Portfolio tab reads
those files.

Scheduled by the com.chriseah.wikitrades.portfolio-snapshot launchd job
(Mon–Fri 19:15 SGT, after the SGX/HKEX 17:00 close and the 17:01 TAT run).
tv_session.sh's CDP lock makes it wait if another capture batch is running.

Usage:
    python3 scripts/portfolio_snapshot.py
    python3 scripts/portfolio_snapshot.py --timeframe W
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

WIKI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_watchlist_charts import capture_charts, load_watchlist, render_section  # noqa: E402

PORTFOLIO_JSON = Path.home() / "tradingview-mcp" / "portfolio.json"
REPORT_DIR = WIKI_ROOT / "wiki" / "reports" / "portfolio"
SGT = ZoneInfo("Asia/Singapore")


def main():
    parser = argparse.ArgumentParser(description="Daily chart snapshot of the portfolio")
    parser.add_argument("--portfolio", default=str(PORTFOLIO_JSON))
    parser.add_argument("--timeframe", default="D")
    args = parser.parse_args()

    watchlist = load_watchlist(args.portfolio)
    if not watchlist:
        print(f"❌ No symbols found in {args.portfolio}.")
        return 1

    results = capture_charts(watchlist, args.timeframe)
    section = render_section(results, args.timeframe, f"Portfolio {args.timeframe} Chart Screenshots")

    now = datetime.datetime.now(SGT)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{now:%y%m%d}-portfolio.md"
    head = "" if path.exists() else f"# 💼 Portfolio Daily Chart Snapshot — {now:%Y-%m-%d}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{head}\n## 🕒 [{now:%H:%M} SGT]\n\n{section}\n")

    captured = sum(1 for r in results if r["image"])
    missing = [r["ticker"] for r in results if not r["image"]]
    body = f"{captured} of {len(results)} {args.timeframe} charts captured → `{path.relative_to(WIKI_ROOT)}`."
    if missing:
        body += " Missing: " + ", ".join(missing) + "."
    subprocess.run([sys.executable, str(WIKI_ROOT / "scripts/append_log.py"), "--action", "report",
                    "--title", f"Portfolio {args.timeframe} chart snapshot {now:%H:%M} SGT", "--body", body],
                   cwd=WIKI_ROOT, check=False)
    print(body)
    return 0 if captured else 1


if __name__ == "__main__":
    sys.exit(main())

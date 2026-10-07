# Trading Desk dashboard

A local, read-only web dashboard over this wiki and the live TAT alert Google Sheet.

```bash
./dashboard/run.sh          # → http://127.0.0.1:8787
PORT=9000 ./dashboard/run.sh
```

No extra dependencies: it's stdlib Python plus `gspread` (already in `.venv`) for the alert sheet, using the
same service account as `scripts/fetch_google_sheet.py`. The page loads `marked` and `DOMPurify` from jsDelivr
to render markdown. It binds to localhost only and never writes to `wiki/` or `raw/`.

## Views

| View | Source |
| --- | --- |
| **Desk** | Overview: today's signal counts, next high-impact event, currency strength + trend, 14-day signal flow, latest TAT setups, upcoming events, suggested pairs / D-R-H-R, latest AHH ideas, central bank tally |
| **TAT Signals** | Live alert sheet (1H, 4H, Daily FX, TV Stocks, Yahoo Bull/Bear). Filter by range, source, direction, signal size, asset class, currency; signals-per-day chart, most-active instruments, multi-timeframe alignment matrix, sortable table |
| **Analysis** | `wiki/reports/tat_analysis/` runs per date: extracted ⭐⭐⭐ dual-alignment and retest setups, run-over-run diff table, full narrative (search terms highlighted); plus the Daily Signals executive summary |
| **Calendar** | `wiki/notes/economic-calendar.md` with impact/currency/date filters and countdowns; central bank tally and upcoming rate decisions |
| **AHH Ideas** | Trade ideas parsed from `wiki/AHH Session Notes/` (AHH Access Time, AHH Session, TAW Pro), grouped by session; most-discussed instruments, direction mix per session, and the trading-rules list |
| **Daily Brief** | Any `wiki/reports/daily_brief/` date: overview, events, currency strength, suggested pairs, news sentiment (with per-instrument summaries), 4H+1H synthesis, D-R-H-R, and the daily watchlist chart gallery |
| **My Watchlist** | Latest `## 📸 My-Watchlist 4H Chart Screenshots` section across `wiki/reports/tat_analysis/`: the 4H chart gallery for `~/tradingview-mcp/my_watchlist.json` (USD + JPY forex crosses + JPN225), captured by `scripts/capture_watchlist_charts.py` after each scheduled 4H run |
| **Journal** | `wiki/notes/journal/` trade entries (via `scripts/journal.py`): win rate, total R, equity curve, R by FOMO score / emotion / planned vs wiki-plan evidence / idea source / mistakes / hour, behaviour flags (revenge, overtrading, unplanned, no stop) and their R cost, trade table (click opens the entry), recent comments |

Click any instrument chip (or type a symbol in the search box and press Enter) to open its drawer: current
D/4H/1H signal state, daily-brief state, your journal trades in it, latest chart captures, TAT setups, AHH ideas, sentiment, upcoming
events for its currencies, and signal history. `/` focuses search; `Esc` closes overlays.

The alert sheet is cached for 5 minutes server-side; the page re-polls every minute and the ↻ button forces a
fresh pull and reloads the wiki data.

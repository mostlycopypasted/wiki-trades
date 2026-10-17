# Trading Desk dashboard

A local, read-only web dashboard over this wiki and the live TAT alert Google Sheet.

```bash
./dashboard/run.sh          # → http://127.0.0.1:8787
PORT=9000 ./dashboard/run.sh
```

No extra dependencies: it's stdlib Python plus `gspread` (already in `.venv`) for the alert sheet, using the
same service account as `scripts/fetch_google_sheet.py`. The page loads `marked` and `DOMPurify` from jsDelivr
to render markdown. It binds to localhost only and never writes to `wiki/` or `raw/`, except through the Journal
form (below); remote access goes through
Tailscale (below), which proxies to that localhost port.

## Remote access (Tailscale)

To open the desk from your phone or another machine, keep the Mac as the server and reach it over your private
Tailscale network. Nothing is exposed to the LAN or the internet, and only devices signed in to your tailnet can
connect. It's free, and no domain is needed.

1. Install Tailscale on the Mac (`brew install --cask tailscale` or the App Store) and on your phone, and sign in
   to the same account on both.
2. In the Tailscale admin console → **DNS**, enable **MagicDNS** and **HTTPS Certificates**.
3. With the dashboard running (it starts at login via the `com.chriseah.wikitrades.dashboard` LaunchAgent, see
   below), run once: `tailscale serve --bg 8787`. This persists
   across reboots. `tailscale serve status` shows the URL: `https://<mac-name>.<tailnet>.ts.net`.
4. Open that URL on your phone. In Safari, Share → *Add to Home Screen* gives it an app icon.

The Mac must be awake to serve. The scheduled automations already need that, but if it sleeps, set
System Settings → Energy → *Prevent automatic sleeping when the display is off*. Don't use `tailscale funnel`,
because that would make the dashboard public with no login. `tailscale serve reset` turns it off.

**Auto-start:** `~/Library/LaunchAgents/com.chriseah.wikitrades.dashboard.plist` runs `run.sh` at login and
restarts it if it crashes. Logs go to `~/Library/Logs/wiki-trades-dashboard{,.err}.log`. To stop it:
`launchctl bootout gui/$(id -u)/com.chriseah.wikitrades.dashboard`. The `tailscale serve` setting is saved by
Tailscale itself, so it needs no startup job; just leave the Tailscale app on *Launch at login*.

On screens under 820px the nav becomes a bottom tab bar, the instrument drawer goes full-screen, and the chart
lightbox can be swiped.

## Look

Terminal skin: black and amber, monospace, square panels with title bars, a live SGT clock with Tokyo/London/New York session lights, and a scrolling signal tape (currency strength plus the latest 40 bull/bear alerts, hover to pause). Keys `1`–`9` jump between views; in the command box type a view name (`cal`, `perf`, `wl`, `jnl`, `sig`, `brief`…) and press Enter, or a symbol to open its drawer. The ◐ button swaps to the light palette (same layout). The skin is the last block of `static/style.css`.

## Look

Terminal skin: black and amber, monospace, square panels with title bars, a live SGT clock with Tokyo/London/New York session lights, and a scrolling signal tape (currency strength plus the latest 40 bull/bear alerts, hover to pause). Keys `1`–`9` jump between views; in the command box type a view name (`cal`, `perf`, `wl`, `jnl`, `sig`, `brief`…) and press Enter, or a symbol to open its drawer. The ◐ button swaps to the light palette (same layout). The skin is the last block of `static/style.css`.

## Views

| View | Source |
| --- | --- |
| **Desk** | Overview: today's signal counts, next high-impact event, **News** card with two tabs, *Watchlist* (moomoo headlines for `scripts/equity_watchlist.json`) and *Latest* (market-wide moomoo headlines from the topic searches in `MARKET_TOPICS`, last 7 days, broker-rating and listing-notice noise filtered out), both via `dashboard/news.py`: 30-min cache, last good copy in `cache/news.json`, ↻ forces a re-pull, 24h/3d/7d/30d filter), currency strength + trend, 14-day signal flow, latest TAT setups, upcoming events, suggested pairs / D-R-H-R, latest AHH ideas, central bank tally |
| **TAT Signals** | Live alert sheet (1H, 4H, Daily FX, TV Stocks, Yahoo Bull/Bear). Filter by range, source, direction, signal size, asset class, currency; signals-per-day chart, most-active instruments, multi-timeframe alignment matrix, sortable table |
| **Analysis** | `wiki/reports/tat_analysis/` runs per date: extracted ⭐⭐⭐ dual-alignment and retest setups, run-over-run diff table, full narrative (search terms highlighted); plus the Daily Signals executive summary |
| **Calendar** | `wiki/notes/economic-calendar.md` with impact/currency/date filters and countdowns; central bank tally and upcoming rate decisions |
| **AHH Ideas** | Trade ideas parsed from `wiki/AHH Session Notes/` (AHH Access Time, AHH Session, TAW Pro), grouped by session; most-discussed instruments, direction mix per session, and the trading-rules list |
| **Daily Brief** | Any `wiki/reports/daily_brief/` date: overview, events, currency strength, suggested pairs, news sentiment (with per-instrument summaries), 4H+1H synthesis, D-R-H-R, and the daily watchlist chart gallery |
| **My Watchlist** | Latest run in `wiki/reports/my_watchlist/YYMMDD-my_watchlist.md` (where the Orca TAT automations file it), or a `My-Watchlist 4H Chart Screenshots` section in `wiki/reports/tat_analysis/` if that is newer: the 4H chart gallery for `~/tradingview-mcp/my_watchlist.json` (USD + JPY forex crosses + JPN225), captured by `scripts/capture_watchlist_charts.py` after each scheduled 4H run |
| **Journal** | `wiki/notes/journal/` trade entries (via `scripts/journal.py`). **＋ Log trade** opens a form for a new entry, and each row has 💬 (comment) and **Close** buttons. The server's `POST /api/journal/{new,comment,close}` runs `journal.py` itself, so the files, the `wiki/log.md` line and the Google Sheet sync are the same as from the terminal. Requests must carry an `X-Desk: 1` header, so other websites open in the browser can't post. Also shows win rate, total R, equity curve, R by FOMO score / emotion / planned vs wiki-plan evidence / idea source / mistakes / hour, behaviour flags (revenge, overtrading, unplanned, no stop) and their R cost, trade table (click opens the entry), recent comments |
| **Performance** | Live broker statement logs, read-only via the service account: AXI (`188-yOG1…`, tab `Statement Logs`) and Fusion (`1mX_2qAY…`, tab `Statement Logs`), parsed by `dashboard/statements.py` (15-min cache, ↻ forces a re-read; the last good copy is kept in `dashboard/cache/statements.json` so the tab still loads offline). Same metrics as the Fusion sheet's `Stats` tab (net P&L, win rate, profit factor, average/largest win and loss, drawdown, hold times, day-of-week and symbol tables), computed over every row, plus an equity curve, monthly P&L, P&L by hour, long vs short and asset class. Filter by account (All / AXI / Fusion) and range. Times are converted to SGT: AXI's MT4 server time is New York + 7h, Fusion's is UTC. Fusion rows with a repeated deal ID are counted once, and balance jumps no deal explains are treated as cash movements. AXI's "Data Truncation" balance rows are left out of the balance because the log already itemises that history. The equity curve and its drawdown use trading P&L only, so deposits and transfers don't distort them |

Click any instrument chip (or type a symbol in the search box and press Enter) to open its drawer: current
D/4H/1H signal state, daily-brief state, your journal trades in it, latest chart captures, TAT setups, AHH ideas, sentiment, upcoming
events for its currencies, and signal history. `/` focuses search; `Esc` closes overlays.

The alert sheet is cached for 5 minutes server-side; the page re-polls every minute and the ↻ button forces a
fresh pull and reloads the wiki data.

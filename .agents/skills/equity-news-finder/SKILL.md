---
name: equity-news-finder
description: Finds equity news — corporate actions, dividends, earnings, and general headlines — for two symbol sets: standout names from Binni's Bull/Bear Daily Stock Alert sheet (US, SGX, HKEX), and a user-maintained watchlist (scripts/equity_watchlist.json) of stocks tracked independent of that day's alerts. TradingView (tradingview.com/symbols/<CODE>/) is the primary source (covers all markets — a bare ticker/code reliably auto-resolves to the correct exchange-prefixed page for US, SGX, HKEX, and KRX names); minichart.com.sg and financialjuice.com supplement it for SGX and US names respectively. All web sources are reached via the ego-browser skill. The equities counterpart to tat-alert-analysis, which covers forex/metals/crypto.
license: MIT
metadata:
  author: AI Trading Team
  version: "2.2.0"
  tags:
    - google-sheets
    - alerts
    - stocks
    - sgx
    - hkex
    - us-equities
    - ego-browser
    - tradingview
    - minichart
    - financialjuice
    - news
    - watchlist
---

# Equity News Finder Skill

This skill (formerly `stock-alert-scanner`, renamed 2026-08-05 to reflect its real center of gravity) finds equity news for two symbol sets, not one:

1. **Standout alert names** — the sector-clustered read of Binni's **Bull Daily Stock Alerts** (`gid: 1875176436`) / **Bear Daily Stock Alerts** (`gid: 1088333741`) tabs on the same Google Sheet `tat-alert-analysis` uses for forex. These tabs mix US, SGX, and HKEX names under a single `Yahoo Symbol` column (`NVDA`, `D05.SI`, `0700.HK`, etc.) and already tag each row with `Sector` / `Sub-Sector`. This half answers "what's the market saying today."
2. **Watchlist names** — [scripts/equity_watchlist.json](file:///Users/chriseah/obsidian/wiki-trades/scripts/equity_watchlist.json), a small user-maintained list of stocks to check for news on **every run**, whether or not they fired an alert today. Managed with `scripts/manage_equity_watchlist.py` (add/remove/list). This half answers "what's happening with the names I actually hold or care about."

Both sets get the same news treatment: a primary TradingView pull (works uniformly across markets via bare-ticker auto-resolution), plus an optional supplemental deep-dive (minichart.com.sg for SGX, financialjuice.com for US).

---

## 📋 1. Data Sources

- **Google Sheet** (alert discovery): same sheet as `tat-alert-analysis` (`1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE`). `Bull Daily Stock Alerts` = `gid=1875176436`, `Bear Daily Stock Alerts` = `gid=1088333741`.
  - **Fetch/scan script**: [scripts/scan_stock_alerts.py](file:///Users/chriseah/obsidian/wiki-trades/scripts/scan_stock_alerts.py) — wraps `scripts/fetch_google_sheet.py`, dedupes on `(date, symbol, signal, price)` (the sheet has the same overlapping-page duplication bug documented for the H1/4H forex tabs in `wiki/hot.md`), and clusters by the sheet's native `Sector` field.
- **Watchlist** (user-maintained monitoring): [scripts/equity_watchlist.json](file:///Users/chriseah/obsidian/wiki-trades/scripts/equity_watchlist.json), managed via [scripts/manage_equity_watchlist.py](file:///Users/chriseah/obsidian/wiki-trades/scripts/manage_equity_watchlist.py):
  ```
  python3 scripts/manage_equity_watchlist.py list
  python3 scripts/manage_equity_watchlist.py add D05.SI --note "Core banking position"
  python3 scripts/manage_equity_watchlist.py remove D05.SI
  ```
  Symbols use the same ticker scheme as the sheet's own `Yahoo Symbol` column (bare ticker for US, `.SI` SGX, `.HK` HKEX, plus non-sheet markets like `.KS` KRX, `.T` TSE, `.L` LSE, `.AX` ASX) — kept as the storage format since it's the sheet's own convention; see the symbol-translation note below for turning it into a TradingView URL. Seeded 2026-08-05 with `000660.KS` (SK Hynix) — originally added as the seed case for the Stock Correction Discount Rule, retired 2026-09-02 when this skill switched off Yahoo Finance (TradingView has no 52-week-range equivalent); the symbol stays on the watchlist for ordinary news/price tracking.
- **Chart-screenshot watchlists** (unrelated to the equity watchlist above — these drive `capture_tv_chart.sh`, not news): `~/tradingview-mcp/us_stocks.json`, `~/tradingview-mcp/sghk_stocks.json`.
- **Primary news/quote source (all markets, switched from Yahoo Finance to TradingView 2026-09-02)**: [TradingView](https://www.tradingview.com/) via the `ego-browser` skill — no login wall on the pages this skill uses, but still needs a real browser session (heavy JS SPA). Spread across three sub-pages per symbol rather than Yahoo's single quote page:
  - **Symbol translation**: strip the Yahoo Symbol's market suffix (`.SI`, `.HK`, `.KS`) and any leading zeros from a purely-numeric code (e.g. `D05.SI` → `D05`, `0700.HK` → `700`, `000660.KS` → `000660`, `NVDA` stays `NVDA`), then visit `https://www.tradingview.com/symbols/<CODE>/`. TradingView's own bare-ticker resolution reliably redirects to the correct canonical exchange-prefixed URL (confirmed 2026-09-02 for US → `NASDAQ-`/`NYSE-` etc., SGX → `SGX-`, HKEX → `HKEX-`, KRX → `KRX-`) — no manual exchange lookup table needed. **Always read the resolved `pageInfo().url`/page title after navigation and confirm it names the expected company** — a bare numeric code can occasionally collide across markets (confirmed once: bare `0700` with the leading zero resolved to a Frankfurt-listed instrument, not Tencent HKEX:700; stripping the leading zero fixed it).
  - **Overview page** (`/symbols/<CODE>/`): last price + % change, and a "Key stats" panel — Market Cap, Dividend Yield (indicated), P/E (TTM), Basic EPS (TTM), Beta, and (when TradingView has a confirmed date, which isn't always) a "Next earnings report" countdown.
  - **Dividends page** (`/symbols/<CODE>/financials-dividends/`): "Next ex-dividend date" + "Next payment date" when a future dividend is scheduled and announced; falls back to "Last ex-dividend date" when it isn't yet.
  - **News page** (`/symbols/<CODE>/news/`): a **Latest headlines** table — timestamp, provider, headline — filterable by All/Earnings/Dividends/M&A/Analysts. A minority of articles (mostly Dow Jones Newswires) are gated behind "Start a free trial to read this" — the headline/provider/timestamp row itself is still visible even when the article body isn't.
  - **No 52-week range anywhere on TradingView** (checked Overview, Technicals, and the "highest/lowest prices ever" FAQ, which only gives *all-time* high/low, not a rolling 52-week window) — this is the one Yahoo Finance field with no TradingView equivalent, and is why the Stock Correction Discount Rule (formerly §3 of this skill) was retired rather than ported.
  - **Careful — two different TradingView symbol formats are both in play in this skill**: the desktop-app chart-symbol form used by `capture_tv_chart.sh`/the TradingView MCP tools (colon-separated, e.g. `SGX:D05`, `HKEX:700` for individual Hong Kong-listed stocks, `KRX:000660`, see §2 step 7) is **not** the same as the website URL-slug form used for this news/fundamentals pull (hyphen-separated, e.g. `SGX-D05`, `HKEX-700`). Note **`HKEX:`/`HKEX-`, not `HSI:`/`HSI-`**, for individual Hong Kong-listed stocks on *either* form — `HSI` (both website and desktop) is reserved for the Hang Seng Index itself and its sub-indices (`HSI:HSI`, `HSI:HSTECH`); the desktop app silently returns "This symbol doesn't exist" for any individual HK stock addressed as `HSI:<code>`, regardless of market cap (confirmed 2026-09-02/09-07/09-08 and again 2026-09-22, flagged those three times before this correction finally landed here — see `capture_tv_chart.sh <SYMBOL> D` in step 7 below and the Screenshot Verification Rule in `AGENTS.md`). Don't reuse one mapping for the other.
- **Supplemental deep-dive, SGX only**: [minichart.com.sg](https://www.minichart.com.sg/) via `ego-browser`. Sits behind an active Cloudflare bot challenge, so `WebFetch`/`curl` can't reach it either. Per-stock pages: `https://www.minichart.com.sg/stocks/sgx-<code>/` (lowercase, no `.SI` — e.g. `D05.SI` → `sgx-d05`). Adds analyst 1Y price target + upside/downside, broker call, and full dividend *history* (TradingView's dividends page only shows the next/last ex-dividend date, not history) beyond what TradingView gives.
- **Supplemental deep-dive, US only**: [financialjuice.com](https://www.financialjuice.com/) via `ego-browser`. No login wall on the headline feed, but it's a heavy JS SPA so still needs a real browser. Per-ticker pages: `https://www.financialjuice.com/<Exchange>/<TICKER>` (e.g. `financialjuice.com/Nasdaq/NVDA`) — reached by typing the ticker into the search box (`input[placeholder*="SEARCH"]`) and clicking the autocomplete suggestion (pressing Enter alone does not navigate). Adds faster, more granular squawk-style headlines (`$TICKER`-tagged, precise timestamps) than TradingView's periodic Latest headlines list — useful for same-day breaking news. Confirmed US-only in practice (a `DBS` search returns no match).

---

## ⚡ 2. Execution Protocol

0. **Clean up stale ego-browser task spaces before starting** (added 2026-08-23, root-cause fix): any interrupted run of this skill — a `claude -p` SIGKILL, a CDP hang, a session limit hit mid-run — aborts *before* reaching the `completeTaskSpace(..., { keep: false })` cleanup in step 5/6, since that's near the end of the workflow. These leaks compound silently across runs: a 2026-08-23 audit found 3 leaked task spaces dating back to 2026-08-20 holding **80 orphaned Chromium renderer processes**, which had driven the machine's free memory down to ~26MB and was the actual root cause of TradingView Desktop's CDP slowness/hangs during that whole period (not a TradingView-specific bug — TradingView's own CDP session was just the most visible victim of a system-wide resource-starved machine). Before step 1, run:
   ```js
   const spaces = await listTaskSpaces();
   for (const s of spaces) { await completeTaskSpace(s.id, { keep: false }); }
   ```
   This is safe unconditionally — any task space still open at the start of a new run is by definition leftover from a prior run that never finished cleanly, not live work.

1. **Run the sector scan** (alert-discovery half):
   ```
   python3 scripts/scan_stock_alerts.py
   ```
   - Defaults to the most recent date present in the sheet. Use `--date YYYY-MM-DD` to target a specific day, `--market {us|sgx|hkex}` to scope to one exchange.
   - Output: overall Bullish/Bearish sentiment and split, a per-sector breakdown sorted by alert count, and a "Multi-Signal Symbols" section flagging same-day double/triple confirmation.

2. **Identify the standout sector theme(s)** — the sector(s) with the most alerts AND a lopsided bullish/bearish split (e.g. this skill's first test run: 48 Technology/Semiconductor alerts, 100% Bullish). Don't just report raw counts; call out which sector is the actual story.

3. **Same-day iteration**: if a report already exists for today (`wiki/reports/equitynews/YYYY-MM-DD_equity-news-scan.md`), don't overwrite it — append a `## 🕒 Intraday Update Run — [HH:MM SGT]` section with a **Differences & Changes Highlights** table, same convention as the 1H TAT iteration rule in `CLAUDE.md`. Every append must also regenerate the Table of Contents block (see §4 item 1) to include the newly-appended section — find the existing `<!-- TOC:START -->...<!-- TOC:END -->` block and replace it with `Edit` (rebuilt from all `## ` headings now present, old and new) rather than reconstructing the whole file.

4. **Load the watchlist** (monitoring half):
   ```
   python3 scripts/manage_equity_watchlist.py list
   ```
   Every symbol here gets a TradingView pull (step 5) on every run, regardless of whether it appears in today's alert sheet.

5. **TradingView pull — for every standout alert symbol AND every watchlist symbol**:
   - Translate the symbol per §1 (strip market suffix + leading zeros), then use the `ego-browser` skill: `useOrCreateTaskSpace(...)`, `openOrReuseTab('https://www.tradingview.com/symbols/<CODE>/', { wait: true })`. Confirm via `pageInfo()` that the resolved URL/title names the expected company before reading data.
   - Read via `snapshotText()` on the Overview page: last price + % change, Market Cap, Dividend Yield, P/E (TTM), EPS (TTM), and "Next earnings report" if present.
   - Navigate to `/financials-dividends/` on the same symbol and read the ex-dividend date (flag if a "Next ex-dividend date" falls within ~5 trading days; fall back to reporting "Last ex-dividend date" if no next date is announced). **Ambiguity gotcha (confirmed 2026-09-23, SGX names `OU8`/`Q01`/`LJ3`/`544`)**: when an ex-date has already passed but its payment is still pending, this page's `innerText` renders a bare "In X days" value that reads, at a glance, as an upcoming ex-dividend — it is actually the *payment* date countdown, not a fresh ex-dividend event. Cross-check against minichart.com.sg's separate Ex Date / Pay Date columns (SGX names) before flagging anything as a genuinely new upcoming ex-dividend.
   - Navigate to `/news/` on the same symbol and read the top 3-5 rows of the Latest headlines table (timestamp, provider, headline).
   - Reuse one task space across symbols and sub-pages (new tab or same-tab navigation per symbol) rather than opening a fresh task space each time.

6. **Supplemental deep-dive** (optional, standouts only — not every symbol, doesn't scale):
   - **SGX standout or watchlist names**: cross-reference via minichart.com.sg (`https://www.minichart.com.sg/stocks/sgx-<code>/`) for analyst target/broker call/dividend history. Dismiss cookie-consent/sign-in modals if present.
   - **US standout or watchlist names**: cross-reference via financialjuice.com (search box → autocomplete suggestion → `financialjuice.com/<Exchange>/<TICKER>`) for faster, more granular breaking headlines.
   - Close task spaces (`completeTaskSpace(..., { keep: false })`) when done unless the user asked to keep a page open.

7. **Chart screenshots — every watchlist symbol, every run** (changed 2026-08-15; previously scoped to standouts only). Same batch-session mechanics as other TAT skills — `./scripts/tv_session.sh start` once, `./scripts/capture_tv_chart.sh <SYMBOL> D <OUTPUT_NAME>` for **every symbol on `equity_watchlist.json`** (map `.SI`/`.HK` Yahoo symbols to their TradingView `SGX:`/`HKEX:` form first, e.g. `D05.SI` → `SGX:D05`, `0823.HK` → `HKEX:823`; **not** `HSI:`, which the desktop app rejects for individual HK stocks — see the symbol-format note in §1; `.KS` KRX symbols to `KRX:` form, e.g. `000660.KS` → `KRX:000660`), `./scripts/tv_session.sh stop` once at the end. Also capture any standout alert symbols from step 2/5 that aren't already on the watchlist. Per the Screenshot Verification Rule (`AGENTS.md`), visually verify at least one capture before trusting the batch — with a full-watchlist batch this size, spot-check a handful rather than assuming all are fine from script output alone. **Runtime note**: with 26+ watchlist symbols, this batch takes meaningfully longer than the old standouts-only approach — budget accordingly, this is no longer a quick step. Real measurements (2026-08-18): individual captures run ~30-35s once TradingView is warmed up, but the first several captures after a cold session start can take 40-150s each while the app/CDP bridge settles — so a full 27-symbol batch can run 15-25 minutes end to end, not a fixed per-capture estimate.

**Non-interactive / unattended runs (e.g. `claude -p`, cron) — do not background this batch and wait for a notification.** That pattern (`run_in_background: true` on the Bash tool, then a `ScheduleWakeup`/task-notification to resume) depends on multi-turn continuation, which does not exist in `-p`/print mode — the process exits after one turn no matter what it's waiting on, silently abandoning the batch partway through (confirmed 2026-08-18: a cron-triggered run backgrounded the capture loop, printed a "waiting for it to finish" message, and the whole process then exited with a "successful" status having completed only 20 of 27 captures, filed no report, and left TradingView open). Instead, **split the batch into sequential chunks of ~5 symbols**, each run as its own **synchronous, foreground** Bash call with an explicit long `timeout` (e.g. 500000-550000ms) — safely under the tool's 600000ms hard cap even if that chunk lands on the cold-start window. Multiple sequential synchronous tool calls within one turn are fine in `-p` mode; only backgrounding+waiting-for-async-resumption is broken there. In an interactive session (a human or an agent that will see the task-notification), backgrounding the whole batch is still fine and faster to work alongside — this caveat is specifically for single-turn/unattended invocations. Embed all captured charts under `## 📸 Watchlist Chart Screenshots`, grouped by symbol. **Formatting rule (added 2026-08-19)**: each embedded chart gets its own `### <Company/Chart Name>` header immediately above the image — the full name (e.g. "SK Hynix", "OUE Limited"), not the raw ticker/symbol — so the report reads as a scannable list of named sections rather than a bare bullet list of images. **"All captured charts" is literal, not a suggestion (reinforced 2026-08-25)**: two separate runs (2026-08-23, 2026-08-25) independently embedded only 2 of 26-27 successful captures "to keep the report a reasonable size," leaving the rest as unlinked files in `wiki/images/` with a placeholder note — this is wrong and had to be fixed after the fact. Report length is not a real constraint here; embed every successful capture, every run, no exceptions for brevity.

---

## 📊 3. Report Delivery Structure

When reporting scan results:
1. **Table of Contents (build last)**: after drafting the rest of the report (items 2-8 below), insert a TOC immediately after the title, linking to every `## ` section that ended up in the finished report. Use Obsidian's native `[[#Exact Heading Text]]` wikilink anchors — verbatim copy of each `## ` line's text (emoji/case/punctuation unchanged; do not slugify or lowercase, Obsidian's CommonMark renderer doesn't resolve GitHub-style `[text](#slug)` anchors for headings). Wrap it for future find/replace on same-day appends (§2 step 3):
   ```
   <!-- TOC:START -->
   **📑 Table of Contents**

   - [[#Heading text]]
   <!-- TOC:END -->
   ```
   Never embed a `[[SYMBOL]]` wikilink inside a `## ` heading line itself — nested double-brackets break the TOC entry's own link parsing.
2. **Headline**: overall alert-sheet sentiment (Bullish/Bearish %, total alert count) and the standout sector theme, in one sentence.
3. **Sector breakdown table**, most-alerts-first, each sector's Bullish/Bearish split and lean.
4. **Multi-signal symbols** (double/triple confirmation within the sector).
5. **Watchlist check-in** — one line per watchlist symbol: price/change, next ex-dividend/earnings date (when TradingView has one), and the single most notable recent headline.
6. **TradingView cross-reference** for standout alert names (price, dividend/ex-div, top news), if run.
7. **Supplemental deep-dive** (minichart.com.sg / financialjuice.com) for standout SGX/US names, if run.
8. **Watchlist chart screenshots** — every watchlist symbol, every run (see §2 step 7), plus any standout alert symbols not already on the watchlist.

---

## 📚 4. Bookkeeping

Same discipline as `tat-alert-analysis`: file the report under `wiki/reports/equitynews/YYYY-MM-DD_equity-news-scan.md`, log the operation via `scripts/append_log.py` (or by hand, matching the existing `wiki/log.md` entry format), update `wiki/index.md`, and rewrite `wiki/hot.md` if a standout sector theme, a watchlist risk flag (ex-dividend date, market-moving headline), or a supplemental-source headline on an active position is worth carrying forward as an open item.

Per the **Entity Creation** rule in `CLAUDE.md`, adding a symbol to `equity_watchlist.json` counts as "first time tracked" if it doesn't already have a `wiki/entities/` page — create one (or update the existing one) the first time a watchlist symbol's TradingView data is actually pulled, not just when it's added to the JSON file.

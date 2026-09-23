---
name: tat-alert-analysis
description: Skill for syncing the latest live Telegram alerts from the Google Sheet via service account or API across H1 and 4H timeframes, aggregating currency alert statistics, and executing Binni's cluster-and-theme market analysis (Metals theme, Crude Oil / Energy theme, Cryptocurrency cluster, AUD strength story, USD consistency check, EUR intraday flips, multi-timeframe H4/H1 alignment, and noise filtering).
license: MIT
metadata:
  author: AI Trading Team
  version: "2.3.0"
  tags:
    - google-sheets
    - alerts
    - binni-analysis
    - tat
    - multi-timeframe
    - crypto
    - oil
---

# TAT Alert Analysis Skill (3-Timeframe: Daily, 4H, & H1)

This skill defines the protocol for pulling live Telegram alert data from the Google Sheet via Service Account authentication (`service_account.json`), supporting **Daily** (`gid: 462165474`), **4H** (`gid: 1105950672`), and **H1** (`gid: 0`) alert streams, aggregating real-time currency alert statistics, and applying **Binni's Qualitative Cluster-and-Theme Analysis Method**.

---

## 📋 1. Data Source & Authentication

- **Google Sheet**: Pre-configured Sheet ID `1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE`.
  - **H1 Alerts Tab**: `gid=0`
  - **4H Alerts Tab**: `gid=1105950672`
  - **Daily Alerts Tab**: `gid=462165474`
  - **Bull Daily Stock Alerts Tab**: `gid=1875176436` ([Direct Tab Link](https://docs.google.com/spreadsheets/d/1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE/edit?gid=1875176436#gid=1875176436))
  - **Bear Daily Stock Alerts Tab**: `gid=1088333741` ([Direct Tab Link](https://docs.google.com/spreadsheets/d/1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE/edit?gid=1088333741#gid=1088333741))
- **Credentials**: `/Users/chriseah/tradingview-mcp/service_account.json`.
- **Fetch Script**: [scripts/fetch_google_sheet.py](file:///Users/chriseah/obsidian/wiki-trades/scripts/fetch_google_sheet.py).
- **Analysis Script**: [scripts/binni_alert_analysis.py](file:///Users/chriseah/obsidian/wiki-trades/scripts/binni_alert_analysis.py).

---

## ⚡ 2. Execution Protocol

To execute a live TAT alert analysis:

1. **H1+4H Combined Alert Analysis (scheduled cadence)**:
   - **Daily Schedule Window (updated 2026-09-24)**: The only scheduled TAT alert analysis runs happen **5x/day, at 06:15, 09:01, 13:01, 17:01, 21:01 SGT** (the morning slot is its own Orca automation, `FREQ=DAILY;BYHOUR=6;BYMINUTE=15`; the other four share `1 9,13,17,21 * * *` and remain 4 hours apart). The morning slot was added 2026-09-10 at 05:01, moved to 05:31, then to **06:15 on 2026-09-24** so it clears the Daily Brief (05:01, now ~30–35 min because it captures a Daily chart per watchlist instrument) and the Daily Signals run (05:45). All three drive the same TradingView session, so the spacing is deliberate — do not move this slot earlier without re-checking the other two. Each scheduled run executes `python3 scripts/binni_alert_analysis.py --timeframe H1_4H` — reviewing both the 1H and 4H TAT signals together in the same report. The 1H fetch + narrative must fully resolve before the 4H fetch + narrative starts (the script enforces this internally; do not interleave TradingView screenshot batches for the two timeframes either — capture 1H's new-alert charts, then 4H's). See §4.5 below for report formatting, including how to format the case where a combined run is the **first** report of the day.
   - **Retired 2026-09-01**: the standalone hourly-only cadence (plain `--timeframe H1`, running every hour 06:01→00:01 SGT) has been retired at the user's request — TAT alert analysis no longer runs on an hourly baseline. Plain `python3 scripts/binni_alert_analysis.py --timeframe H1` (and standalone `--timeframe 4H`, item 2 below) remain available for ad hoc/manual use but are not scheduled.
   - **Live Execution Mechanism (added 2026-08-28, updated 2026-09-10)**: This schedule runs unattended via a single Orca automation (`orca automations list`), not a manual/ad hoc invocation: **"TAT Combined 1H+4H Review"** (id `38849272-f13f-452c-93f3-2e3c38291d73`, trigger `1 5,9,13,17,21 * * *`, `--provider claude`), pinned to the existing wiki-trades worktree (`--workspace-mode existing`) and `--timezone Asia/Singapore`. (The former "TAT Hourly Review" automation, id `aa6a9424-ce65-4ae9-9d9d-0e2e936e115e`, was removed 2026-09-01.) Requires Orca's runtime to be running (kept alive after login by the `com.chriseah.wikitrades.orca-runtime` LaunchAgent) and a managed Claude account added via `orca account add`.

2. **4H Alert Analysis**:
   - Run `python3 scripts/binni_alert_analysis.py --timeframe 4H` via `run_command`.

3. **Daily Alert Analysis**:
   - Run `python3 scripts/binni_alert_analysis.py --timeframe DAILY` via `run_command`.

4. **3-Timeframe Multi-Timeframe Alignment Analysis (Daily + 4H + 1H)**:
   - Run `python3 scripts/binni_alert_analysis.py --timeframe 3tf` via `run_command`.
   - Cross-references Daily macro trend & Daily TAT boundaries + 4H intermediate structure + H1 execution triggers.

---

## 🧠 3. Binni's Analytical Method Rules

When synthesizing the alert data, analyze according to Binni's core pillars:

1. **Overall Session Sentiment**: Calculate total Bearish vs. Bullish alert counts and state the dominant session tone.
2. **Metals Theme (Gold, Silver & Copper)**:
   - Group `XAUUSD`, `XAGUSD`, `XAUJPY`, `XAUAUD`, `XAUGBP`, `XCUUSD`, `GLD`, `SLV`.
   - Highlight identical timestamps (e.g. `07:01:02`) to confirm **strong, repeated institutional signals rather than noise**.
3. **Crude Oil & Energy Theme (WTI, Brent & USOIL)**:
   - Group `USOUSD`, `CL1!`, `WTI`, `BRENT`, `USOIL`.
   - Track energy market sentiment, oil breakout/retracement TAT signals, and correlation with commodity currency flows (`CAD`, `NOK`).
4. **Cryptocurrency Cluster (Bitcoin, Ethereum, Solana & Altcoins)**:
   - Group `BTCUSD`, `ETHUSD`, `SOLUSD`, `NEARUSD`, `IBIT`, `MSTR`, `CLSK`, `RIOT`.
   - Track Bitcoin directional leadership, crypto market sentiment, institutional ETF flow proxies (`IBIT`, `MSTR`), and altcoin expansion/squeeze triggers.
5. **Currency Cross Mirror Alignment (AUD, NZD, EUR, USD, GBP, JPY, CHF, CAD, etc.)**:
   - Check Base vs. Quote pair alignment across all currency blocs (`AUD`, `NZD`, `EUR`, `USD`, `GBP`, `JPY`, `CHF`, `CAD`, etc.).
   - Cross-reference base pairs (e.g. `AUDCAD`, `AUDJPY`) against quote pairs (e.g. `GBPAUD`, `EURAUD`) to confirm mirror alignment.
   - Confirm whether cross-pair mirror alignment identifies a **standout currency strength or weakness story**.
6. **DXY (US Dollar Index) Macro Direction & Gap Analysis**:
   - Track `DXY` / `USDX` key levels, weekly/daily Wash & Rinse boundaries, gap-fill behavior, and macro dollar trend context.
   - Cross-reference DXY direction against major dollar pairs (`EURUSD`, `GBPUSD`, `USDJPY`, `USDCAD`, `USDSGD`) to confirm macro dollar alignment or flag divergence.
7. **Inconsistency Check (USD Pairs Divergence)**:
   - Check `USDX`, `USDCAD`, `USDSGD` against `USDJPY` and `USDCNH`.
   - Flag conflicting directions and warn traders to treat with caution until confirming alert timestamps and labeling conventions.
8. **Intraday Flips & Splits (e.g. EUR Pairs)**:
   - Identify pairs that flipped direction within the same day.
9. **Indices & Global Equity Sector**:
   - Group `NDQ100`, `GER40`, `FRA40`, `UK100`, `US2000`, `SPX500`, `US30`, `JPN225`, `CN50`, `HSI`, `HK50`, `ASX200`, `EU50`.
   - Track global index breakout signals, tech sector momentum, and European/Asian equity sentiment.
10. **All-Symbol Comprehensive Inclusion Rule**:
    - Every TAT analysis report (1H, 4H, Daily, 3TF) MUST evaluate and include **ALL SYMBOLS across ALL ASSET CLASSES** (Forex, Metals, Energy, Cryptocurrencies, AND Global Indices). Never omit any category or logged alert symbol.
11. **Timeframe Signal Probability Hierarchy Rule**:
    - **Highest Probability (⭐⭐⭐ — 4H + 1H Dual Alignment)**: When 4H and 1H TAT indicators produce the **SAME signal direction**, the setup carries the **highest statistical win rate and conviction**.
    - **High Probability (⭐⭐ — 4H Standalone Signal)**: 4H TAT signals carry **higher structural probability** and macro trend weight than 1H signals alone.
    - **Lower Probability (⭐ — 1H Standalone Signal)**: 1H TAT signals alone carry **lower probability** and higher noise risk; use primarily for tactical timing.
    - **Retest Execution (4H Trend vs 1H Pullback)**: When 4H is in one direction (e.g., Bearish) and 1H fires the opposite signal (e.g., Bullish), treat 1H as a temporary counter-trend pullback returning to 4H TAT boundaries for optimal risk-reward re-entry.
12. **Explicit Per-Instrument Direction Rule in Cluster Tables**:
    - In all TAT Alert Analysis reports and cluster summary tables, every instrument MUST explicitly specify its individual direction with visual indicators: `[[SYMBOL]] (🟢 Bull)` or `[[SYMBOL]] (🔴 Bear)`.
    - In cluster summary tables, group or tag pairs explicitly (e.g., `[[CADCHF]] (🟢 Bull), [[USDCAD]] (🟢 Bull), [[EURCAD]] (🔴 Bear), [[NZDCAD]] (🔴 Bear), [[GBPCAD]] (🔴 Bear)`) so the exact direction of every single pair is immediately unambiguous and obvious to evaluate at a glance.

### 📋 Standard Cluster Summary Table Template:

| Cluster | Pairs & Instruments (with Explicit Direction) | Cluster Bias | Count | Conviction & Structural Significance |
| :--- | :--- | :--- | :--- | :--- |
| **Commodity & Cross FX (CAD Surge)** | `[[CADCHF]] (🟢 Bull)`, `[[USDCAD]] (🟢 Bull)`, `[[EURCAD]] (🔴 Bear)`, `[[NZDCAD]] (🔴 Bear)`, `[[GBPCAD]] (🔴 Bear)` | **Bullish CAD vs G10 / Bearish vs USD** | 5 (2 Bull / 3 Bear) | Loonie outperforming EUR, NZD, GBP, CHF |

---

## 📊 4. Autonomous Execution & Same-Day Reporting Protocol

1. **Autonomous Service Account Protocol**:
   - Sheet data pulling and report updates MUST execute autonomously using native tools without prompting for user confirmation.
2. **1H Analysis Header Timestamp Rule**:
   - All TAT analysis reports must include explicit SGT timestamps in the main title (e.g., `# 📈 TAT Alert Report — YYYY-MM-DD [HH:MM SGT]`).
3. **Same-Day 1H Iteration & Diff Protocol**:
   - When executing an update run on a date that already has a report file (`wiki/reports/tat_analysis/YYYY-MM-DD-tat-alert-report.md`), do not overwrite existing content.

   - Append a new section: `## 🕒 Intraday Update Run — [HH:MM SGT]`.
   - Include an explicit **Differences & Changes Highlights** table comparing alert counts, sentiment shifts, signals, and structural changes since the previous run.
4. **New Alert Screenshot Capture & Report Linking Protocol**:
   - Whenever a TAT alert analysis detects **NEW alerts** for specific instruments during the scan run, the report MUST explicitly state which symbol fired a new signal (with signal name, direction, and timestamp).
   - Execute `./scripts/tv_session.sh start` once, `./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME>` for each new alert symbol (which automatically generates timestamped filenames `YYMMDD-HHMMSS_<symbol>_<tf>_chart.png` for sorting), and `./scripts/tv_session.sh stop` once at the end.
   - Embed the captured chart screenshots under a dedicated `## 📸 New Alert Chart Screenshots` section in the report (`![<Symbol> Chart Screenshot](../../images/YYMMDD-HHMMSS_<symbol>_<tf>_chart.png)`) and present them in the response.
5. **5x-Daily 1H+4H Combined Review Rule (updated 2026-09-24 — morning slot now 06:15 SGT)**:
   - At the five scheduled combined-review times (06:15, 09:01, 13:01, 17:01, 21:01 SGT — see §2.1, now the day's *only* scheduled TAT alert runs), run `--timeframe H1_4H`.
   - **If a report for today already exists** (i.e. this is not the first scheduled run of the day), append a new section with header `## 🕒 Intraday Update Run — [HH:MM SGT] (1H + 4H Combined Review)`, containing the 4H cluster/theme narrative and the 4H+1H confluence/retest classification (⭐⭐⭐ dual-alignment and retest-pullback buckets) in addition to the normal 1H Differences & Changes Highlights table — all within the same single daily report file. No separate 4H report file is created for these 5 runs.
   - **If this is the first report of the day** (typically the 06:15 run, since there is no hourly run before it anymore) — start a fresh report with a top-level header `# 📈 1H + 4H TAT Alert Analysis Report — YYYY-MM-DD [HH:MM SGT] (1H + 4H Combined Review)` instead of an appended section. Its body carries the same content an appended combined section would (1H executive summary + instrument watchlist table, 4H cluster/theme narrative, 4H+1H confluence/retest classification), followed by the TOC per rule 6 below. Later same-day combined runs (09:01/13:01/17:01/21:01) still append as intraday update sections as described above.
   - New-alert screenshot capture (rule 4 above) applies to new alert symbols from either timeframe during these runs, captured in two sequential batches (1H's, then 4H's).
6. **TOC Maintenance Protocol (create + every append)**:
   - The **first** report file created for a given date must place a Table of Contents immediately after the title line, before any `## ` section — build it last, after that first section's content is drafted (you can't link to sections that don't exist yet).
   - Every subsequent same-day append (rules 3 and 5 above) MUST regenerate this TOC to include the newly-appended section — do not leave a stale TOC that's missing the latest run(s).
   - Use this exact marker convention so the block can be found and replaced with `Edit` rather than reconstructing the whole file:
     ```
     <!-- TOC:START -->
     **📑 Table of Contents**

     - [[#Heading text]]
     <!-- TOC:END -->
     ```
   - Each entry is Obsidian's native `[[#Exact Heading Text]]` wikilink format — copy the `## ` line's text **verbatim** (emoji, brackets, case, punctuation unchanged). Do NOT use markdown-style `[Text](#slug)` links or any lowercased/hyphenated slug — Obsidian's CommonMark-based renderer does not resolve those for heading anchors, only wikilinks.
   - Never embed a `[[SYMBOL]]` wikilink inside a `## ` heading line itself (only in body text) — nested double-brackets break the TOC entry's own wikilink parsing.




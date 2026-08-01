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

1. **H1 Alert Analysis**:
   - Run `python3 scripts/binni_alert_analysis.py --timeframe H1` via `run_command`.

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

---

## 📊 4. Autonomous Execution & Same-Day Reporting Protocol

1. **Autonomous Service Account Protocol**:
   - Sheet data pulling and report updates MUST execute autonomously using native tools without prompting for user confirmation.
2. **1H Analysis Header Timestamp Rule**:
   - All 1H TAT analysis reports must include explicit SGT timestamps in the main title (e.g., `# 📈 1H TAT Analysis Report — YYYY-MM-DD [HH:MM SGT]`).
3. **Same-Day 1H Iteration & Diff Protocol**:
   - When executing an update run on a date that already has a report file (e.g., `wiki/reports/tat_analysis/YYYY-MM-DD-1h-*-report.md`), do not overwrite existing content.

   - Append a new section: `## 🕒 Intraday Update Run — [HH:MM SGT]`.
   - Include an explicit **Differences & Changes Highlights** table comparing alert counts, sentiment shifts, signals, and structural changes since the previous run.
4. **New Alert Screenshot Capture & Report Linking Protocol**:
   - Whenever a TAT alert analysis detects **NEW alerts** for specific instruments during the scan run, the report MUST explicitly state which symbol fired a new signal (with signal name, direction, and timestamp).
   - Execute `./scripts/tv_session.sh start` once, `./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME>` for each new alert symbol (which automatically generates timestamped filenames `YYMMDD-HHMMSS_<symbol>_<tf>_chart.png` for sorting), and `./scripts/tv_session.sh stop` once at the end.
   - Embed the captured chart screenshots under a dedicated `## 📸 New Alert Chart Screenshots` section in the report (`![<Symbol> Chart Screenshot](../../images/YYMMDD-HHMMSS_<symbol>_<tf>_chart.png)`) and present them in the response.




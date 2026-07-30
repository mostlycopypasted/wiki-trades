---
name: daily-chart-scanner
description: Skill for reading Daily (1-day) charts on TradingView using the watchlist extracted from rules.json (~/tradingview-mcp/rules.json), scanning TAT trend bars, market structure (Bullish, Bearish, Squeeze, Expand), and TAT signals, and evaluating setups against the Retest Execution concept.
license: MIT
metadata:
  author: AI Trading Team
  version: "1.0.0"
  tags:
    - tradingview
    - daily-scanner
    - watchlist
    - retest-execution
---

# Daily Chart Scanner & Watchlist Skill

This skill defines the standardized protocol for scanning Daily (1-day / 1440-minute) charts on TradingView by extracting the active watchlist from `~/tradingview-mcp/rules.json`, capturing TAT trend indicators, ZigZag market structures, and TAT signals, and filtering candidates against the **Retest Execution** concept.

---

## 📋 1. Watchlist & Configuration Source

The active watchlist and scanning configuration are driven dynamically by `/Users/chriseah/tradingview-mcp/rules.json`:

- **Watchlist**: Extracted from `rules.json`, which serves as the master combined default watchlist containing **88 unique instruments** across Forex, Commodities, Indices, Crypto, US Equities (`us_stocks.json`), and Singapore/Hong Kong Equities & Indices (`sghk_stocks.json`).
- **Timeframe**: Fixed to **`D`** (Daily / 1-day resolution).
- **Bias Criteria**:
  - `🟢 Bullish`: TAT `Up Trend` is active (1.0).
  - `🔴 Bearish`: TAT `Down Trend` is active (-1.0).
  - `⚪ Neutral`: Neither trend bar is active.

---

## ⚡ 2. Execution Protocol

To run a Daily chart scan:

1. **Verify TradingView CDP Connection & Reset Protocol**:
   - Run `bash ~/tradingview-mcp/scripts/launch_tv_debug_mac.sh` to ensure TradingView Desktop is running with Chrome DevTools Protocol enabled on port 9222.
   - For every symbol scanned, reset chart scale for Daily resolution (`chart_set_timeframe` = `1D`).

2. **Execute Automated Daily Scanner & TAT Level Extraction**:
   - Run `node ~/tradingview-mcp/scratch/run_daily_brief.mjs` via `run_command`.
   - Query `data_get_pine_lines` and `data_get_study_values` via TradingView MCP to extract:
     - **Wash Lines**: `Day Buy` (Daily Buy Wash Line), `Day Sell` (Daily Sell Wash Line), `Wk Buy` (Weekly Buy Wash Line), `Wk Sell` (Weekly Sell Wash Line).
     - **TAT Levels**: `MajD/MinD <Price> FiRet m15/h1/h4/D/W/M`, `MajD/MinD <Price> Sup/Res m15/h1/h4/D/W`, and `TP : <Price>`.
     - **TAT Alerts**: `OptBull`, `LBull`, `SBull` (Bullish) | `OptBear`, `LBear`, `SBear` (Bearish).
   - The scanner extracts the watchlist from `rules.json`, sets timeframe to `D`, scans all symbols, compares results with yesterday's Daily brief, and computes the Daily Currency Strength Scoreboard.

3. **Output Files**:
   - Markdown Report: `/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/YYYY-MM-DD.md`
   - Structured JSON: `/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/YYYY-MM-DD.json`

---

## 🎯 3. Retest Execution Filter Rules

Once the Daily brief data is captured, evaluate candidate setups against the **Retest Execution** principles (`wiki/concepts/retest-execution.md`):

### 🟢 Bullish Retest Candidates
- **Structure**: Market structure is in `Squeeze` or `Bearish` pullback into support.
- **TAT Signal**: Reversal signal triggered (`↑SBull`, `LBull`, or `⬤OptBull`).
- **Risk Scale**: Price is at **Level 1–2** on the 1-to-10 scale (at or near support bottom).

### 🔴 Bearish Retest Candidates
- **Structure**: Market structure is in `Squeeze` or `Bullish` retracement into resistance.
- **TAT Signal**: Reversal signal triggered (`↓LBear`, `SBear`, or `⬤OptBear`).
- **Risk Scale**: Price is at **Level 9–10** on the 1-to-10 scale (at or near resistance top).

---

## 📊 4. Report Delivery Structure

When reporting results to the user:
1. **Summary of Daily Changes**: Highlight any structural shifts or new TAT signals since yesterday.
2. **Currency Strength Scoreboard (Daily)**: Present the aggregated currency scores and top strong-vs-weak trade ideas.
3. **Top Retest Trade Candidates**: Highlight symbols meeting the Daily Retest Execution filter rules with entry zones and risk-scale levels.

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

2. **Execute Master Daily Brief Generator**:
   - Run `python3 scripts/generate_daily_brief.py` via `run_command`.
   - This master script automatically:
     1. Invokes the `currency-strength-tracker` skill (`pull_currency_strength.py`) to scrape live readings, generate historical CSV, and render `wiki/images/currency-strength-graph.svg`.
     2. Runs Daily & 3-Timeframe TAT Alert Analysis (`binni_alert_analysis.py`).
     3. Runs the D-R-H-R Short-Term Trading Scanner (`scan_drhr_setups.py`).
     4. Captures live TradingView chart screenshots using `./scripts/capture_tv_chart.sh` for top setups and saves them to `wiki/images/`.
     5. Assembles and writes the complete Daily Brief report to `wiki/reports/daily_brief/YYYY-MM-DD.md`.


3. **Output Files & Screenshot Storage**:
   - Markdown Report: `/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/YYYY-MM-DD.md`
   - Structured JSON: `/Users/chriseah/obsidian/wiki-trades/wiki/reports/daily_brief/YYYY-MM-DD.json`
   - Chart Screenshots: Captured via `./scripts/capture_tv_chart.sh` and stored directly in `/Users/chriseah/obsidian/wiki-trades/wiki/images/<symbol>_<timeframe>_chart.png` (embedded in Daily Brief reports using relative path `../../images/<symbol>_<timeframe>_chart.png`).


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

When generating the Daily Brief and reporting results to the user:
1. **Summary of Daily Changes**: Highlight any structural shifts or new TAT signals since yesterday.
2. **Currency Strength Scoreboard & Trend Graph (Mandatory)**: 
   - Execute `python3 .agents/skills/currency-strength-tracker/scripts/pull_currency_strength.py` to ensure the latest Currency Strength Meter readings and SVG trend graph are generated.
   - Present the full **Currency Strength Table** (Scores, Trend Biases, and Suggested Pairs).
   - Embed the **Currency Strength Trend Graph (SVG)** (`![Currency Strength Trend Graph](../../images/currency-strength-graph.svg)`).
3. **Top Retest Trade Candidates**: Highlight symbols meeting the Daily Retest Execution filter rules with entry zones and risk-scale levels.


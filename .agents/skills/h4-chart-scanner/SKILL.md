---
name: h4-chart-scanner
description: Skill for reading 4H (240-minute) charts on TradingView using the watchlist extracted from rules.json (~/tradingview-mcp/rules.json), scanning TAT trend bars, market structure (Bullish, Bearish, Squeeze, Expand), and TAT signals, and evaluating setups against the Retest Execution concept.
license: MIT
metadata:
  author: AI Trading Team
  version: "1.0.0"
  tags:
    - tradingview
    - 4h-scanner
    - watchlist
    - retest-execution
---

# 4H Chart Scanner & Watchlist Skill

This skill defines the standardized protocol for scanning 4-hour (240-minute) charts on TradingView by extracting the active watchlist from `~/tradingview-mcp/rules.json`, capturing TAT trend indicators, ZigZag market structures, and TAT signals, and filtering candidates against the **Retest Execution** concept.

---

## 📋 1. Watchlist & Configuration Source

The active watchlist and scanning configuration are driven dynamically by `/Users/chriseah/tradingview-mcp/rules.json`:

- **Watchlist**: Extracted from the `"watchlist"` array in `rules.json` (contains ~90+ instruments across Forex, Commodities, Indices, Crypto, and Equities).
- **Timeframe**: Fixed to **`240`** (4-hour resolution).
- **Bias Criteria**:
  - `🟢 Bullish`: TAT `Up Trend` is active (1.0).
  - `🔴 Bearish`: TAT `Down Trend` is active (-1.0).
  - `⚪ Neutral`: Neither trend bar is active.

---

## ⚡ 2. Execution Protocol

To run a 4H chart scan:

1. **Verify TradingView CDP Connection**:
   - Run `bash ~/tradingview-mcp/scripts/launch_tv_debug_mac.sh` to ensure TradingView Desktop is running with Chrome DevTools Protocol enabled on port 9222.
   - Verify connection using `call_mcp_tool` with `ServerName: "tradingview"`, `ToolName: "tv_health_check"`.

2. **Execute Automated 4H Scanner**:
   - Run `node ~/tradingview-mcp/scratch/run_4h_brief.mjs` via `run_command`.
   - The scanner extracts the watchlist from `rules.json`, sets timeframe to `240`, scans all symbols, compares results with yesterday's 4H brief, and computes the 4H Currency Strength Scoreboard.

3. **Output Files**:
   - Markdown Report: `/Users/chriseah/tradingview-mcp/4H_brief/YYYY-MM-DD.md`
   - Structured JSON: `/Users/chriseah/tradingview-mcp/4H_brief/YYYY-MM-DD.json`

---

## 🎯 3. Retest Execution Filter Rules

Once the 4H brief data is captured, evaluate candidate setups against the **Retest Execution** principles (`wiki/concepts/retest-execution.md`):

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
1. **Summary of 4H Changes**: Highlight any structural shifts or new TAT signals since yesterday.
2. **Currency Strength Scoreboard (4H)**: Present the aggregated currency scores and top strong-vs-weak trade ideas.
3. **Top Retest Trade Candidates**: Highlight symbols meeting the 4H Retest Execution filter rules with entry zones and risk-scale levels.

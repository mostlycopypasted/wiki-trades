---
name: short-term-trading
description: Skill for executing Binni Ong's D-R-H-R (Day-Retest-HigherHigh-Retracement) short-term trading methodology. Maximizes account growth and risk-to-reward ratio (1:5 to 1:10+) by combining Daily (D1) macro target profits with H1 trendline breakouts and M15 retest entry triggers.
license: MIT
metadata:
  author: AI Trading Team
  version: "1.6.0"
  tags:
    - tat
    - short-term-trading
    - drhr-formula
    - retest-execution
---

# Short-Term Trading Skill (The D-R-H-R Methodology)

This skill codifies Binni Ong's structured **D-R-H-R** (Day, Retest, Higher High / Lower Low, Retracement) short-term trading framework, designed for small-account growth ($500 USD) and high profit potential through **asymmetric risk-to-reward (1:5 to 1:10+ R:R)**.

---

## 📋 1. Core Philosophy

High-profit short-term trading is achieved by **decoupling the stop-loss timeframe from the target profit timeframe**:
- **Entry & Stop-Loss**: Managed on **H1 / M15** (ultra-tight risk, ~15–20 pips).
- **Profit Target**: Set on **Daily (D1) TAT Resistance** (massive reward, ~150–300 pips).

---

## ⚡ 2. The 4-Step D-R-H-R Protocol

### **Step 1: D — Day Chart Reference Frame (D1)**
1. Open the **Daily (D1) chart** to filter out market noise.
2. **TradingView MCP Wash Line & TAT Level Extraction**: Query `data_get_pine_lines` and `data_get_study_values` on D1 resolution (`chart_set_timeframe` = `1D`) to extract exact **Wash Lines** (`Day Buy` Daily Buy Wash Line, `Day Sell` Daily Sell Wash Line, `Wk Buy` Weekly Buy Wash Line, `Wk Sell` Weekly Sell Wash Line) and **Daily TAT Support & Resistance Levels**.
3. Identify the ultimate **Daily TAT Target Profit Level** (Daily Resistance for Longs / Daily Support for Shorts) for maximum asymmetric expansion.

### **Step 2: R — Retest (The 2nd Test Rule & Firm Level Establishment)**
1. **Retest Determination**: Monitor the Day chart for price returning to and touching a previously identified support (for buys) or resistance (for sells) level for a **second time**.
2. **Confirming Firm Level & Cut-Loss Point**: The confirmed retest level becomes your strict boundary for risk management (Level 1–2 on Binni's 1–10 Risk Scale).
3. **Transition to H1/4H Timeframe**: Reset chart view to target timeframe resolution (`chart_set_timeframe`) and query `data_get_pine_lines` for exact **`MajD`** (Major Daily) and **`MinD`** (Minor Daily) TAT structural levels with timeframe suffixes:
   - **First Retracement**: `MajD/MinD <Price> FiRet m15/h1/h4/D/W/M` (15m, 1h, 4h, Daily, Weekly, Monthly).
   - **Support / Resistance**: `MajD/MinD <Price> Sup/Res m15/h1/h4/D/W` (15m, 1h, 4h, Daily, Weekly).
   - **Take Profit**: `TP : <Price>` (e.g. `TP : 1.64055`).
   - **TAT Alerts**: `OptBull`, `LBull`, `SBull` (Bullish) | `OptBear`, `LBear`, `SBear` (Bearish).

### **Step 3: H — Higher High / Lower Low (H1 Structure Shift)**
1. **Structure Shift Confirmation**: Confirm price has broken previous trend momentum and created a Higher High (buys) or Lower Low (sells) on H1.
2. **TAT Trend Status**: Verify `TATbyBinniOngv2` study state via TradingView MCP (`Up Trend = 1.0` for buys / `Down Trend = 1.0` for sells).

### **Step 4: R — Retracement (M15 Execution)**
1. **Strict Discipline Rule**: Never chase initial breakout candles; await retracement pullback into pre-calculated 1H/M15 TAT support/resistance cluster.
2. **Extract Retracement TAT Levels**: Query `data_get_pine_lines` via TradingView MCP to pinpoint exact limit buy/sell coordinates (`1.91009 – 1.91058` zone for GBPAUD, `1.2027 – 1.2035` zone for AUDNZD, `1.6355 – 1.6365` zone for EURAUD).
3. **M15 Signal & Execution**: Confirm reversal signal (`LBull`, `OptBull`, `LBear`, `OptBear`) and place limit order.

---

## 🛡️ 3. Risk Management & Position Trailing

1. **Risk Management & Capital Protection**:
   - Protect your capital by using the minimum trade size, such as **0.01 micro-lots** (especially on smaller $500 USD accounts) to avoid margin stress.
   - Stop-Loss Placement: Placed just below the H1 retest swing low (Level 1–2 on Binni's 1–10 Risk Scale).
   - **Trailing Stop Discipline**: Once the trade is profitable, shift your stop-loss into a trailing stop right below the current price structure so that a sudden reversal does not result in a loss. As price reaches intermediate H1 targets, lock in partial profits and trail the stop-loss to the most recent H1 higher low to guarantee a 100% risk-free trade.

2. **Maximizing Reward (Asymmetric R:R Ratio)**:
   - Manage the trade by combining your precise H1 entry and tight H1 stop-loss with the **higher target profits mapped out on the Day chart (D1)**.
   - Hold the core position until price touches the **Daily (D1) Target Profit**.
   - This technique maximizes your reward-to-risk ratio (**1:5 to 1:10+ R:R**), allowing you to generate significant profits even on a small account.

---

## 📡 4. TradingView MCP Mandatory Data Protocol

Whenever executing the D-R-H-R Short-Term Trading Framework, **MUST use the TradingView MCP Toolset** (`chart_set_symbol`, `chart_set_timeframe`, `data_get_pine_lines`, `data_get_study_values`, `chart_get_state`) to extract live, 100% accurate broker chart analysis:
1. **Chart View Reset Protocol**: ALWAYS call `chart_set_symbol` or `chart_set_timeframe` to reset the chart scale and center candles for the target timeframe (D1, 4H, H1, M15) before reading levels.
2. **Pine Script Level Extraction**: Query `data_get_pine_lines` and `data_get_study_values` to fetch exact `MajD`, `FiRet`, `Sup`, `Res`, and `TAW4` lines.
3. **5-Decimal Broker Precision**: Verify exact 5-decimal price coordinates directly against Eightcap broker charts.

---

## 📄 Source Reference
- **Transcript**: [raw/Short-term trading with high profit potential.md](file:///Users/chriseah/obsidian/wiki-trades/raw/Short-term%20trading%20with%20high%20profit%20potential.md)
- **Concept Page**: [wiki/concepts/retest-execution.md](file:///Users/chriseah/obsidian/wiki-trades/wiki/concepts/retest-execution.md)

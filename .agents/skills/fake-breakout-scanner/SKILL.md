---
name: fake-breakout-scanner
description: Skill for scanning the full watchlist for Wash & Rinse "Long-Tail Bottom/Top Heavy Wash Candle" fake-breakout setups — a candle that spikes past recent structure (a trendline, support, or resistance) then closes back against it with a long wick — in both directions (long and short), using scripts/scan_fake_breakout_setups.py.
license: MIT
metadata:
  author: AI Trading Team
  version: "1.0.0"
  tags:
    - tradingview
    - wash-and-rinse
    - fake-breakout
    - watchlist
    - long-short
---

# Fake Breakout (Wash & Rinse Long-Tail Candle) Scanner Skill

This skill defines the protocol for scanning the watchlist for the **Long-Tail Bottom/Top Heavy Wash Candle** pattern documented in [wiki/concepts/wash-and-rinse.md](../../../wiki/concepts/wash-and-rinse.md) — a fakeout past trendline/structure that leaves a long tail wick, indicating an institutional liquidity sweep. It generalizes the setup first identified ad-hoc on `[[BTCUSD]]` in the 2026-08-01 Weekly Review (see `wiki/entities/btcusd.md`) into a repeatable scan across **all watchlist symbols, in both directions**.

---

## 📋 1. Pattern Definition

### 🔴 SHORT — Fake Breakout / Bottom-Heavy Wash Candle
- A candle spikes to a **new local high** above recent structure (a false breakout past resistance or a trendline).
- It closes back in the **bottom** of its range with a long upper wick ("bottom-heavy").
- The candle's **low** becomes the **green sell wash line**.
- **Trigger**: a later closed bar closes below that low, confirming the reversal down toward the next structural support.
- **Re-entry rule ("Sell High, Sell High, Sell High")**: after the trigger, never sell at the low — wait for price to rally back up into resistance / the green wash line before shorting again.

### 🟢 LONG — Fake Breakdown / Top-Heavy Wash Candle
- Mirror image: a candle spikes to a **new local low** below recent structure (a false breakdown past support or a trendline).
- It closes back in the **top** of its range with a long lower wick ("top-heavy").
- The candle's **high** becomes the **magenta buy wash line**.
- **Trigger**: a later closed bar closes above that high, confirming the reversal up toward the next structural resistance.
- **Re-entry rule**: wait for price to pull back down into support / the magenta wash line before going long again.

### Confirmation discipline ("Slow is good")
Wait for the long-tail candle to fully close before acting on it — don't front-run an in-progress bar.

---

## ⚡ 2. Execution Protocol

1. **Ensure the watchlist snapshot is current**:
   - If today's `~/tradingview-mcp/daily_brief/{date}.json` doesn't exist yet, run the live `tv brief -r ./rules.json` scan and `scripts/build_daily_bias.py` first (same step `generate_daily_brief.py` performs). Otherwise the scanner falls back to the most recent existing snapshot.

2. **Run the scanner** for the desired timeframe:
   ```
   python3 scripts/scan_fake_breakout_setups.py --timeframe 4h
   python3 scripts/scan_fake_breakout_setups.py --timeframe 1h
   python3 scripts/scan_fake_breakout_setups.py --timeframe 1d
   ```
   - Each run reports **both** 🟢 LONG and 🔴 SHORT candidates, labeled `⚡ TRIGGERED` (wash line already broken — watch for the retracement re-entry) or `👀 ARMED` (wick has formed, wash line not yet broken).
   - Optional tuning: `--lookback` (bars of prior structure checked for the breakout, default 10), `--recent` (how many of the latest closed bars are checked as candidates, default 5), `--watchlist <file>` to scope to a specific instrument list (e.g. `~/tradingview-mcp/crypto_list.json`).

3. **Cross-check exact levels live** (per the Continuous Trade Monitoring & Execution Protocol in `CLAUDE.md`) for any `TRIGGERED` or newly `ARMED` symbol before treating it as actionable:
   - Reset the chart (`Alt+R`) and re-read `data_get_pine_lines` / `data_get_pine_labels` for the live wash lines (`Day Buy`, `Day Sell`, `Wk Buy`, `Wk Sell`) and TAT levels (`MajD/MinD ... Sup/Res`, `TP :`) — the scanner's wash line is a geometric proxy from raw OHLC, not the on-chart Pine-plotted line.
   - Confirm the nearest higher-timeframe structural boundary (per the Multi-Timeframe Context rule) for stop-loss/take-profit placement.

4. **Screenshot new signals**: for any symbol newly flagged `TRIGGERED` since the last scan, follow the New Alert Screenshot Capture Rule — `./scripts/tv_session.sh start` once, `./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME> <OUTPUT_NAME>` per symbol, `./scripts/tv_session.sh stop` once — and embed under a `## 📸 New Alert Chart Screenshots` section in any report.

---

## 📊 3. Report Delivery Structure

When reporting scan results to the user:
1. **Summary counts**: total Long vs. Short candidates found, and how many are `TRIGGERED` vs. `ARMED`.
2. **Triggered setups first**, each with: symbol, direction, wash line price, spike/broken-structure level, last close, and the re-entry rule to apply.
3. **Armed setups**: flagged as pattern candidates to watch, not yet actionable.
4. **New alert screenshots** (if any symbol newly triggered), per the protocol above.

---

## 📚 4. Bookkeeping

If a flagged setup is acted on or discussed further, follow standard wiki bookkeeping discipline: update the relevant `wiki/entities/<symbol>.md` page with the setup and outcome, cross-reference `wiki/concepts/wash-and-rinse.md`, log the operation via `scripts/append_log.py`, and rewrite `wiki/hot.md`.

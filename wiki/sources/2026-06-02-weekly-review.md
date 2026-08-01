---
type: transcript
date: 2026-06-02
ingested: 2026-06-03
status: read
raw: ../../raw/Ahh-Access-Time-BN-20260602-89a02c5c-c735.md
---

# Weekly Review (Access Time) — 2nd June 2026

> Weekly Access Time meeting transcript of BN Ong (Bini) analyzing lower timeframe reversals on gold and forex, HSI support bounds, copper's cup and handle breakout, and Magnificent 7 rotation.

## Ingested Instruments List

1. **[XAUUSD](../entities/xauusd.md) (Gold)**:
   - **Key Levels**: Daily chart target profit hit. H4 support zone retesting 62% Fibonacci level. H1 green line resistance at 4471. M15/H1 breakout confirmation above previous swing high; H4 pending bullish close above the W/R (Wash and Rinse) line.
   - **Direction**: Bullish Reversal.
2. **[HSI](../entities/hsi.md) (Hang Seng Index / Hong Kong 50)**:
   - **Key Levels**: Crucial support line at 24,880 (within the equidistant channel). Daily structure maintains higher highs and higher lows. Key resistance target at 26,000 (specifically 26,085).
   - **Direction**: Bullish Flattish (Uptrend intact, consolidating near support).
3. **[AUDUSD](../entities/audusd.md)**:
   - **Key Levels**: Weekly wash line support boundary. Neckline support zone. Bullish H4 signal hit target profit, now re-testing the wash/rinse line. Reversal confirms on a close above the local H1 horizontal high.
   - **Direction**: Bullish setup (buying neckline retests with stops below neckline).
4. **[HGUSD](../entities/hgusd.md) (Copper)**:
   - **Key Levels**: Daily cup and handle pattern, bouncing 3 times off the base. Strongest performer among metals, supported by the blue line. Breaking out to a new high.
   - **Direction**: Bullish.
5. **[XAGUSD](../entities/xagusd.md) (Silver)**:
   - **Key Levels**: Support verified at target profit level. Double bottom pattern forming on lower timeframes. Confirmation breakout level at 72.76 / 76 on the M15 chart.
   - **Direction**: Pending Bullish (waiting for breakout above 72.76 / 76).
6. **[AUDJPY](../entities/audjpy.md)**:
   - **Key Levels**: Breakout setup above key resistance.
   - **Direction**: Bullish.
7. **[NVDA](../entities/nvda.md) (Nvidia)**:
   - **Key Levels**: Bounced off its consolidation base, showing a strong reversal candlestick last night.
   - **Direction**: Bullish (buying near the base).
8. **[MSFT](../entities/msft.md) (Microsoft)**:
   - **Key Levels**: Bullish signal on the orange line. Retraced to support and bounced last night, leading the software sector.
   - **Direction**: Bullish.
9. **[GOOGL](../entities/googl.md) (Google)**:
   - **Key Levels**: Predicted upper target level at 368. Correcting from its high back towards its base.
   - **Direction**: Bullish (buy zone near the base).
10. **[AMZN](../entities/amzn.md) (Amazon)**:
    - **Key Levels**: Solid base consolidation; currently in a healthy retracement.
    - **Direction**: Bullish (preparing for next momentum leg).
11. **[ARM](../entities/arm.md) (ARM Holdings)**:
    - **Key Levels**: Bullish signal on the orange line. Made higher highs and higher lows, bouncing 3 times off its base. Up 300% since detection at 120.
    - **Direction**: Bullish.
12. **[IGV](../entities/igv.md) (Software ETF)**:
    - **Key Levels**: Retracing after a run to 107.7 (initial signals triggered in the 80s).
    - **Direction**: Bullish.

---

## Technical Trading Rules Emphasized

- **Rule 1: Higher Timeframe Anchor**: Lower timeframe execution triggers (M15/H1) must always align with the direction and support/resistance zones established on the higher timeframes (Daily/H4).
- **Rule 2: Avoid Breakout Chase (Frenzy)**: Do not buy stocks in a breakout frenzy. Safer and more profitable entries occur when the asset is trading near its horizontal base.
- **Rule 3: Core to Peripheral Rotation**: Markets rotate in cycles—flowing from core assets (like Magnificent 7) to peripheral sectors (like software) and back. Position early in the lagging sector near its base.
- **Rule 4: Horizontal Primacy Over Moving Averages**: Moving averages can lag and cause confusion in flattish markets. Focus on horizontal price levels (pivots, wash lines) for structural validation.

---

## Pine Script Accumulation & Wash and Rinse Overlap

These techniques are documented to construct a comprehensive Pine Script indicators/trading system:

### 1. TAT Reversal Confirmation
* **Logic**: Verifies a structural change in direction on intraday charts (M15/H1).
* **Pine Script Strategy Implementation**:
  - Track swing highs and lows to define the current trend structure.
  - Signal a reversal when price creates a higher low and subsequently closes above the previous local swing high.
  - Define the stop-loss level dynamically as the low of the higher low.

### 2. Double Bottom Reversal (Silver Setup)
* **Logic**: Trading double bottoms at major support targets.
* **Pine Script Strategy Implementation**:
  - Scan for a major support touch (retest of previous swing low).
  - Confirm the second low does not close below the first low.
  - Trigger a buy when the price breaks above the swing high (neckline peak, e.g. 72.76 level for Silver) separating the two lows.

### 3. Neckline/Shoulder Retest (Aussie Setup)
* **Logic**: Entering head and shoulders patterns at the right shoulder to maximize risk-to-reward.
* **Pine Script Strategy Implementation**:
  - Identify a potential Head and Shoulders bottom pattern.
  - Instead of waiting for a breakout of the neckline, place limit buy orders in the right shoulder area (neckline support zone).
  - Stop loss must be placed immediately below the neckline boundary; target is the next major resistance.

---

## How this relates to the wiki

- [BN Ong](../entities/bn-ong.md): Speaker of this transcript, developer of the TAT systems and metal swing analyses.
- [Wash and Rinse](../concepts/wash-and-rinse.md): Validates retests of wash/rinse zones on H4 charts.
- [Forex Trading](../concepts/forex-trading.md): Analyzes JPY pair breakouts and AUDUSD neckline structures.

## Open questions

- What is the exact price feed calculation for the gold 4471 resistance line mentioned in the transcript?
- Does copper's cup and handle breakout have a specific ATR volatility filter to confirm the breakout?

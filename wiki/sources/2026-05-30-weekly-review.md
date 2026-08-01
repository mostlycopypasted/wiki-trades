---
type: transcript
date: 2026-05-30
ingested: 2026-06-03
status: read
raw: ../../raw/Weekly-Review-bd627ad9-dace_20260530.md
---

# Weekly Review — 30th May 2026

> Weekly meeting transcript of BN Ong (Bini) discussing stocks, indices, forex, commodities, and cryptos, focusing on the TAT trading systems, email signal screening, and automated portfolio execution.

## Ingested Instruments List

1. **[NASDAQ](../entities/nasdaq.md) (or [QQQ](../entities/qqq.md) ETF)**:
   - **Key Levels**: Broke above the highs of two valid weekly Dojis (formed at the equidistance channel high). Healthy trend angle of 45-50 degrees.
   - **Direction**: Bullish (continuation).
2. **[IGV](../entities/igv.md) (Software ETF)**:
   - **Key Levels**: Bouncing off support levels (~90-91 signal price to ~101 current price) after a correction, rotating money from semiconductors into software.
   - **Direction**: Bullish.
3. **[NTAP](../entities/ntap.md) (NetApp)**:
   - **Key Levels**: First appeared in the TAT scan at 112, now trading up 60% around 180, supported above aligned weekly moving averages.
   - **Direction**: Bullish.
4. **[CRWD](../entities/crwd.md) (Crowdstrike)**:
   - **Key Levels**: Signal triggered at 527; current price is 725 (up 37%).
   - **Direction**: Bullish.
5. **[PANW](../entities/panw.md) (Palo Alto Networks)**:
   - **Key Levels**: Triggered bullish signals; currently up 32% since detection.
   - **Direction**: Bullish.
6. **[DELL](../entities/dell.md) (Dell)**:
   - **Key Levels**: Consolidated at a base above the two weekly moving averages, then had a 45% blowout move on Q1 earnings.
   - **Direction**: Bullish.
7. **[XAUUSD](../entities/xauusd.md) (Gold)**:
   - **Key Levels**: Volatility dampening zones at 4639 and 4674. 62% Fibonacci retracement level of the macro up-move. H1 chart inverted head-and-shoulders zone.
   - **Direction**: Bullish continuation once support holds, or Range Bound.
8. **[HSI](../entities/hsi.md) (Hang Seng Index)**:
   - **Key Levels**: Critical last support level at 24,800. Key resistance on the H1 chart. Downtrend targets at 22,000 and 23,000 if support breaks.
   - **Direction**: Bearish if 24,800 support is broken.
9. **[USDJPY](../entities/usdjpy.md)**:
   - **Key Levels**: Flattish price action with MACD heading down on lower timeframes (hidden divergence).
   - **Direction**: Bullish (weakening JPY / rising USDJPY).
10. **[AUDUSD](../entities/audusd.md)**:
    - **Key Levels**: Flat structure but MACD correcting down, indicating Aussie strength continuation.
    - **Direction**: Bullish.
11. **[DXY](../entities/dxy.md) (Dollar Index)**:
    - **Key Levels**: Flat trading range. Look for execution only at the range extremes, not in the middle.
    - **Direction**: Neutral / Range Bound.
12. **[BTCUSD](../entities/btcusd.md)**:
    - **Key Levels**: Closed the week below the first key support level. Requires a massive spike down (liquidity sweep) to flush out weak players before a reversal.
    - **Direction**: Bearish / Weak.
13. **[ETHUSD](../entities/ethusd.md)**:
    - **Key Levels**: Weak recovery, already broken down in other price feeds.
    - **Direction**: Bearish / Weak.
14. **[FUNUSD](../entities/funusd.md) (Altcoin)**:
    - **Key Levels**: Purchased at 0.07, went up to 66 (average exit 60), now crashed.
    - **Direction**: Bearish (characterized as a pump-and-dump scan).

---

## Technical Trading Rules Emphasized

- **Rule 1: Weekly Signal Supremacy for Stocks**: Weekly signals are vastly more reliable and profitable in stocks than daily signals, with an average unfiltered watch list win rate of ~64% (due to capturing macro corporate quarterly trends).
- **Rule 2: Volatility Decay (Ball Theory)**: High-volatility zones (like in gold) behave like a dropped ball, showing dampening bounces to unwind energy and flush out weak retail hands before starting a clean trend.
- **Rule 3: Extreme Range Execution in Flat Markets**: In highly range-bound markets (like DXY), ignore signals or setups in the middle of the range. Only trade at the support/resistance extremes.
- **Rule 4: Crypto Reversals Require Liquidity Sweeps**: A crypto asset cannot establish a sustainable bottom without a violent spike down (stop-hunt/flush-out) to clean the order book of leveraged longs.

---

## Pine Script Accumulation & Wash and Rinse Overlap

These techniques are documented to construct a comprehensive Pine Script indicators/trading system:

### 1. The TAT Consolidation Detector (Cup & Handle Core)
* **Logic**: Detects the end of a base or consolidation before a breakout.
* **Pine Script Strategy Implementation**:
  - Filter signals to ensure the shorter Moving Average is above the longer Moving Average (e.g., EMA 20 > EMA 50) and both are sloping upward.
  - Scan for a period where price moves sideways (low volatility, flattish ATR) and pulls back close to the moving averages without crossing below them.
  - Trigger a buy when the price closes above the local consolidation channel high.
  - *Filtration Tip*: Turn off Moving Average filters for the *first detection* of the base, but turn on the Moving Average filter for *entries* to capture momentum.

### 2. MACD Hidden Continuation Divergence
* **Logic**: Price is flattish or consolidating, but MACD is actively moving in the opposite direction (correcting down in an uptrend, or up in a downtrend).
* **Pine Script Strategy Implementation**:
  - Detect flat price structure: standard deviation of close over $N$ bars is below a threshold, or ATR is low.
  - Scan for MACD line or histogram making lower lows while price makes equal or higher lows.
  - Trigger a continuation long signal when MACD reverses upward while price remains above key support.

### 3. Wash and Rinse (WR) Liquidity Overlap
* **Logic**: Sweeping key lows/highs to trigger stops before reversing.
* **Pine Script Strategy Implementation**:
  - Identify a key swing low/high on H1 or H4 charts.
  - **The Sweep**: Price spikes below the key swing low (creating a long wick).
  - **The Close (Wash Line)**: The bar must close back *above* the swing low level (the Wash Line).
  - **The Confirmation (3-Bar Rule)**: Bar 0 is the sweep, Bar 1 is a minor breakout/retest, and Bar 3 must confirm the upward shift by closing above Bar 1's high.
  - Combine with the MACD hidden divergence and the TAT moving average alignment to filter out fake sweeps.

---

## How this relates to the wiki

- [BN Ong](../entities/bn-ong.md): Speaker of this transcript, developer of the TAT systems and weekly screening protocols.
- [Wash and Rinse](../concepts/wash-and-rinse.md): Leverages liquidity sweeps. This transcript adds MACD hidden divergence overlap and volatility decay.
- [Autonomous Trading](../concepts/autonomous-trading.md): Discusses python execution scripting, telegram alerts, and Google Sheets portfolio integrations.
- [Forex Trading](../concepts/forex-trading.md): Details JPY MACD setups and flat market rules.

## Open questions

- How does the TAT target profit (TP) calculator dynamically select which pivot breakout determines the target level?
- What are the exact parameters of the moving averages used in the weekly stock filter scans?

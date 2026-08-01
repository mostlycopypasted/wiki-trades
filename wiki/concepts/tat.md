---
kind: concept
tags: [trading, technical-analysis, setup, momentum]
updated: 2026-06-27
sources: 6
---

# TAT

## Definition

TAT (officially correcting previous transcript variations like TAG, TED, or TAD) is a proprietary technical analysis trading system and dashboard developed by [BN Ong](../entities/bn-ong.md) that utilizes horizontal breakout levels, support/resistance zones, and moving average filters to identify high-probability multi-asset reversals and trend continuations.

## Origin

Developed by [BN Ong](../entities/bn-ong.md) to convert manual multi-asset chart strategies into automated screeners. It is implemented both as TradingView custom scripts and as a web-based alert dashboard (such as TAT V2) to track forex, commodities, indices, and stocks.

## Key claims

- **TAT Horizontal Levels**: The core of the system relies on drawing static horizontal levels—specifically orange lines to mark turning points/retracements and red/green lines to define the boundaries of key support and resistance zones. (see [Weekly Review (Access Time) — 2nd June 2026](../sources/2026-06-02-weekly-review.md))
- **EMA-Filtered Dashboard (TAT V2)**: The V2 dashboard introduces default filters utilizing the 21 EMA (short-term) and 133 EMA (long-term). Bullish signals are filtered to display only when price is above both EMAs, and bearish signals only when price is below both, significantly reducing signal noise. (see [TAW Pro — 3rd June 2026](../sources/2026-06-03-tat-pro.md))
- **Unfiltered Scanning for Deep Reversals**: Disabling the EMA filter allows the dashboard to display all raw signals. While filtered scans are optimized for gentle pullbacks off a rising base, unfiltered scans are required to capture high-yield, deep-reversal momentum setups that occur when price is far below the 20/21 EMA. (see [TAW Pro — 3rd June 2026](../sources/2026-06-03-tat-pro.md))
- **The "1+1" Reversal Confirmation**: Designed for short-term H1/M15 scalping and fine-tuning. A valid reversal is confirmed when price closes above/below a horizontal TAT level and simultaneously crosses the short-term 20/21 EMA, providing a confluence of static price level and dynamic momentum. (see [TAW Pro — 3rd June 2026](../sources/2026-06-03-tat-pro.md))
- **Watchlist-Alert Creation Constraints**: Alerts built on TradingView watchlists lock in the parameters (such as the EMA filters) active at the moment of alert creation. Modifying chart indicators or dashboard filters after creation will not update the active alert; it must be deleted and re-created to apply new rules. (see [TAW Pro — 3rd June 2026](../sources/2026-06-03-tat-pro.md))
- **20/133 Moving Average Confluence**: When the short-term 20 MA and long-term 133 MA merge or flatten together, they form a highly potent support/resistance zone indicating heavy trend boundaries (e.g. EURUSD). (see [AHH Access Time — 3rd June 2026](../sources/2026-06-03-ahh-access-time.md))
- **Structural Confluence ("1+1 = 2")**: Trend bar colors show structural shifts (Green = higher highs/higher lows, Red = lower highs/lower lows). Executing a trade signal matching the trend bar color yields a "two" (confluence of signal + macro structure) for maximum confidence, whereas opposite pairings are only a "one". (see [AHH Access Time — 3rd June 2026](../sources/2026-06-03-ahh-access-time.md))
- **Community Alert Scaling**: Community watchlist signals (under "Ted" indicators) can be aggregated and distributed via a VPS automated scraper to bypass TradingView's premium account cost barriers. (see [Weekly Review — 6th June 2026](../sources/2026-06-06-weekly-review.md))
- **Lower-Timeframe Retracement Entry alert**: High-probability setups (like shorting EURUSD) are entered by placing alert lines slightly below H4 horizontal resistance zones, then using the H1 timeframe to execute short trades when price tests the zone and matches the bearish continuation pattern. (see [Weekly Review — 6th June 2026](../sources/2026-06-06-weekly-review.md))
- **Month-End Close Significance**: Large structural trend shifts (like WTI Crude Oil breaking a 4-year correction) require validation on the monthly close rather than daily/weekly charts. (see [Weekly Review Binni 2026-03-07](../sources/2026-03-07-weekly-review-binni.md))
- **Support Retest Confirmation**: Favour long entries on pullbacks/retracements to horizontal key zones instead of chasing breakouts. (see [Weekly Review Binni 2026-03-07](../sources/2026-03-07-weekly-review-binni.md))
- **Unfiltered Scanning Stance**: Scanning the wider pool of raw setups using unfiltered alerts and manually choosing confluences yields higher flexibility. (see [Weekly Review 2026-06-13](../sources/2026-06-13-weekly-review.md))

## Related concepts

- [Autonomous Trading](../concepts/autonomous-trading.md) — Gating automated execution behind dashboard signals.
- [Wash and Rinse](../concepts/wash-and-rinse.md) — Reversal confluences at liquidity sweep boundaries.
- [Trading Confluence](../concepts/trading-confluence.md) — Combining horizontal price levels with dynamic moving averages.
- [Pine Script](../concepts/pine-script.md) — Translating TAT mathematical rules into TradingView strategy scripts.

## Sources

- [Weekly Review (Access Time) — 2nd June 2026](../sources/2026-06-02-weekly-review.md)
- [TAW Pro — 3rd June 2026](../sources/2026-06-03-tat-pro.md)
- [AHH Access Time — 3rd June 2026](../sources/2026-06-03-ahh-access-time.md)
- [Weekly Review — 6th June 2026](../sources/2026-06-06-weekly-review.md)
- [Weekly Review Binni 2026-03-07](../sources/2026-03-07-weekly-review-binni.md)
- [Weekly Review 2026-06-13](../sources/2026-06-13-weekly-review.md)

## Timeframe Reconciliation
When reconciling TAT trend signals across timeframes (e.g., an H4 downtrend but an M15 uptrend), traders assume the lower timeframe is a retracement wave moving toward an optimal entry point to resume the higher timeframe's dominant structure. Additionally, the **recency effect** dictates that the most recent, smaller wave is followed until it breaks, at which point the macro wave regains control (see [TAW Pro (2026-07-01)](../sources/2026-07-01-taw-pro.md)).

## Technical Trading Rules
- **Timeframe Hierarchy**: Always rely on higher timeframe trends while trading short-term impulse waves for quality trades.
- **Confluence Analysis**: Combine TAT signals with traditional historical support/resistance levels for better trade decisions.
- **Trend Bar Interpretation**: If downtrend bars appear on most timeframes while only lower timeframes show uptrend, the higher timeframe downtrend is the determined trend.
- **Wait for Confirmation**: Before entering bullish trades, wait for TAT signals to confirm trend changes; don't trade prematurely when support holds.
- **Support/Resistance Tests**: It's the test of resistance that matters, not just the break; price may hit resistance and reverse.

## Related Concepts
- [Retest Execution](../concepts/retest-execution.md)
- [Wash and Rinse](../concepts/wash-and-rinse.md)
- [Market Structure](../concepts/market-structure.md)


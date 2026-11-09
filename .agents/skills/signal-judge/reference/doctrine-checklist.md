# Signal Judge doctrine checklist

The rules the judge cites by id (`R01` …). Each ends with its source: `claim N` is the N-th bullet (or numbered item) under that page's `## Key claims`. Ids are permanent: a rule that is retired keeps its id and is marked *(retired)*; a new rule takes the next free id. `scratch/check_signal_judge.py` checks that every citation resolves.

Scope reminder: the judge sees forex on the 4H and gold, silver, WTI oil and indices on the 1H only (user decision 2026-11-03).

## Signal strength
- **R01** Rank by tier: `OptBull`/`OptBear` > `LBull`/`LBear` > `SBull`/`SBear`, and a Tflow keeps its tier (`Tflow OptBull` > `Tflow LBull` > `Tflow SBull`). — (see [Tflow](../../../../wiki/concepts/tflow.md) claim 2)
- **R02** A Tflow whose pullback low (bear: high) sits in a Weekly/Monthly D-Zone (`@Zone`) is the stronger setup; a plain signal that doesn't trace the pattern is just a signal. — (see [Tflow](../../../../wiki/concepts/tflow.md) claim 3, claim 9)
- **R03** Tflow is the indicator's own retest entry: don't buy the impulse, take the trend signal that fires when the pullback finishes. — (see [Tflow](../../../../wiki/concepts/tflow.md) claim 8)
- **R04** The same pattern on the 4H is a longer, more trustworthy signal than on the 1H. — (see [TAT](../../../../wiki/concepts/tat.md) claim 15)

## Retest rules per timeframe (a scoped pair: apply the one that matches the signal's timeframe)
- **R05** 4H (and higher) breakouts: wait for the retracement retest; the retest, not the break, is what matters, and chasing the breakout bar widens the stop. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 2, claim 6, claim 17)
- **R06** 1H signals carry no retest requirement: entering on the signal ("I choose to jump") is allowed. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 16)
- **R07** Never chase the breakout bar when adding or entering a strong trend; wait for the pull back into the structural line. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 8)

## Higher-timeframe permission and structure
- **R08** A signal that matches the trend bar colour (green = HH/HL, red = LH/LL) is the "1+1 = 2" structural confluence; trading against it needs a reason. — (see [TAT](../../../../wiki/concepts/tat.md) claim 8)
- **R09** An uptrend stays intact while swings make higher highs and higher lows; buy retracements into the higher-low zone (mirror for downtrends). — (see [Market Structure](../../../../wiki/concepts/market-structure.md) claim 1, claim 2)
- **R10** A close past the latest higher low (uptrend) or lower high (downtrend) invalidates the structure: that swing is the stop. — (see [Market Structure](../../../../wiki/concepts/market-structure.md) claim 3)
- **R11** A downtrend is not over until price closes back above the red line; a bounce off support is not a reversal. — (see [Market Structure](../../../../wiki/concepts/market-structure.md) claim 7)
- **R12** A red/orange TAT line in an intact uptrend is a place to buy the break; in a downtrend it is a place to short the retracement. — (see [TAT](../../../../wiki/concepts/tat.md) claim 17)

## Location, room and risk
- **R13** A signal right under resistance (above support for a short) leaves little reward: take it only with a tight stop just beyond the level so the trade is at least 1:1. — (see [Wash and Rinse](../../../../wiki/concepts/wash-and-rinse.md) claim 28)
- **R14** Don't trade into a target: as price approaches a long-standing TP, expect a retracement there, not continuation. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 18)
- **R15** "No more room": price pinned near a structural boundary with little space to the next level is due to stall or flip. — (see [Market Structure](../../../../wiki/concepts/market-structure.md) claim 19)
- **R16** Enter on the lower-timeframe retest to sit at 1–2 on Binni's 1–10 risk scale (1 = support bottom, 10 = resistance top); a late entry near 10 is poor. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 4)
- **R17** D-Zones with a higher `xN` count, or spanning both W and M, are stacked confluence and natural take-profit or stop references. — (see [D-Zones](../../../../wiki/concepts/d-zones.md) claim 7)
- **R18** A tail does not break a level; only a solid close beyond it does. — (see [Wash and Rinse](../../../../wiki/concepts/wash-and-rinse.md) claim 36)
- **R19** A late re-entry after a missed breakout has no profit cushion; treat it as lower quality. — (see [Market Structure](../../../../wiki/concepts/market-structure.md) claim 17)

## Wash & Rinse (not machine-checked in v1: wash-line prices aren't read)
- **R20** A TAT signal or a W&R alone is an earlier entry; both together give higher confidence. — (see [TAT](../../../../wiki/concepts/tat.md) claim 18)
- **R21** A bullish W&R after a V-shaped fall (no base, no higher high, no TAT level broken) is low probability. — (see [Wash and Rinse](../../../../wiki/concepts/wash-and-rinse.md) claim 26)

## News, calendar and timing
- **R22** Before a high-impact event, read TAT for whether price is being supported or resisted; only a surprise moves the market, so an entry right before a Red Folder release carries event risk. — (see [TAT](../../../../wiki/concepts/tat.md) claim 14)
- **R23** Don't chase a late-week trigger at the low: a Friday signal with price already at a local extreme waits for a lower-timeframe retracement. — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 12)
- **R24** In choppy, indecisive conditions conserve capital: "don't anyhow fire". — (see [Retest Execution](../../../../wiki/concepts/retest-execution.md) claim 9)

## Scope
- **R25** Timeframe per class: forex is judged on the 4H; gold, silver, WTI oil and indices on the 1H. — (user decision 2026-11-03; see [Signal Judge design](../../../../docs/design/signal-judge.md) "User decisions")

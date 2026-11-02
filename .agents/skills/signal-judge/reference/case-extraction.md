# Case extraction

Turn one session note into a JSON array of cases: one case per concrete call Binni makes about an
instrument. Write the array to scripts/signal_judge_runs/cases_<note-stem>.json (create the folder if needed). Do NOT run add
yourself when you are a backfill subagent; the session that started you runs add for each note,
one at a time. In an ingest session, run:
python3 scripts/signal_cases.py add --presenter <binni|pauline|unknown> --note "<note path>" --file <that file>

## Presenter
Cases keep whoever presented the session (user decision 2026-11-02: Pauline's calls are kept and
tagged, not dropped). Read the note's header: its "> **Presenter**:" line, or "Pauline leads ...",
"Single-presenter (Pauline)". Fireflies labels every speaker "Binni Ong", so trust the note's
conclusion, not that label. binni = Binni speaks first-person; pauline = Pauline presents (often on
Binni's behalf); unknown = the note says it's unclear or probable only (e.g. "probably the co-host",
"speaker is unnamed"). A backfill subagent reports the presenter per note; the session running add
passes it.

## What is a case
A statement by Binni about a specific instrument that says, or clearly implies, what to do or not
do: trade it now, wait for a pullback, only trade if X, watch it, avoid it, or "it already went".
One instrument can yield several cases if she makes different calls (e.g. on two timeframes).
Not a case: background commentary with no action ("the dollar is strong"), the user's own
questions, or general rules (those belong in the doctrine checklist). A note with no calls → [].
A mention that supports another call (e.g. "EURNZD already moved", said to explain why GBPNZD is
the laggard) IS a case of its own when it states a call (already_moved).

## Fields (note, date, session_type and id are filled in by the script; leave them out)
- opportunity_no: the number of the item in the note's opportunities section ("## ... Opportunit..."),
  else null. If the note has no such section, always null.
- section: the heading text the call sits under.
- instrument: the ticker as bracketed in the note (the script canonicalises it).
- asset_class: fx | metal | index | crypto | stock | commodity.
- tf: the timeframe the call is about (m15 | 1h | 4h | d | w | m), else unspecified.
- direction: long | short | neutral.
- verdict:
  - take: she would enter now or names it her trade ("my preferred short", "best candidate for a long").
  - wait_retest: direction is right but she wants a pullback/retest of a level before entering.
    condition = the level or pullback she wants.
  - conditional: entry only if a stated future event happens that is not a pullback (a close
    above X, a break of a support, a clear move above a zone). condition = that event.
  - watch: interesting, no trade yet, and no concrete trigger given ("not yet", "keep an eye on").
  - skip: she would not trade it or says to avoid it.
  - already_moved: the move has happened; too late to enter.
  Rule of thumb: a concrete trigger → conditional (or wait_retest if the trigger is a pullback);
  no trigger → watch.
- condition: required for conditional and wait_retest; null otherwise unless she adds one.
- setup (any that apply): breakout (price broke a level/zone), retest (back at a broken level),
  trend_continuation (with an existing trend), pullback_in_trend (a dip inside a trend), reversal
  (trend change), range_bounce, range_break, trendline_break, pattern_hs (head and shoulders,
  incl. inverted), pattern_double (double top/bottom), tflow (a Tflow pattern), laggard (expected
  to follow a theme its sibling pairs already moved on), leader (the pair that moved first).
- location (relative to the trade direction; "behind" = support for a long, resistance for a
  short): htf_level_behind, htf_level_ahead, at_d_zone (a Weekly/Monthly D-Zone), open_space (no
  level close ahead), mid_range, at_wash_line, at_ema.
- structure (relative to the direction): with_trend, counter_trend, range, transition (trend
  changing), unspecified.
- htf: aligned | opposed | ambiguous | unspecified — the higher timeframe vs the direction.
- risk_flags (any): news_pending (an event she mentions), ugly_chart, friday (late-week trigger),
  late_entry, room_consumed (much of the move already gone), counter_trend, intervention_risk.
- signal_named: a TAT/Tflow label she names (OptBull, Tflow LBull, ...), else null.
- levels: key levels as written in the note, else null.
- quote: copy a phrase from the note exactly (2+ words, ≤ 300 chars). Prefer her quoted words; otherwise the
  note's sentence about the call. The script rejects quotes it cannot find in the note.
- timestamp: the [mm:ss–mm:ss] range nearest the quote, else null.
Use only what the note says. Don't infer tags the note doesn't support; leave lists empty and use
unspecified instead.

## Worked examples (wiki/AHH Session Notes/2026-10-27-ahh-access-time.md)
Item 1, GBPAUD:
{"opportunity_no": 1, "section": "📈 Trading Opportunities", "instrument": "GBPAUD",
 "asset_class": "fx", "tf": "4h", "direction": "short", "verdict": "take", "condition": null,
 "setup": ["trendline_break", "trend_continuation", "laggard"], "location": ["htf_level_behind"],
 "structure": "with_trend", "htf": "aligned", "risk_flags": [], "signal_named": null,
 "levels": "Resistance from higher-timeframe levels; 4H green/blue supports under a whole chunk of resistance",
 "quote": "Today the 4H broke the uptrend line, so look for a short as the continuation of the AUD strength",
 "timestamp": "29:10–29:40"}
Item 7, GBPJPY:
{"opportunity_no": 7, "section": "📈 Trading Opportunities", "instrument": "GBPJPY",
 "asset_class": "fx", "tf": "unspecified", "direction": "long", "verdict": "conditional",
 "condition": "lower timeframe shows support and a clear move above the resistance zone",
 "setup": ["retest"], "location": ["htf_level_behind"], "structure": "unspecified",
 "htf": "aligned", "risk_flags": [], "signal_named": null,
 "levels": "own resistance-turned-support; still a support level on the higher timeframe",
 "quote": "Check the lower timeframe for support and a clear move above the resistance zone",
 "timestamp": "43:53–44:20"}

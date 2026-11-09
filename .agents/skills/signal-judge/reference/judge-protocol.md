# Signal Judge — judge protocol

How a session judges a Signal Judge brief. Verbatim from `docs/design/signal-judge.md` §Judge protocol (revision 11). The slot session (or a manual Claude Code session) judges **inline**: it reads the files and writes the verdicts file itself. It does not spawn a subagent, because an unattended `claude` run cannot wait on a background subagent's notification.

Fill the placeholders from the packet `scripts/signal_judge_runs/<run_id>_packet.json`: `<CHECKLIST_PATH>` = `doctrine_checklist`, `<BRIEF_PATH>` = `brief_path`, `<VERDICTS_PATH>` = `verdicts_path`, `<RUN_ID>` = `run_id`.

```
You are the Signal Judge for a TAT/Wash & Rinse trading wiki. Rule on each signal in the brief
using the doctrine checklist, the chart features in the brief, and the precedents attached to each
signal (Binni's own past calls, as summarised in the session notes; a few were presented by
Pauline, shown as the presenter). Do not use any other source and do not invent precedents.

Read, in this order:
1. The doctrine checklist: <CHECKLIST_PATH>
2. The brief: <BRIEF_PATH>. Its title line gives the number of survivors (sections S1..SN). Read
   the whole file (Read with offset/limit if needed) and confirm you have every section.
3. For any survivor whose "Chart image" line names a file, that image (Read tool).

For EVERY survivor, decide one verdict:
- take: no blocking rule applies, the entry location is acceptable now, and the evidence supports
  the direction and setup.
- wait_retest: the setup is valid but entering now is poor (e.g. the impulse bar itself on 4H,
  room consumed > 0.5, price more than ~1 ATR from the broken level, or a controlling precedent
  says wait for the pullback). Give retest_level (prefer the broken trigger level; else the near edge of the @Zone;
  the Tflow pivot only if it is clearly inside the stop; strictly between SL and the entry) and retest_window_bars (1H: 1-12,
  4H: 1-6).
- skip: a blocking rule applies (HTF opposed, counter-trend into intact structure, Red Folder
  imminent, Binni's recent call on this instrument goes the other way or says skip), or the trade
  is not worth its risk.
- no_ruling: the evidence genuinely conflicts and the checklist does not settle it, or the
  features are too incomplete to judge. Put the question you would ask Binni in
  question_for_binni.

Basis:
- precedent: you followed at least one precedent (list it in controlling_cases, max 3).
- own_analysis: the survivor has no precedents ("None — own analysis required"), or none of its
  precedents applies (list each in distinguished with why). Then do your own analysis of the TAT
  signal itself, in this order, and cite the checklist rule for each step you rely on (at least
  two R-ids):
  1. Higher-timeframe permission: the htf bias (TAT trend on 4H for a 1H signal, Daily for a
     4H signal) and the daily brief.
  2. Signal strength: tier (Opt > L > S), Tflow, @Zone.
  3. Structure: with trend / counter / transition; break of structure on the signal bar.
  4. Location: trigger level and close quality, HTF level behind/ahead, room consumed, EMA20.
  5. Risk: SL at the elbow, R:R to TP1, Red Folder within 24 h, Friday / late entry.
  6. The chart image, if any: does it show the same picture?
  Confidence comes from how many of steps 1-5 agree: high = all clear, medium = one doubtful,
  low = two or more doubtful.

A `weekend_gap` flag (the signal bar closed before the weekend and the entry price is Monday's): lower confidence one step; it is not a skip by itself.

Confidence with precedents: high = checklist and at least two precedents agree and htf is aligned;
medium = one of those is missing; low = conflicting evidence.

What a precedent's verdict means (Binni's call at the time):
- take: she would enter. Supports take in that direction.
- wait_retest: valid, wait for the pullback. Supports wait_retest; supports take only if price has since retested.
- conditional: valid only if its `cond:` holds. Check the condition against this signal's features and say in the reason whether it is met now; if met, treat it as take; if not met or not checkable, as watch.
- watch: interest without an entry call. Supports the direction only; never a take on its own (you need the checklist to carry it).
- skip: she would not trade it. Supports skip.
- already_moved: the move had happened. Supports wait_retest or skip for a late entry, not take.
A precedent in the other direction (same_direction false) counts against this signal by the same scale.
"in transcript: no" means the quote is from the note's summary and was not found word for word in the transcript; it is still her call as summarised, weigh it the same.

Each precedent carries hindsight (a case not yet scored, `hindsight: null`, is shown as "unscored"):
(favourable / adverse / flat / unscored, with mfe/mae in ATR). It is a rough daily-bar check that
ignores the call's conditions, entries and stops, so it does not overrule the setup match. You may
follow an adverse precedent, but say so in the reason and lower your confidence one step. A
favourable precedent does not raise confidence by itself.

Precedence when sources disagree: a same-instrument call from the last 21 days ([recent]) outweighs
a similar case; a higher-similarity case outweighs a lower one; a later case outweighs an earlier
one; doctrine rules scoped to the signal's timeframe outweigh general ones.

Write <VERDICTS_PATH> as JSON exactly in this shape (no other text in the file):
{"run_id": "<RUN_ID>", "verdicts": [{"key": ..., "verdict": ..., "basis": "precedent"|"own_analysis",
 "confidence": ..., "retest_level": number|null, "retest_window_bars": int|null,
 "controlling_cases": [ids], "distinguished": [{"case_id": id, "why": text}],
 "doctrine": ["R01", ...], "reason": "<= 400 chars, no | or newlines", "dissent": text|null,
 "question_for_binni": text|null}]}
Use each survivor's key exactly as written in its section heading, one verdict per survivor, and
only case ids that appear in that survivor's precedents. Then say: "verdicts written: N of N".
```

Notes for the session:
- A wait_retest level on or just past the stop (within 0.1 ATR) is moved to stop ± 0.1 ATR by `apply` with a warning; further past it, the verdict is rejected. Prefer the broken trigger level.
- `no_ruling`: basis is `precedent` if you name any controlling case, else `own_analysis` (put conflicting precedents in `distinguished`; own_analysis still needs two R-ids).
- One verdict per key. Two verdicts for the same key reject both.
- A `weekend_gap` risk (signal bar closed before the weekend, entry price is Monday's): lower confidence one step; not a skip by itself.

---
name: signal-judge
description: The Signal Judge. Phase 1 is the Binni case store (session-note calls in wiki/notes/signal-judge/cases.jsonl, hindsight-scored, retrieved as precedents). Phase 2 is the live judge — forex 4H and metals/oil/indices 1H TAT signals are chart-read from TradingView, pre-filtered, given Binni's precedents and judged take / wait_retest / skip / no_ruling (precedent or own analysis), tracked to TP1/SL and reported. Use when running or judging the Signal Judge ("run the signal judge", the Combined-slot step), when ingesting a session note (case extraction), when asked what Binni said about a setup, or for scorecard / coverage numbers.
license: MIT
metadata:
  author: AI Trading Team
  version: "0.2.0"
  tags:
    - tat
    - signal-validation
    - session-notes
---

# Signal Judge

Two phases. **Phase 1, the case store** (`scripts/signal_cases.py`, design `docs/design/signal-cases-phase1.md`) turns Binni's calls in the session notes into quote-verified cases. **Phase 2, the live judge** (`scripts/signal_judge.py`, design `docs/design/signal-judge.md` rev 11 — read its "Revision 11 — binding decisions") rules on fresh TAT signals using those cases plus a doctrine checklist. Phase 2 sections are below the Phase 1 ones.

## Data

- `wiki/notes/signal-judge/cases.jsonl` — one case per line (schema in the design doc §1).
- `wiki/notes/signal-judge/notes_done.json` — which notes have been extracted (also those with 0 cases).
- `scripts/signal_judge_runs/` (local, gitignored) — staged extraction files and `*.rejects.json` for review.
- **Writer host**: `add` and `score` write only on the Mac mini (`writer_host` in `scripts/signal_judge_config.json`, gitignored; `pepper`). Obsidian Sync doesn't merge non-markdown files, so a single writing machine avoids lost cases. Elsewhere they exit 6 and keep the staged file; run `pending` on the Mac mini later.

## Commands

```bash
python3 scripts/signal_cases.py pending            # notes not yet extracted, newest first
python3 scripts/signal_cases.py add --presenter binni|pauline|unknown --note "wiki/AHH Session Notes/<stem>.md" --file scripts/signal_judge_runs/cases_<stem>.json [--replace]
python3 scripts/signal_cases.py score [--all]      # hindsight: 10 trading days after each call (needs note date + 14 d)
python3 scripts/signal_cases.py match --signal <signal.json>
python3 scripts/signal_cases.py coverage [--days 14] [--json]
python3 scripts/signal_cases.py stats
```

`add` exit codes: 0 stored (rejects, if any, listed in `cases_<stem>.rejects.json`); 1 note already extracted (use `--replace`); 2 unreadable staged file / note, or not a session-note filename; 3 every case rejected (nothing stored, note stays pending); 4 lock timeout; 6 not the writer host.

## Presenter

Many AHH sessions are presented by Pauline on Binni's behalf (10 of the 24 pilot notes; 2 unclear). Her calls are kept and every case carries `presenter` (`binni` / `pauline` / `unknown`), passed to `add --presenter` from the note header (see the protocol). Retrieval does not filter on it; the Phase 2 judge will see it on every precedent and decide how to weigh it.

## Extracting cases

Follow `reference/case-extraction.md` exactly. One case per concrete call; the quote must be copied from the note (the script rejects quotes it can't find). Note, date, session type and id are filled in by the script.

**In an ingest** (step 7 of `trading-transcript-ingest`, after the hot-cache rewrite and before the Fireflies deletion): extract → `add` → on exit 0, `score` and delete the staged file; on 2/3/6 keep the staged file and say so in the ingest summary (it does not block deletion: the note persists). Mention any rejects count.

**Backfill**: `pending` → subagents (≤ 5 notes each, up to 4 at once) that only write staged files → this session runs `add` per note, one at a time → `score` → `stats`.

## Coverage gate

`coverage` replays the last N days of deduped in-scope 1H/4H alerts (no chart, so tags are limited: tf, Tflow/@Zone, laggard, Daily-brief htf, Friday, Red Folder inside the calendar note's weeks) and reports how many alerts have ≥ 1 same-instrument case in the 21 days before (`instrument_recent`) or ≥ 2 similar cases that share at least one substantive tag (setup, location, structure, htf) at similarity ≥ 0.45. `GATE` = % with either; recommendation: go for Phase 2 at ≥ 60%. Check `similar_only_htf` — matches resting on the htf tag alone are weak evidence.

## Retrieval

`find_precedents(signal, cases)` in `scripts/signal_cases.py`: `instrument_recent` (same canonical instrument, ≤ 21 days before, max 3) and `similar` (top 5; must share a substantive component). Direction is not a filter; every returned case carries `same_direction`, because a recent opposite call is evidence too. Each case carries its hindsight label (favourable / adverse / flat), which the judge weighs but which does not change ranking.


---

# Phase 2 — the live judge

## What it judges
- **Forex on the 4H; gold, silver, WTI oil (`USOUSD`) and indices on the 1H** (user decision 2026-11-03). Forex 1H and non-forex 4H alerts are counted (`out_of_tf`), not judged. GER40, HK50, UK100, FRA40, CN50, USDX and the gold crosses are judged but untracked (no 24-hour Yahoo series).
- Fresh only: alerts ≤ 12 market hours old; 1H older than 6 market hours and 4H older than 12 are `STALE`.
- Weekends (Fri 17:00 → Sun 17:00 New York): `run` exits 10 (`SKIPPED weekend`).
- Bar grid: metals and gold crosses close their 1H bars at hh:01, GER40/HK50 at hh:15, everything else on the hour; forex 4H bars follow New York (02/06/10/14/18/22 SGT in US standard time). `GRID_OFFSET_MIN` in `signal_cases.py`; each run reports mismatches as ⚠️.

## Run / Judge / Apply (the slot step and "run the signal judge")
1. **Run** — `python3 scripts/signal_judge.py run` (one foreground Bash call, timeout 600000 ms). Prints `PACKET <path> SURVIVORS <n>`. Exit 10 = weekend (stop silently); 6 = not the writer host (report it); 3 both sheet tabs failed / gspread missing; 4 another Signal Judge command is running; 5 a ledger shard is corrupt. On any non-zero exit skip steps 2–3. It holds TradingView for one batch (`tv_session.sh` with an owner token; ≤ 120 s lock wait, else the pass is skipped and the alerts retry next slot) and stops it right after the reads.
2. **Judge** — if `SURVIVORS` > 0, follow `reference/judge-protocol.md` **inline in this session** (no subagent: an unattended run cannot wait on one). Read `reference/doctrine-checklist.md`, the packet's brief (`brief_path`, all sections S1..SN) and any chart image it names; write the packet's `verdicts_path` as JSON exactly as the protocol says.
3. **Apply** — `python3 scripts/signal_judge.py apply --packet <path>` (foreground, timeout 600000 ms), with or without survivors. Validates the verdicts, runs the tracker, appends the day's report section, logs and updates the weekly index. A second `apply` on the same packet prints `already applied` and does nothing.

On the MacBook use `run --dry-run --out <scratch dir>` and stop, or set `SIGNAL_JUDGE_DATA_DIR`, `SIGNAL_JUDGE_REPORT_DIR` and `SIGNAL_JUDGE_RUNS_DIR` to scratch paths for a full loop.

Other commands: `python3 scripts/signal_judge.py track` (resolve OPEN entries), `stats [--since YYYY-MM-DD] [--json]` (30-day scorecard + live precedent hit rate; read-only, any host).

## Verdicts
- `take` / `wait_retest` (with `retest_level` between SL and entry, window 1–12 bars on 1H, 1–6 on 4H) / `skip` / `no_ruling` (with a question for Binni).
- `basis`: `precedent` when it follows at least one of the survivor's precedents (`controlling_cases`); `own_analysis` when there is none that applies — the judge then works through the TAT signal itself (HTF permission, signal strength, structure, location, risk, chart) and cites at least two checklist R-ids. The scorecard keeps the two apart.
- Hindsight on a precedent is weighed, not obeyed (protocol). A `weekend_gap` flag lowers confidence one step.
- Pre-filter codes (not judged): `STALE`, `CLOSED` (market closed or the 17:00–18:00 New York break, retried), `NO_DATA` (read failed / TAT study not loaded / chart pass skipped / Tflow sheet unreadable — retried, up to 3 attempts that actually reached the chart), `NO_STOP`, `RR_LT_1`. More than 8 passes → the rest `unjudged_cap` (tracked, not judged).

## Outputs
- Ledger `wiki/notes/signal-judge/ledger-YYYY-MM.json` (writer host only, under `judge.lock`).
- Report `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md`, one `## 🕒 Signal Judge Run — [HH:MM SGT]` section per run.
- Dashboard: Signals tab → Signal Judge card + Judge column (`GET /api/judge`).
- Packets, briefs and verdicts in `scripts/signal_judge_runs/` (pruned after 90 days).

## Known limits
- The tracker uses Yahoo 1H bars from the first full hour after entry: a stop or target touched in the first partial hour is missed. Futures rolls can shift the price basis for entries that span them.
- The higher-timeframe trend is read on the forming bar (what the chart shows at judging time).
- If the Tflow extract sheet stays unreadable for hours, the held alerts go `STALE` before they are judged.
- Delayed alerts are matched to their bar by the level-cross rule (`MATCH_DELAYED_BY_CROSS`); the 2026-11-04 dry run found it agreed with time matching on 8 of 8 alerts where it found a bar (1 of 9 had no crossing bar and falls back to time).

## Orca prompt change (the user applies it)
Automation "TAT Combined 1H+4H Review" (`38849272-f13f-452c-93f3-2e3c38291d73`). Insert right after the sentence ending "…in two sequential batches (1H symbols first, then 4H symbols - tv_session.sh start, capture_tv_chart.sh per symbol, tv_session.sh stop, once per batch)." :

> Then run the Signal Judge step per `.agents/skills/signal-judge/SKILL.md` §Run / Judge / Apply: (1) `python3 scripts/signal_judge.py run` as one foreground Bash call (timeout 600000 ms). Exit 10 (weekend): skip the rest of this step silently. Exit 6: put its message in your final summary and skip the rest. Any other non-zero exit: skip the rest. (2) If it exited 0 and printed SURVIVORS greater than 0, judge them yourself, inline, following `.agents/skills/signal-judge/reference/judge-protocol.md` with the packet's brief, checklist and verdicts paths (do not spawn a subagent). (3) If it exited 0, run `python3 scripts/signal_judge.py apply --packet <path>` (foreground, timeout 600000 ms). The scripts log their own errors.

and change "After the 4H leg completes and its new-alert screenshots are captured, run the My-Watchlist 4H Screenshot Protocol" to "After the Signal Judge step, run the My-Watchlist 4H Screenshot Protocol". The disabled "06:15 AM Slot" automation (`fba46300…`) has the old step order; apply the same change only if it is ever re-enabled.

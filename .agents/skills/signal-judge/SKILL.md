---
name: signal-judge
description: The Binni case store behind the (planned) Signal Judge. Extracts every concrete instrument call Binni makes in the AHH / TAW Pro / Weekly Review / 3TT / TAR session notes into wiki/notes/signal-judge/cases.jsonl, scores each call against what price did afterwards, retrieves past calls as precedents for a signal, and replays recent 1H/4H TAT alerts to measure coverage. Use when ingesting a session note (case extraction step), when asked what Binni said about a setup like a given signal, or when checking the case store / coverage numbers.
license: MIT
metadata:
  author: AI Trading Team
  version: "0.1.0"
  tags:
    - tat
    - signal-validation
    - session-notes
---

# Signal Judge — Phase 1: the Binni case store

Phase 1 of the Signal Judge (design: `docs/design/signal-cases-phase1.md`). It turns Binni's calls in the session notes into structured, quote-verified cases so a later judge can rule on a fresh TAT signal by citing her own past calls. **Phase 2, the live judge** (pre-filter, TradingView pass, verdicts, tracking, report, dashboard), is designed separately in `docs/design/signal-judge.md` and is not built yet. Nothing here runs on a schedule or opens TradingView.

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

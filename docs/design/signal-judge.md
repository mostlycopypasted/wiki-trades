# Design: Signal Judge (Case Reporter + pre-filter)

Status: **parked** after revision 5 (2026-11-02). The user split the work: Phase 1, the case store, is `docs/design/signal-cases-phase1.md`; this doc becomes the starting point for Phase 2 (the live judge). Round-5 findings still open for Phase 2 are listed in Phase 1's "Out-of-scope follow-ups". Written on the Mac mini (`pepper`) · origin: `/eg-brainstorm` → "Case Reporter + pre-filter" pick, then `/eg-new-feature` scope answers (below). Revision log at the end.

## Why

A fired 1H/4H TAT alert is not a trade. Today nothing turns the doctrine in the wiki (TAT, Tflow, Wash & Rinse, D-Zones, multi-timeframe, retest execution) into a consistent take / wait / skip call per signal, so the user decides by eye, sometimes at FOMO 3+ (journal: AUDUSD opened 13:19, 18 min after the 13:01 report).

The one existing attempt, `h4-signal-validation` (`scripts/validate_h4_signals.py`), is a rules-only judge: six hard gates + a 0–10 score, 4H FX only, on demand. It was run once (2026-09-19), rejected 7/7 signals, every score was capped by a 37-day-stale Daily brief, and its 7 forward watches are still `OPEN` because nobody ran `--track`. Lessons carried into this design:

1. Hard gates must be few and mechanical; judgment belongs to a judge that can weigh conflicting doctrine.
2. The best available record of Binni's judgment is her own calls as captured in the session notes, not the concept pages (which generalise and contradict themselves, e.g. `wiki/concepts/retest-execution.md` claim 16 "H1: no retest needed" vs claims 2/6/17 "wait for the retest"). The notes are Claude's summaries of the transcripts, so a case is "Binni's call as summarised"; §1's quote checks say how far that is verified.
3. Measurement must run with no human step.

User decisions (this conversation):
- Instruments: **FX + metals + indices** (2026-11-01). Instruments the tracker cannot follow (no 24-hour Yahoo series) are **judged but marked untracked** (2026-11-02).
- Output: **own report + dashboard**; the TAT alert report is untouched (matches the 2026-10-12 "one home per output" decision) (2026-11-01).
- Outcome scoring: **TP1 vs SL, plus MFE in R** (2026-11-01).
- Phasing: **full loop, on-demand first**; the Orca prompt change is written here and in the skill, applied by the user after a few good manual runs (2026-11-01).
- Machines: **`wiki/` syncs between the MacBook and the Mac mini (Obsidian Sync); the Mac mini is the only writer of the ledger and the daily report**; MacBook manual runs are dry runs unless the user says otherwise (2026-11-02). Whether `.json`/`.jsonl` files sync is being tested now (`wiki/notes/signal-judge/sync-test.jsonl`, written on the Mac mini 2026-11-02 14:02 SGT); §Data contract has the contingency.
- Slot order: **the judge runs right after the 4H leg and its new-alert screenshots**, before the My-Watchlist sweep and the 4H currency-strength scan (2026-11-02).
- **No Signal Judge step in the 17:01 slot** (2026-11-02). The Orca automation "Equity News — Asian" (Mon–Sat 17:30 SGT) is the user's scan for signals on Asian stocks after the SGX/HKEX close; it keeps its slot unchanged. The 17:01 slot already runs long, and a judge pass would compete with that scan for the TradingView lock. The 17:01 slot's 4H alerts are picked up by the 21:01 run (fresh for 12 market hours); most of its 1H alerts will be `STALE` by then and only counted.
- **Hindsight labels are shown, and the judge weighs them** (2026-11-02): every precedent carries favourable / adverse / flat; the judge may follow an adverse precedent but must say so and lowers its confidence one step; retrieval ranking ignores hindsight.

Facts checked on the Mac mini (2026-11-02):
- The repo here is the canonical copy (`main` 11 commits ahead of `origin`, nothing behind). `scripts/validate_h4_signals.py`, `report_toc.py`, `append_log.py` and the Tflow fold-in in `fetch_google_sheet.py` (`TFLOW_PERIOD_BY_GID`, `_extract_tflow_rows`) are committed here. The `h4-signal-validation` skill folder exists only on the MacBook.
- The Combined review is one Orca automation, "TAT Combined 1H+4H Review" (`38849272`, `rrule: 1 6,9,13,17,21 * * *`): **06:01, 09:01, 13:01, 17:01, 21:01 SGT, every day including weekends**. The separate "06:15 AM Slot" automation is disabled. AGENTS.md still says 06:15 (pre-existing drift; corrected under Docs).
- Other Orca automations that use TradingView: Daily Brief 05:01, Daily Signals 05:45, Equity News — US/EU 04:31, Equity News — Asian 17:30 Mon–Sat, Central Bank Statement Ingest (no TradingView).
- Writer host LocalHostName: `pepper`.

## Scope

In:
1. **Case store**: every concrete instrument call in the session notes (AHH Access Time, AHH Session, TAW Pro, Weekly Review and 3TT under `wiki/AHH Session Notes/`, plus TAR Session and older 3TT notes under `wiki/sources/`) extracted once into structured cases, then on every such ingest; each case scored against what price did afterwards (hindsight).
2. **Pre-filter + feature extractor** for new 1H and 4H alerts (Telegram tabs gid 0 and 1105950672, including the Tflow rows from the TAT Alert Extract_v2 sheet). Signal bars, levels and trend state are read from TradingView itself (exact Eightcap bars), reusing the timeframe-agnostic helpers in `validate_h4_signals.py`.
3. **Precedent retrieval**: deterministic tag similarity between each surviving signal and earlier cases.
4. **Judge**: one subagent per run, guided by a new `signal-judge` skill, rules take / wait_retest / skip / no_ruling for up to 8 survivors.
5. **Ledger + forward tracker**: every tracked alert is followed to TP1 / SL / expiry with R and MFE/MAE in R, on Yahoo 1H bars.
6. **Report**: `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md`, one appended section per run.
7. **Dashboard**: read-only `/api/judge` + a "Signal Judge" card and a Judge column on the Signals tab.
8. **Docs**: AGENTS.md rule edits, new skill, ingest-skill step, TAT-skill step, weekly index.

Instrument classes:

| Class | Instruments | Judged | Tracked |
|---|---|---|---|
| fx | 6-letter pairs of AUD NZD GBP EUR USD CAD CHF JPY SGD CNH (`is_in_scope`) | yes | yes (Yahoo `<SYM>=X`) |
| metal | XAUUSD (GC=F), XAGUSD (SI=F) | yes | yes |
| index | NDQ100 (NQ=F), SPX500 (ES=F), US30 (YM=F), US2000 (RTY=F), JPN225 (NIY=F) | yes | yes |
| untracked | GER40, HK50, UK100, FRA40, CN50, USDX, XAUJPY, XAUAUD, XAUGBP | yes | no: outcome `UNTRACKED` (no 24-hour Yahoo series — `^FTSE`/`^GDAXI`/`^HSI` carry 7–9 cash hours; `DX=F`/`FDAX=F` return nothing; checked 2026-11-01) |

Everything else in the tabs (crypto, oil, copper, stocks, other crosses) is counted as out of scope and not recorded.

Out (v1):
- Order placement of any kind.
- Daily-timeframe signals (Daily Signals owns them).
- Wash-line prices and D-Zone boxes for non-Tflow signals: the CLI's `getPineLines`/`getPineBoxes` round prices to 2 decimals (`~/tradingview-mcp/src/core/data.js:371`, `:443`). v1 passes `wash_lines: null` and uses D-Zones only from the Tflow `@Zone` alert text.
- New chart screenshots: the judge reuses those the slot already captured (§4).
- Any change to `validate_h4_signals.py` or `scan_fake_breakout_setups.py` (imported only).
- Moving the existing slots for winter time (Related finding).

### Related finding (not built here)

US daylight saving ended 2026-11-01. In summer the sheet's FX 4H alerts land at 01/05/09/13/17/21 SGT (bars anchored on the 17:00 New York FX open); metal and index 4H alerts were observed at 02, 10, 14, 18 and 22 SGT plus index alerts at 05 (a short session-end bar). These move one hour later in SGT from 2026-11-02 if, as the evidence suggests, TradingView anchors on New York time. The 09:01/13:01/17:01/21:01 slots, `ANCHOR_4H` in `scan_fake_breakout_setups.py:45` and AGENTS.md's "Forex closes 05:00 SGT" lines assume summer time. This feature reads bars from TradingView and measures entry at run time, so it doesn't depend on them; the user decides separately whether to move the slots.

## Surfaces touched

New:
- `scripts/signal_judge.py`: run / apply / track / stats.
- `scripts/signal_judge_stats.py`: the scorecard function shared by the report, `stats` and the dashboard (§9).
- `scripts/tv_judge_pass.mjs`: one Node process reading bars, TAT labels, study values, quote and chart state for a list of symbol × timeframe pairs (§4).
- `scripts/signal_cases.py`: case store CLI (pending / add / score / match / coverage / stats) and `find_precedents()`.
- `scripts/signal_judge_config.json` (gitignored, per machine): `{"writer_host": "pepper"}` on the Mac mini.
- `.agents/skills/signal-judge/SKILL.md`, `reference/doctrine-checklist.md`, `reference/case-extraction.md`.
- `scratch/check_signal_judge.py`: fixture checks (scratch/ is gitignored).
- Data in `wiki/notes/signal-judge/`: `cases.jsonl`, `notes_done.json`, `ledger-YYYY-MM.json` (monthly shards). Local per machine: `scripts/signal_judge_runs/` (packets, briefs, verdicts, staged case files).

Changed:
- `scripts/tv_session.sh` (defaults unchanged for every other caller):
  - `LOCK_MAX_WAIT_SECS=${TV_LOCK_MAX_WAIT_SECS:-600}`.
  - `TV_LOCK_FAIL_ON_TIMEOUT=1`: a lock wait that runs out prints the holder and `exit 75` without launching or touching the lock (today `tv_session.sh:77-80` returns 0 and proceeds).
  - `TV_LOCK_OWNER=<token>`: `start` writes `owner=<token>` into `$LOCK_DIR/info`; `stop` with `TV_LOCK_OWNER` set quits TradingView and releases the lock only if the lock's `owner` equals the token, else prints `not the lock owner; leaving TradingView alone` and exits 0. Without the variable, `stop` behaves as today.
- `scripts/update_weekly_index.py`: `scan_reports_for_date()` gains a Signal Judge block and `extract_report_summary()` an `r_type == "signal_judge"` branch.
- `dashboard/wiki_data.py` (`signal_judge(since, until)`), `dashboard/server.py` (route), `dashboard/static/app.js` (+ `style.css` for verdict badges).
- `.gitignore`: `scripts/signal_judge_runs/`, `scripts/signal_judge_config.json`.
- `AGENTS.md`, `.agents/skills/trading-transcript-ingest/SKILL.md`, `.agents/skills/tat-alert-analysis/SKILL.md`.

Imported, unchanged:
- From `scripts/validate_h4_signals.py`: `parse_tat_levels`, `triggering_level`, `nearest_level`, `find_swings` (explicit `lookback`), `latest_swing`, `structure_from_swings`, `tat_bias`, `ema_from_bars`, `gate_convincing_close`, `gate_room_to_target`, `gate_break_of_structure`, `elbow_invalidation`, `cross_pair_consistency`, `risk_scale_position`, `is_in_scope`, `clean_symbol`, `SIGNAL_TIER`, `BULL_SIGNALS`, `TFLOW_PREFIX`. These take bar dicts `{"dt", "open", "high", "low", "close"}`.
- `fetch_with_service_account` from `scripts/fetch_google_sheet.py` (the service-account route that folds in Tflow rows; the public-CSV route in `fetch_sheet_records` would not), as `dashboard/wiki_data.py:1124` already does.
- `upsert_toc` from `scripts/report_toc.py`; `scripts/append_log.py` and `scripts/update_weekly_index.py` as subprocesses.

Git: this Mac mini checkout already contains every dependency above (committed). New files and edits are committed here with this feature (the commit step asks).

External services: Google Sheets (existing service account), Yahoo chart API (unauthenticated; tracking, market-open check, hindsight), TradingView Desktop via its CDP bridge. No new sources.

Interpreter: plain `python3` (what Orca runs) and `.venv/bin/python3`; code is 3.9-compatible (no `X | Y` evaluated at runtime, no `match`). Node: the `node` `tv_session.sh` uses.

## Interfaces

### 1. Case store

**`wiki/notes/signal-judge/cases.jsonl`**, one JSON object per line:

| Field | Type / enum | Notes |
|---|---|---|
| `id` | str | `<note-stem>-<instrument lower>-<n>`, e.g. `2026-10-27-ahh-access-time-usdjpy-1`; `n` = 1-based order of that instrument's cases in the staged file; assigned by `add` |
| `note` | str | repo-relative path |
| `date` | `YYYY-MM-DD` | the note filename's date prefix |
| `session_type` | `ahh-access-time` \| `ahh-session` \| `taw-pro` \| `weekly-review` \| `3tt` \| `tar-session` | |
| `opportunity_no` | int \| null | numbered item under `## 📈 Trading Opportunities`, else null |
| `section` | str | the `##`/`###` heading text the call sits under |
| `instrument` | str | `canon_instrument()`: upper-case, strip `[[ ]]`, then the dashboard's `ALIASES` (`dashboard/wiki_data.py:109`) with these overrides/additions: `NDX`, `NAS100`, `US100`, `NASDAQ` → `NDQ100`; `S&P`, `SPX`, `US500`, `SP500` → `SPX500`; `JP225`, `NIKKEI`, `NIKKEI225`, `N225` → `JPN225`; `RUSSELL`, `RUT` → `US2000`; `DXY`, `USDX` → `USDX` (the sheet's name); `BITCOIN` → `BTCUSD`. Copied into `signal_cases.py` as a dict (not imported from the dashboard). The same function normalises sheet symbols (after `clean_symbol`). |
| `asset_class` | `fx` \| `metal` \| `index` \| `crypto` \| `stock` \| `commodity` | |
| `tf` | `m15` \| `1h` \| `4h` \| `d` \| `w` \| `m` \| `unspecified` | |
| `direction` | `long` \| `short` \| `neutral` | |
| `verdict` | `take` \| `wait_retest` \| `skip` \| `conditional` \| `already_moved` \| `watch` | Binni's call |
| `condition` | str \| null | |
| `setup` | list ⊂ {`breakout`, `retest`, `trend_continuation`, `pullback_in_trend`, `reversal`, `range_bounce`, `range_break`, `trendline_break`, `pattern_hs`, `pattern_double`, `tflow`, `laggard`, `leader`} | |
| `location` | list ⊂ {`htf_level_behind`, `htf_level_ahead`, `at_d_zone`, `open_space`, `mid_range`, `at_wash_line`, `at_ema`} | relative to the trade direction ("behind" = support for a long / resistance for a short) |
| `structure` | `with_trend` \| `counter_trend` \| `range` \| `transition` \| `unspecified` | relative to direction |
| `htf` | `aligned` \| `opposed` \| `ambiguous` \| `unspecified` | |
| `risk_flags` | list ⊂ {`news_pending`, `ugly_chart`, `friday`, `late_entry`, `room_consumed`, `counter_trend`, `intervention_risk`} | |
| `signal_named` | str \| null | |
| `levels` | str \| null | as written in the note |
| `quote` | str | ≤ 300 chars; must be found in the note |
| `quote_in_raw` | bool \| null | informational |
| `timestamp` | str \| null | e.g. `44:55–45:06` |
| `extracted_at` | ISO datetime SGT | set by `add` |
| `hindsight` | object \| null | set by `score`: `{"status": "favourable"|"adverse"|"flat"|"unscored", "mfe_atr", "mae_atr", "horizon_days": 10, "scored_at", "reason": null|"no_ticker"|"fetch_failed"|"no_bars"}` |

**`wiki/notes/signal-judge/notes_done.json`**: `{"<note-stem>": {"note": path, "extracted_at": iso, "cases": int}}`. A note is done even with 0 cases.

**Quote checks** in `add`:
- Normalise both texts: strip `[[`, `]]`, `**`, `*`, `_` and backticks; curly → straight quotes; `…` → `...`; collapse whitespace; lowercase. The normalised quote must be a substring of the normalised note, else the case is rejected.
- `quote_in_raw` (informational, never blocks): locate the transcript, in order:
  1. the note's `raw:` frontmatter, if present;
  2. else `*.md` anywhere under `raw/` (excluding `raw/recordings/`, `raw/archives/`) whose lowercased basename (with `_` and spaces turned into `-`) contains the note's date (`YYYY-MM-DD` or `YYYYMMDD`) **and** a session-type token: ahh-access-time → `ahh-access-time` | `access-time`; ahh-session → `ahh-session`; taw-pro → `taw-pro` | `tat-pro`; weekly-review → `weekly-review`; 3tt → `3-trade-thoughts` | `3tt`; tar-session → `tar-session`. (Recent transcripts sit in `raw/` root, e.g. `raw/2026-10-27-ahh-access-time.md`; older ones in `raw/AHH Sessions/`.)
  3. else, if exactly one such file has the date alone, that one; else none.
  
  `quote_in_raw` = true if, in some 400-word window of the transcript, ≥ 80% of the quote's normalised words appear in order (gaps allowed); false if a transcript was found but no window passes; null if none was found.
- This verifies fidelity to the note (Claude's summary), and only informationally to Binni's words, an accepted limit.

### 2. `scripts/signal_cases.py` CLI

All diagnostics go to stderr. Only `cases.jsonl`, `notes_done.json` and staged files are written. Env `SIGNAL_CASES_DIR` redirects the directory holding both JSON files (fixtures, tests).

```
python3 scripts/signal_cases.py pending [--json]
    Note set: wiki/AHH Session Notes/*.md and wiki/sources/*.md whose stem fully matches
    ^\d{4}-\d{2}-\d{2}-(ahh-access-time|ahh-session|taw-pro|weekly-review(-binni)?|3tt|tar-session)(-.*)?$
    (session_type = the captured group; weekly-review-binni -> weekly-review). Lists notes whose
    stem is not in notes_done.json (mtime is not used).

python3 scripts/signal_cases.py add --note "<path>" --file <staged.json> [--replace]
    staged.json = JSON array (may be empty) of case objects without id / extracted_at / hindsight /
    quote_in_raw. Validates enums and required fields, that opportunity_no (when non-null) is a
    numbered item in the note, and the quote check. If the note is already in notes_done.json:
    without --replace exit 1 ("already extracted"); with --replace its cases are replaced and
    hindsight is carried over only to a new case with the same id AND the same instrument,
    direction and verdict. Invalid cases are skipped (one stderr line each). Records the note in
    notes_done.json. Exit 0 if the staged file parsed (even with 0 valid cases), 1 already done,
    2 unreadable staged file. Writes under a local fcntl lock (cases.jsonl.lock), temp file +
    os.replace.

python3 scripts/signal_cases.py score [--all]
    Scores cases with direction long|short whose hindsight is null, or "unscored" with reason
    fetch_failed or no_bars (retried every time); --all rescores everything. Only cases whose note
    date + 14 calendar days < today. Daily bars: yahoo_bars(ticker, "1d", period1=date-40d,
    period2=date+30d) (ticker map §4; crypto <BASE>-USD; untracked-class and stock instruments ->
    unscored/no_ticker, final). Entry = OPEN of the first daily bar dated after the note date (no
    look-ahead). ATR = Wilder 14 on the bars before entry. Walk 10 daily bars from the entry bar:
    favourable if price reaches entry + 1 ATR in the called direction before entry - 1 ATR against;
    adverse if the reverse (same bar both -> adverse); flat otherwise. mfe_atr / mae_atr over the 10
    bars. Run by the ingest step, never by apply.

python3 scripts/signal_cases.py match --signal <json file> [--top 5]
    Debug: prints find_precedents() for one signal object (§3 signature, time as ISO).

python3 scripts/signal_cases.py coverage --days 14
    Feasibility replay WITHOUT TradingView, WITHOUT bars and WITHOUT the pre-filter, over every
    judged-class deduped (§5) 1H/4H alert of the last N days. Only tags derivable from the sheet,
    anchored on the alert's nominal bar close (§5):
      tf; setup: tflow, pullback_in_trend, laggard; location: only at_d_zone (Tflow text);
      structure: unspecified (excluded from the similarity max);
      htf: from ~/tradingview-mcp/daily_brief/<D>.json, the newest file with D <= the alert's SGT
           date and at most 3 days older (no look-ahead), else unspecified;
      risk_flags: news_pending (Red Folder within 24 h after the bar close), friday (§4 rule).
    Only cases dated strictly before each alert are eligible. Prints: alerts replayed; % with >= 1
    instrument_recent case; % with >= 2 similar cases at similarity >= 0.45; % with either (the
    gate metric, §Verification 2); the 10 most-matched cases; tag values never matched. A lower
    bound on what a live run (with chart tags) would match.

python3 scripts/signal_cases.py stats
    Counts by session_type / verdict / tf / asset_class; hindsight status counts; notes done vs pending.
```

### 3. Precedent retrieval

```python
def find_precedents(signal, cases, top=5):
    """signal = {"instrument": "GBPUSD", "asset_class": "fx", "currencies": ["GBP", "USD"],
                 "time": aware datetime (signal bar close),
                 "tags": {"tf", "setup", "location", "structure", "htf", "risk_flags"}}
    returns {"instrument_recent": [case, ...], "similar": [dict(case, similarity=float), ...]}"""
```
- Eligible cases: `date` strictly before the SGT date of `signal["time"]`.
- **instrument_recent**: same `instrument`, date within the 21 days before, newest first, max 3, no threshold.
- **similar**: every other eligible case (only the ones already returned in instrument_recent are excluded), scored below. A component counts toward the maximum only if the signal has a value for it (non-empty list, or not `unspecified`). The `asset_class` comparison treats the `untracked` class by its underlying kind (indices → `index`, metal crosses → `metal`).

| Component | Points |
|---|---|
| tf exact / adjacent (m15↔1h, 1h↔4h, 4h↔d, d↔w, w↔m) | 2 / 1 (max 2) |
| each shared `setup` tag | 2 each (max 2·\|signal setup\|) |
| each shared `location` tag | 2 each (max 2·\|signal location\|) |
| `structure` equal | 2 |
| `htf` equal | 1.5 |
| each shared `risk_flags` tag | 1 each (max \|signal risk_flags\|) |
| same `asset_class` | 1 |
| shares a currency (both FX) | 1 (in the max only for FX signals) |

  `similarity = points / max`. Keep ≥ 0.45, sort by similarity desc, then date desc, top 5.

### 4. Chart pass, features and tags (inside `signal_judge.py`)

**Helper alert dict** passed to the imported helpers: `{"symbol": tv_symbol, "clean": SYMBOL, "direction": "Bullish"|"Bearish", "signal": signal, "base_signal": signal minus "Tflow ", "tflow": bool, "signal_price": float(sheet Signal Price), "event": Event, "alert_dt": aware SGT datetime}`. `tv_symbol` = the sheet's `Symbol` as written (e.g. `EIGHTCAP:NDQ100`).

**`scripts/tv_judge_pass.mjs`**: `node scripts/tv_judge_pass.mjs <request.json> <out.json>`.
- request = `{"deadline_ms": <epoch ms>, "items": [{"symbol": "EIGHTCAP:GBPUSD", "timeframes": ["60", "240"]}, ...]}`. A symbol's `timeframes` is the union over its candidate alerts (1H alert → `60` + `240`; 4H alert → `240` + `D`), ordered `60`, `240`, `D`. Items are in candidate rank order (§5).
- Imports: `morning.js` uses relative paths (`./chart.js`, `./data.js`, `./ui.js`); this script loads the same modules with `await import(pathToFileURL(join(homedir(), "tradingview-mcp/src/core/chart.js")).href)` (likewise `data.js`, and `ui.js` for `layoutSwitch`). It calls `layoutSwitch({name: "0 TAW Layout"})` once, then waits 2 s.
- Per item: `chart.setSymbol`, then per timeframe: `chart.setTimeframe`, wait 900 ms, then read `chart.getState()`, `data.getOhlcv({count: 300})`, `data.getPineLabels({study_filter: "TAT", max_labels: 500})` (the default keeps only the newest 50, `data.js:384-400`, which TAT v3 pattern/zone labels could exhaust), `data.getStudyValues()`, `data.getQuote({})`.
- After each item it rewrites `out.json` (`{"items": {"<symbol>": {"<tf>": {state, bars, tatLabels, indicators, quote, read_at}}}, "errors": [...]}`) so partial results survive a kill. It stops starting new items once `Date.now() > deadline_ms`, records per-read errors instead of throwing, and ends with `process.exit(0)` (the CDP client would otherwise keep Node alive).
- Cost: `chart.setSymbol` carries ~3.2 s of fixed sleeps plus a ready-wait (`~/tradingview-mcp/src/core/chart.js:47-99`); each timeframe adds `setTimeframe` + ready-wait + 900 ms + 5 reads. Plan on ~8–12 s per symbol with 2 timeframes.

**Read validation** (each symbol × timeframe read; a failure discards that read and gives retryable `NO_DATA` with the reason):
- `state.symbol` ends with the clean symbol ("symbol not confirmed");
- `state.resolution` equals the requested timeframe ("timeframe not confirmed"), and the median spacing of the last 20 bar starts equals T (3600 / 14400 s; for `D` ≥ 72000 s) ("bar spacing mismatch");
- for tracked classes, `|quote.last − yahoo meta.price| / meta.price ≤ 0.03` ("quote mismatch"; Yahoo is fetched once per symbol right after the pass);
- a label read returning exactly 500 labels is kept but flagged `labels_capped: true` in the features.

**Bar close times**: `close(bar i) = min(start_i + T, start_{i+1})` for every bar but the last; for the last bar, `start + T`. This makes short session-end bars close at the next session's open boundary or their nominal end, whichever is earlier.

**Signal bar**: the latest TV bar with `close ≤ alert_dt + 120 s`, and the signal bar's start must be `≥ alert_dt − T − 6 h` (so a wildly delayed or out-of-place alert cannot match an old bar). It is accepted even when it is the last bar (the alert proves it closed). If the alert arrived more than 10 min after that close, `features.delayed_alert_min` records the delay (the sheet shows delayed batches, e.g. 1H rows at 14:54–15:27 on 2026-10-21). No such bar → `NO_DATA` "no TradingView bar for this alert" (retryable once). `bar_close` (ledger, report) = the signal bar's close.

**Closed bars for calculations**: ATR, EMA, swings and `age_bars` use bars up to and including the last bar whose close ≤ `read_at` (a forming last bar is excluded, unless it is the signal bar). `age_bars` = such bars after the signal bar.

**Market open**: a symbol is closed at read time if its last TV bar's start is more than `2 × T` before `read_at` (1H: 2 h; 4H: 8 h), or, for tracked classes, Yahoo `meta.time` is more than 30 min old. Closed → prefilter `CLOSED` (retryable, attempts not counted), so the alert is retried at the next run instead of being judged on a stale price. (Weekend runs are already skipped, §6 step 0; this catches the daily 17:00–18:00 New York break for metals/indices and holidays.)

**Entry reference**: `entry_ref = {"time": read_at of the signal-TF read, "price": quote.last}`: the moment the judge looked, so outcomes never include moves from before the verdict. `signal_close` = the signal bar's close.

**Levels** (signal-TF read = `60` for 1H, `240` for 4H; higher-TF read = `240` for 1H, `D` for 4H):
- `sig_levels` = `parse_tat_levels(signal-TF read, ref=entry_ref.price)`.
- `htf_levels_all` = `parse_tat_levels(higher-TF read, ref=entry_ref.price)` + the `sig_levels` whose `tf` suffix is higher than the signal TF (1H: h4/d/w/m; 4H: d/w/m).
- `trigger_level` = `triggering_level(sig_levels, signal_close, bull, signal_bar)`.
- `tp1` = `nearest_level(sig_levels, entry_ref.price × (1 ± 0.0005), "up"|"down")`, replaced by the nearest `TP`-kind level on the same side if that is nearer (as `validate_h4_signals.py:960-983` does, anchored on entry_ref).
- `swings` = `find_swings(bars, signal_idx, lookback=L)`, L = 120 (1H) or 60 (4H); `sl` = `elbow_invalidation(alert, signal_bar, bars, swings)`.
- `htf_levels.behind/ahead` = nearest `htf_levels_all` level behind/ahead of entry_ref (`nearest_level`), with `dist_atr = |level − entry| / ATR`.
- `ATR` = Wilder ATR(14) on the closed signal-TF bars; null with fewer than 15.

**Features** (in the packet and the brief; not in the ledger, §8):
```
features = {
  "close_quality": trigger_level is None -> {"excursion": null, "close_pos": null, "crossed_on_bar": null}
                   else g = gate_convincing_close(alert, signal_bar, trigger_level, contemporaneous=(age_bars <= 1))
                        -> {"excursion": g.get("excursion"), "close_pos": g.get("close_pos"), "crossed_on_bar": g.get("crossed")},
  "htf": {"source": "TAT trend 4H" (1H) | "TAT trend D" (4H),
          "bias": htf_bias(higher-TF read),   # = tat_bias, but null when the read is missing or has no study named "TATbyBinniOng*" with both "Up Trend" and "Down Trend" values (tat_bias returns "neutral" then, validate_h4_signals.py:391-406)
          "daily_brief": {"bias", "age_days"}},   # newest ~/tradingview-mcp/daily_brief/<D>.json with D <= run date; informational / fallback
  "room_consumed": trigger_level and tp1 -> gate_room_to_target(alert, trigger_level, tp1_level, entry_ref.price).get("consumed") else null,
  "structure": g = gate_break_of_structure(alert, signal_bar, swings) ->
               {"state": g.get("structure", "Mixed"),
                "mode": g["mode"] if g["pass"] else ("counter" if latest_swing(swings, "high" if bull else "low") else "none"),
                "latest_high": (latest_swing(swings, "high") or {}).get("price"), "latest_low": (latest_swing(swings, "low") or {}).get("price")},
  "ema20": e = ema_from_bars(bars, 20) -> {"value": e, "side_ok": entry > e (bull) / entry < e (bear), "dist_atr": |entry - e| / ATR},
  "cross_pair": fx only: (score, detail) = cross_pair_consistency(alert, same-TF deduped fx alerts with the same nominal bar close) -> {"score", "detail"};
                other classes -> {"score": null, "detail": "not FX"} (the helper treats any 6-letter symbol as FX, validate_h4_signals.py:823-857),
  "trigger_level", "tp1_level": {"price", "kind", "tf"} | null,
  "htf_levels": {"behind": {"price", "kind", "tf", "dist_atr"} | null, "ahead": ... | null},
  "tflow": parsed Event (regex below) | null,
  "other_tf_alert": latest deduped alert on the same symbol in the other tab: 4H within 24 h before a 1H signal's bar close, 1H within 8 h before a 4H signal's -> {"tf", "signal", "direction", "hours_ago"} | null,
  "red_folder_24h": rows of the "This Week" / "Next Week" tables in wiki/notes/economic-calendar.md with Date + Time (SGT) in [entry_ref.time, + 24 h] and Currency in the instrument's currencies (FX: both legs; metals and metal crosses: USD + the cross currency; US indices: USD; JPN225: JPY; GER40/FRA40: EUR; UK100: GBP; HK50/CN50: CNY, HKD; USDX: USD) -> [{"date", "time", "ccy", "event"}],
  "risk_scale": tp1 and sl -> risk_scale_position(entry_ref.price, lower, upper, bull), (lower, upper) = (sl, tp1) long / (tp1, sl) short, else null,
  "age_bars": int, "delayed_alert_min": int | null, "labels_capped": bool,
  "wash_lines": null
}
```

Tflow Event regex (anchored, on the `Event` of a `Tflow ` row):
`^Tflow (Bullish|Bearish) Signal(?: @Zone \((Support|Resistance) Zone x(\d+) \(([A-Z,]+)\), Zone High: ([\d.]+), Zone Low: ([\d.]+)\))?: D Level: ([\d.]+), (LL|HH): ([\d.]+)` → `{"direction", "at_zone": bool, "zone": {"role", "count", "tfs", "high", "low"} | null, "d_level", "pivot_label", "pivot"}`. No match → `{"parse_error": "<event>", "at_zone": false}`.

**Tag mapping** (signal → case vocabulary):
- `tf`: `1h` / `4h`.
- `setup`: `tflow` + `pullback_in_trend` if Tflow; `trend_continuation` if structure.mode = trend; `reversal` if mode = reversal; `breakout` if close_quality.crossed_on_bar is true; `laggard` (FX only) if, among the same-TF deduped FX alerts whose nominal bar close is 1–3 bars before this one, a pair sharing a currency expressed the same move for that currency (the `cross_pair_consistency` rule: GBPAUD bear = AUD strong; an earlier EURAUD bear or AUDCAD bull matches).
- `location` (a set): `at_d_zone` if tflow.at_zone; `htf_level_behind` if behind.dist_atr ≤ 1.0; `htf_level_ahead` if ahead.dist_atr ≤ 1.0; `open_space` if no ahead level or ahead.dist_atr > 3.0 (never with `htf_level_ahead`); `at_ema` if ema20.dist_atr ≤ 0.3; `mid_range` only if none of the above applies. With ATR null only `at_d_zone` and `open_space` (no ahead level) can apply.
- `structure`: trend → `with_trend`; counter → `counter_trend`; reversal → `transition`; none → `unspecified`.
- `htf`: htf.bias equal to the signal direction → `aligned`; opposite → `opposed`; neutral → `ambiguous`; null → the daily brief bias by the same rule if age ≤ 3 days, else `unspecified`.
- `risk_flags`: `news_pending` if red_folder_24h is non-empty; `friday` if the signal bar closes on a Friday in New York time at or after 01:00 NY (the last ~16 trading hours of the week; this includes the bars closing Saturday early morning SGT); `room_consumed` if room_consumed > 0.5; `counter_trend` if structure.mode = counter; `late_entry` if age_bars ≥ 3.

**Screenshot reuse**: `chart_image` = the newest `wiki/images/<YYMMDD-HHMMSS>_<symbol lowercase>_<1h|4h>_chart.png` (matching the signal TF) timestamped within 45 min before the run start; else null.

**Yahoo fetcher**: `yahoo_bars(ticker, interval, range_=None, period1=None, period2=None) -> (bars, meta)`, `interval` ∈ {`1h`, `1d`}. Ticker map: FX `<SYM>=X`; XAUUSD `GC=F`; XAGUSD `SI=F`; indices as in the class table; crypto `<BASE>-USD` (hindsight only); untracked class → none. Drops bars with any null OHLC and 1H bars whose minute ≠ 0. Bars `{"dt": SGT-aware start, ...}`; `meta` = `{"price": regularMarketPrice, "time": regularMarketTime}`. Timeout `min(15, budget)` s, no retry, per-run cache by (ticker, interval, range).

**Basis** (metals and indices; FX 0; untracked class: none): `basis = meta.price − quote.last` within the same run (lag ≤ a few minutes, stored as `basis_lag_s`). The tracker compares `yahoo price − basis` against SL / TP1. No Yahoo price for a tracked metal/index → `NO_DATA` "no Yahoo price" (retryable).

### 5. Candidate selection, dedupe and pre-filter

Load both tabs with `fetch_with_service_account("H1")` / `("4H")` (each in try/except, inside `contextlib.redirect_stdout(buffer)`; the buffer is echoed to stderr afterwards), with `socket.setdefaulttimeout(20)` set at startup. A tab that raises or returns 0 rows counts as failed (these tabs always hold hundreds of rows). If the buffer contains `Tflow supplement skipped`, that tab's status is `ok, tflow skipped`: the run continues on the plain rows, the report shows ⚠️ "Tflow / @Zone tags unavailable this run", and the writer host logs an `error`.

Parse `Date` + `Time` (`%H:%M:%S`, `%H:%M`, `%I:%M:%S %p`, `%I:%M %p`) as SGT. **Nominal bar close** = alert time floored to the hour (used for grouping, keys and freshness before the chart pass).

**Market hours** between two instants = calendar hours minus the overlap with each weekend closure, defined in New York time as Friday 17:00 → Sunday 17:00 `America/New_York` (correct in both seasons).

**Window**: keep rows whose nominal bar close is ≤ 12 market hours before the run (any tab), whose signal minus `Tflow ` is in `SIGNAL_TIER`, and whose instrument is in a judged class (others are counted `out_of_scope`). Older rows are not looked at.

**Dedupe**: group by (canonical symbol, tf, direction, nominal bar close). One alert per group: `signal` = the Tflow row's if any row in the group is Tflow, else the highest tier (Opt > L > S); `tflow` parsed from that Tflow row's Event; `event` from the chosen row; `also_fired` = the other rows' signals.

**Key** = `<SYMBOL>|<1H|4H>|<Bull|Bear>|<nominal bar close ISO SGT>`, e.g. `GBPUSD|4H|Bull|2026-11-02T10:00:00+08:00`. Opposite directions on the same bar stay separate.

**Rank** (one sort key, used for the chart-pass order, the symbol cap and the judge cap): `(tflow_at_zone desc, tflow desc, tier desc, rr_group, rr desc, nominal close desc)`, where before the chart pass `rr_group`/`rr` are 0 for all, and after it `rr_group` = 0 for a computed R:R, 1 for OPEN RUN.

Steps, in order:
1. **Already seen**: drop alerts whose key is in the ledger (`already_seen`), except **retryable** entries: `prefilter` ∈ {`NO_DATA`, `CLOSED`} with `retryable: true` and `attempts < 3` (`CLOSED` doesn't increment `attempts`). Those re-enter as candidates; the ledger entry is updated in place under the same key.
   - Retryable `NO_DATA` reasons: chart pass skipped (lock busy, start failed, not enough budget, or `--no-chart` on a non-dry run), chart pass cap, run budget exceeded, symbol not read, symbol/timeframe not confirmed, bar spacing mismatch, quote mismatch, no Yahoo price, and "no TradingView bar for this alert" (once: `attempts < 2` for this reason).
2. **STALE**: market hours since the nominal bar close > 6 (1H) or > 12 (4H; can't happen inside the window, kept for retried entries) → `STALE`, final; recorded with no chart data, outcome `UNTRACKED`. A retryable entry that has gone stale is updated to `STALE`.
3. **Chart candidates**: the rest, in rank order. Their unique symbols, capped at **24** (~4 minutes at ~10 s each), go to the chart pass. Alerts on symbols beyond the cap → `NO_DATA` "chart pass cap" (retryable).
4. After the pass, per alert:

| Code | Rule |
|---|---|
| `CLOSED` | market closed at read time (§4) |
| `NO_DATA` | not read / read failed validation / no signal bar / no Yahoo price (tracked metal or index) |
| `NO_STOP` | `sl` null, or not on the losing side of `entry_ref.price` |
| `RR_LT_1` | `tp1` exists and R:R = \|tp1 − entry\| / \|entry − sl\| < 1.0 (no level ahead = OPEN RUN, passes with `tp1` null) |
| `PASS` | everything else |

5. PASS alerts, re-sorted by the rank key with their R:R: the top 8 get verdict `pending` and go to the judge (packet `survivors`); the rest get `unjudged_cap` (packet `capped`).

**Tracked** = prefilter `PASS` (any verdict) or `RR_LT_1`, in a tracked class. Everything else (`STALE`, `NO_DATA`, `CLOSED`, `NO_STOP`, untracked class) has outcome `UNTRACKED`. When a retried entry becomes `PASS`/`RR_LT_1`, its outcome resets to `OPEN` with the new `entry_ref`.

### 6. `scripts/signal_judge.py` CLI

```
python3 scripts/signal_judge.py run   [--symbol SYM] [--no-chart] [--dry-run --out DIR] [--force-writer] [--ignore-skip-window]
python3 scripts/signal_judge.py apply --packet PATH [--verdicts PATH] [--force-writer]
python3 scripts/signal_judge.py track [--force-writer]
python3 scripts/signal_judge.py stats [--since YYYY-MM-DD] [--json]
```
All diagnostics go to stderr; subprocesses get `stdout=sys.stderr`. `run`'s only stdout is one final line: `PACKET <path>`, or `SKIPPED <reason>` on exit 10.

**Writer guard**: `run` (without `--dry-run`), `apply` and `track` write the ledger/report only when `scutil --get LocalHostName` (fallback `socket.gethostname().split(".")[0]`) equals `writer_host` in `scripts/signal_judge_config.json`, or with `--force-writer`; otherwise exit 6 `not the Signal Judge writer host (<name>); use --dry-run`. Test redirection: with env `SIGNAL_JUDGE_DATA_DIR` (ledger dir) **and** `SIGNAL_JUDGE_REPORT_DIR` (report dir) both set, the guard is skipped and `append_log` / `update_weekly_index` are not called; only one set → exit 6 "set both". `cases.jsonl` is only read by these commands (env `SIGNAL_CASES_DIR` for fixtures). `--dry-run` requires `--out DIR` and writes only the packet and brief there.

**`run`** — wall-clock budget 540 s from process start, tracked by a `Budget` object (`deadline = time.monotonic() + 540`; `remaining()`; `cap(x) = max(1, min(x, remaining() − 90))`; the 90 s reserve covers `stop` and the writes). No `signal.alarm`: every blocking call gets its own bounded timeout.
0. **Skip windows** (unless `--ignore-skip-window`): SGT 17:00–17:59 Mon–Sat → `SKIPPED 17:00 window (Equity News — Asian)`; any time inside the weekend closure (Friday 17:00 → Sunday 17:00 New York) → `SKIPPED weekend`. Exit 10; nothing read or written.
1. Unless `--dry-run`: age `pending` entries older than 2 h to `unjudged_error`; delete `scripts/signal_judge_runs/*` older than 90 days.
2. Load, dedupe, pre-chart steps (§5). Both tabs failed → log + exit 3.
3. Chart pass, unless `--no-chart` or there are no candidates. If `budget.remaining() < 300` (not enough for a 120 s lock wait + launch + a pass), skip it ("not enough budget", retryable). Otherwise:
   - Token `T = <run_id>-<pid>`. `start_invoked = True` just before `subprocess.run(["bash", "scripts/tv_session.sh", "start"], env={…, TV_LOCK_MAX_WAIT_SECS: "120", TV_LOCK_FAIL_ON_TIMEOUT: "1", TV_LOCK_OWNER: T}, timeout=budget.cap(360), stdout=sys.stderr)`.
   - Exit 75 → this run never took the lock: no chart data, `chart_pass.ok=false`, and no stop.
   - Exit 0 → pass: `subprocess.Popen(["node", "scripts/tv_judge_pass.mjs", req, out], start_new_session=True, stdout=sys.stderr, stderr=sys.stderr)` with `deadline_ms` = now + `budget.cap(300)` s; Python polls `proc.poll()` every 1 s and kills the group (`os.killpg(proc.pid, SIGKILL)`) if it is alive 20 s past the deadline or `budget.remaining() < 90`; then reads `out.json` as is.
   - Any other outcome (non-zero exit, timeout, exception) → no chart data.
   - **Stop** whenever `start_invoked` and start did not return 75: `subprocess.run(["bash", "scripts/tv_session.sh", "stop"], env={…, TV_LOCK_OWNER: T}, timeout=60, stdout=sys.stderr)` in `finally`. Because of the owner token, a stop after a start that timed out while still waiting for someone else's lock does not touch that job's TradingView. A SIGTERM/SIGINT handler kills the Node group (if any), runs the same stop, then exits 143 / 130.
4. Yahoo: one 1H fetch per tracked-class chart-candidate symbol (`meta` + quote check), each skipped once `budget.remaining() < 100` (that symbol → `NO_DATA` "run budget exceeded", retryable).
5. Features, market-open check, pre-filter, precedents (cases.jsonl missing → no cases).
6. Unless `--dry-run`: write all recorded / updated entries to the ledger.
7. Write `scripts/signal_judge_runs/<run_id>_packet.json` and `<run_id>_brief.md` (or into `--out DIR`); print `PACKET <path>`.

Candidates the pass did not reach become `NO_DATA` "run budget exceeded" (retryable). `run_id` = `YYYY-MM-DD_HHMM` of the run start in SGT.

Exit codes: 0 success (including zero candidates or a degraded chart pass); 3 both sheet tabs failed; 4 ledger lock not acquired within 60 s; 5 a ledger shard exists but is invalid JSON (never overwritten); 6 writer guard; 10 skipped by a skip window (not an error, not logged).

**`apply`**:
1. Read the packet (missing/unreadable → exit 2).
2. Read the verdicts (default `packet["verdicts_path"]`). Survivors present and the file missing or unparseable → all survivors `unjudged_error` "judge unavailable".
3. Validate (§7) and write verdicts into entries still `pending`; entries already aged to `unjudged_error` are left alone (warning line in the report).
4. Tracker (§8, budget 150 s), remembering the keys it resolved.
5. Append the report section (§9); `report_toc.upsert_toc`.
6. `append_log.py --action report --title "Signal Judge Run — <date> <HH:MM> SGT" --body "<run summary line>"`; `update_weekly_index.py`.

`apply` runs for every packet, including zero survivors. Exit 0 when the report is written; 2 unreadable packet; 4 / 5 / 6 as above.

**`track`**: standalone tracker (§8, budget 300 s); prints the resolved count. Exit 0 / 4 / 5 / 6.

**`stats`**: the §9 scorecard over `--since` (default 30 days back), table or JSON; read-only, any host.

**Ledger writes**: every write is a read-modify-write inside the `fcntl` lock on `wiki/notes/signal-judge/ledger.lock`: re-read the affected shard(s), merge by key (append new keys; update existing keys field by field), temp file, `os.replace`. The lock is held per write.

**Error logging** (writer host): the scripts call `append_log.py --action error` for exits 3/4/5, a skipped or failed chart pass (except exit 75 lock-busy, which is logged as a one-line `error` only if it happens twice in a row), an exceeded budget, "judge unavailable", and the Tflow-skipped status. Exit 6 cannot log; the Orca prompt reports it.

### 7. Packet, brief and verdict files

**Packet** (`<run_id>_packet.json`, machine-readable, for `apply`):
```json
{
  "run_id": "2026-11-02_1317",
  "created_at": "2026-11-02T13:19:40+08:00",
  "doctrine_checklist": ".agents/skills/signal-judge/reference/doctrine-checklist.md",
  "brief_path": "scripts/signal_judge_runs/2026-11-02_1317_brief.md",
  "verdicts_path": "scripts/signal_judge_runs/2026-11-02_1317_verdicts.json",
  "counts": {"rows_in_window": 40, "deduped": 31, "out_of_scope": 4, "already_seen": 12, "retried": 2,
             "stale": 3, "chart_candidates": 12, "recorded": 15, "closed": 0, "pass": 9, "judged": 8,
             "unjudged_cap": 1, "by_tf": {"1H": 10, "4H": 5}},
  "chart_pass": {"ok": true, "symbols": 9, "failed": [], "budget_exceeded": false, "skipped_reason": null},
  "sheet": {"H1": "ok", "4H": "ok"},
  "survivors": [{
    "key": "GBPUSD|4H|Bull|2026-11-02T10:00:00+08:00", "n": 1,
    "symbol": "GBPUSD", "asset_class": "fx", "tracked": true, "tf": "4H", "direction": "Bullish",
    "signal": "Tflow LBull", "also_fired": ["LBull"], "alert_time": "2026-11-02T10:00:12+08:00",
    "bar_close": "2026-11-02T10:00:00+08:00",
    "entry_ref": {"time": "2026-11-02T13:18:02+08:00", "price": 1.34012},
    "sl": 1.33551, "tp1": 1.34903, "rr": 1.93,
    "features": {}, "tags": {"tf": "4h", "setup": ["tflow", "pullback_in_trend"], "location": ["at_d_zone"], "structure": "with_trend", "htf": "aligned", "risk_flags": []},
    "precedents": {"instrument_recent": [], "similar": []},
    "chart_image": "wiki/images/261102-131502_gbpusd_4h_chart.png"
  }],
  "capped": [{"key": "...", "symbol": "...", "tf": "1H", "direction": "Bearish", "signal": "...", "entry_ref": {}, "sl": 0, "tp1": 0, "rr": 0}],
  "filtered": [{"key": "...", "symbol": "...", "tf": "1H", "direction": "Bearish", "signal": "...", "prefilter": "RR_LT_1", "detail": "1:0.64 from entry 1.08120", "retryable": false}]
}
```
(In the real file `features` follows §4 and `precedents` holds full case records.)

**Brief** (`<run_id>_brief.md`, what the judge reads): plain Markdown, one section per survivor so it reads reliably in chunks:
```
# Signal Judge brief — run 2026-11-02_1317 — 8 survivors

## S1 — GBPUSD 4H Tflow LBull (Bull) — key GBPUSD|4H|Bull|2026-11-02T10:00:00+08:00
- Entry 1.34012 (13:18 SGT) · SL 1.33551 · TP1 1.34903 · R:R 1:1.93 · tracked: yes
- Tags: tf 4h · setup tflow, pullback_in_trend · location at_d_zone · structure with_trend · htf aligned · risks none
- Features: one line each (close quality, htf + daily brief, room consumed, structure, EMA20, cross-pair, trigger/TP levels, HTF levels with dist_atr, Tflow zone, other-TF alert, Red Folder 24 h, risk scale, age, delay, labels capped)
- Chart image: wiki/images/261102-131502_gbpusd_4h_chart.png
### Precedents
- [recent] 2026-10-27-ahh-access-time-usdjpy-1 · 2026-10-27 · USDJPY 4h long · take · cond: — · hindsight favourable (+1.8 ATR / −0.4 ATR) · "Dollar yen is my best candidate … for a long"
- [similar 0.62] <id> · <date> · <instrument tf direction> · <verdict> · cond: <condition or —> · hindsight <label (mfe/mae)> · "<quote, ≤ 200 chars>"

## S2 — …
```
Lines are ≤ 400 characters (quotes truncated to 200 with `…`), so no line hits the Read tool's 2,000-character limit. Survivors are capped at 8 and precedents at 8 per survivor, keeping the brief under ~250 lines.

**Verdicts** (written by the judge):
```json
{
  "run_id": "2026-11-02_1317",
  "verdicts": [{
    "key": "GBPUSD|4H|Bull|2026-11-02T10:00:00+08:00",
    "verdict": "take | wait_retest | skip | no_ruling",
    "confidence": "low | medium | high",
    "retest_level": null,
    "retest_window_bars": null,
    "controlling_cases": ["2026-10-27-ahh-access-time-usdjpy-1"],
    "distinguished": [{"case_id": "2026-10-14-taw-pro-gbpjpy-1", "why": "that was a Daily breakout; this is a 4H Tflow off a W,M zone"}],
    "doctrine": ["R07", "R12"],
    "reason": "1–400 chars, no | or newline",
    "dissent": null,
    "question_for_binni": null
  }]
}
```

`doctrine-checklist.md` is a numbered list of rules with stable ids `R01`, `R02`, …, each line `- **R07** <rule> — (see [<page>](../../../../wiki/concepts/<page>.md) claim N / [<note>](...))`. New rules get the next id; ids are never reused.

Validation in `apply` (a failing verdict → that entry `unjudged_error` with the error text; the others proceed):
- exactly one verdict per survivor key (a survivor with none → `unjudged_error` "no verdict returned"); unknown keys ignored with a warning;
- enums as above;
- `wait_retest`: `retest_level` strictly between `sl` and `entry_ref.price`; `retest_window_bars` 1–12 (1H) / 1–6 (4H); other verdicts: both null;
- `controlling_cases` (0–3) and `distinguished[].case_id` are ids in that survivor's packet precedents;
- `doctrine` entries match `^R\d{2,3}$` and exist in the checklist;
- `no_ruling` needs a non-empty `question_for_binni`;
- `reason` 1–400 chars, no `|` or newline.

### 8. Ledger and tracker

**Shards** `wiki/notes/signal-judge/ledger-YYYY-MM.json` (by the SGT month of the nominal bar close) = `{"version": 1, "entries": [...]}`. Entries are compact (no `features`; those live in the packet and brief, kept 90 days in `scripts/signal_judge_runs/`), about 0.8–1 KB each, so a month of ~100 entries/day stays near 3 MB, inside Obsidian Sync's 5 MB per-file limit on the Standard plan. The tracker and `run` read the current and previous month's shards (OPEN entries are never older than 10 days); the dashboard and `stats` read the shards covering their range.

Entry:
```json
{
  "key": "GBPUSD|4H|Bull|2026-11-02T10:00:00+08:00", "run_id": "2026-11-02_1317",
  "symbol": "GBPUSD", "tv_symbol": "EIGHTCAP:GBPUSD", "asset_class": "fx", "tracked": true, "tf": "4H", "direction": "Bullish",
  "signal": "Tflow LBull", "also_fired": ["LBull"], "tflow": true, "at_zone": true,
  "alert_time": "...", "bar_close": "...", "signal_close": 1.33990,
  "entry_ref": {"time": "...", "price": 1.34012}, "sl": 1.33551, "tp1": 1.34903, "rr": 1.93,
  "basis": 0.0, "basis_lag_s": 0,
  "prefilter": "PASS", "prefilter_detail": "", "retryable": false, "attempts": 1,
  "tags": {}, "precedent_ids": ["..."],
  "verdict": "take", "retest_level": null, "retest_window_bars": null,
  "judge": {"confidence": "medium", "controlling": [{"id": "...", "verdict": "take", "quote": "...", "hindsight": "favourable"}], "doctrine": ["R07"], "reason": "...", "dissent": null, "question_for_binni": null, "error": null},
  "outcome": {"status": "OPEN", "entry": null, "fill_time": null, "resolved_time": null, "bars": 0, "r": null, "mfe_r": null, "mae_r": null}
}
```
- `judge.controlling` snapshots each controlling case (id, verdict, quote ≤ 200 chars, hindsight label).
- `verdict` ∈ {`take`, `wait_retest`, `skip`, `no_ruling`, `pending`, `unjudged_cap`, `unjudged_error`, null (prefilter not PASS)}.
- `outcome.status` ∈ {`OPEN`, `TP1_HIT`, `SL_HIT`, `EXPIRED`, `OPEN_RUN_EXPIRED`, `NO_FILL`, `NO_DATA`, `UNTRACKED`}.

**Tracker**, per tracked entry with status `OPEN`, grouped by Yahoo ticker: one fetch per ticker, `yahoo_bars(ticker, "1h", period1 = oldest OPEN entry_ref.time − 1 h, period2 = now)`. Prices are compared after subtracting the entry's `basis`. Bars are Yahoo 1H for both TFs, using only bars whose start ≥ the first full hour after `entry_ref.time` (the judging moment is never back-filled).
- **Entry point**:
  - `wait_retest`: the first bar within `retest_window_bars × (1 for 1H, 4 for 4H)` bars whose range contains `retest_level` fills at `retest_level` (`fill_time` = that bar's start); SL and TP1 are checked on that same bar (stop first). No fill → `NO_FILL`, r = 0, and `mfe_r` = the favourable move from `entry_ref.price` over the window, in units of the planned risk `|retest_level − sl|`.
  - Every other tracked entry: entry = `entry_ref.price`.
- `risk = |entry − sl|`. Walk up to 24 bars (1H) or 120 bars (4H = 30 4H bars) from the entry point:
  - range reaches SL → `SL_HIT`, r = −1 (checked before TP on the same bar);
  - range reaches TP1 → `TP1_HIT`, r = |tp1 − entry| / risk;
  - window exhausted → `EXPIRED`, r = (last close − entry) / risk in the trade direction; with `tp1` null → `OPEN_RUN_EXPIRED`.
- `mfe_r` / `mae_r`: max favourable / adverse excursion from entry in R up to resolution; `bars` = bars walked.
- Window not exhausted → stays `OPEN`. Still `OPEN` 10 calendar days after `entry_ref.time` → `NO_DATA`.
- A per-call budget (150 s in `apply`, 300 s standalone) stops fetching new tickers when exceeded; the rest stay `OPEN`.

### 9. Report: `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md`

Written only by `apply` on the writer host (or into `SIGNAL_JUDGE_REPORT_DIR`). The date is the run's SGT date. The first run of the day creates:
```
---
type: report
date: "2026-11-02"
---

# ⚖️ Signal Judge — 2026-11-02

<!-- TOC:START -->
...
<!-- TOC:END -->
```
Each `apply` appends one section, then `report_toc.upsert_toc` regenerates the TOC from the `##` headings:

```
## 🕒 Signal Judge Run — [13:19 SGT]

**Run summary:** run `2026-11-02_1317` · 40 alerts in window · 15 recorded (1H 10 · 4H 5) · 9 passed the pre-filter · 8 judged · verdicts: take 2 · wait 2 · skip 3 · no ruling 1 · unjudged 1 · 4 out of scope · chart pass 9/9

### Verdicts — [13:19 SGT]
| Instrument | TF | Signal | Verdict | Entry / SL / TP1 | R:R | Controlling precedent |
|---|---|---|---|---|---|---|
| [[GBPUSD]] (🟢 Bull) | 4H | Tflow LBull @Zone | ✅ Take (medium) | 1.34012 / 1.33551 / 1.34903 | 1:1.93 | [AHH Access Time 2026-10-27 · USDJPY](../../../AHH Session Notes/2026-10-27-ahh-access-time.md) |

### Opinions — [13:19 SGT]
#### GBPUSD 4H Tflow LBull — Take
- **Reason**: … **Followed**: <case id + quote + hindsight, e.g. "favourable (+1.8 ATR)"> **Distinguished**: … **Doctrine**: R07, R12 **Dissent**: …
- ![GBPUSD 4H Chart Screenshot](../../../images/261102-131502_gbpusd_4h_chart.png)   (only when chart_image)

### Pre-filter — [13:19 SGT]
<details><summary>6 alerts filtered</summary>

| Instrument | TF | Signal | Code | Detail |
</details>

### Resolved Since Last Run — [13:19 SGT]
| Instrument | TF | Verdict | Outcome | R | MFE R |      (keys resolved by this apply's tracker; "None." when empty)

### Questions for Binni — [13:19 SGT]                 (only when any no_ruling)

### 30-Day Scorecard — [13:19 SGT]
| Group | Resolved | TP1 % | Avg R | Avg MFE R | No fill |
```
- **Verdicts table**: every entry in `survivors` and `capped` (`unjudged_cap` → ⚠️ Unjudged "cap"; `unjudged_error` → ⚠️ Unjudged with the error). Untracked-class rows add "(untracked)" after the R:R.
- **Opinions**: one block per judged survivor; one line per `unjudged_error` naming the error.
- **Pre-filter block**: `filtered` (codes and details; retryable ones marked "will retry").
- Verdict icons: ✅ Take · ⏳ Wait for retest @ <level> · ⛔ Skip · ❔ No ruling · ⚠️ Unjudged.
- Instrument cells follow the per-instrument direction rule. Headings and image alt text carry no `[[...]]` or backticks; the only brackets allowed in a heading are the `[HH:MM SGT]` timestamp (as in the TAT report; `update_weekly_index.py` reads those).
- Zero survivors → summary line, Resolved, Scorecard only. A failed tab, Tflow-skipped status or skipped chart pass adds a ⚠️ line under the summary.

**Scorecard** (`scripts/signal_judge_stats.py: scorecard(entries, since) -> {"window_days", "rows": {group: {...}}}`, the single definition used by the report, `stats` and the dashboard):
- Entries: tracked entries whose `alert_time` ≥ `since`.
- Groups: `take`, `wait_retest`, `skip`, `no_ruling`, `unjudged` (cap + error), `filtered` (prefilter `RR_LT_1`; the only tracked non-PASS code).
- `resolved` = status ∈ {`TP1_HIT`, `SL_HIT`, `EXPIRED`, `OPEN_RUN_EXPIRED`}. `TP1 %` = TP1_HIT / resolved × 100; `Avg R` = mean `r` over resolved; `Avg MFE R` = mean `mfe_r` over resolved. Empty → "—".
- `no_fill` = count of `NO_FILL` (wait_retest only), shown separately and excluded from resolved. `OPEN`, `NO_DATA` and `UNTRACKED` are excluded everywhere.

**Weekly index**: `scan_reports_for_date()` adds `{"category": "Signal Judge", "title": "Signal Judge (<first> initial, latest <last>)", "rel_path", "summary"}` when the file exists; the summary sums the day's `**Run summary:**` lines into `N judged · take X · wait Y · skip Z · no ruling W`.

### 10. Dashboard

`GET /api/judge?since=YYYY-MM-DD[&until=YYYY-MM-DD]` (defaults since = today − 6, until = today) → `W.signal_judge(since, until)`. The ledger directory is `wiki/notes/signal-judge/`, or env `SIGNAL_JUDGE_LEDGER_DIR` if set (read per request).

```json
{
  "status": {"ledger": true, "mtime": "2026-11-02T13:19:52+08:00", "error": null, "truncated": null},
  "entries": [{"key", "match", "symbol", "tf", "direction", "signal", "alert_time", "prefilter", "verdict",
               "retest_level", "entry", "sl", "tp1", "rr", "tracked", "outcome", "r", "mfe_r", "reason"}],
  "reports": {"2026-11-02": "reports/tat_analysis/signal_judge/2026-11-02-signal-judge.md"},
  "stats": {"window_days": 30, "rows": {"take": {"resolved": 12, "tp1_pct": 58, "avg_r": 0.41, "avg_mfe_r": 1.3, "no_fill": 0}}}
}
```
- `entries`: SGT date of `bar_close` in [since, until], newest first, max 5000; beyond that `status.truncated` = the total, and the UI shows "Judge data shows the newest 5,000 of N alerts" above All signals.
- `match` = `<_norm_sym(tv_symbol, src)[0]>|<1H|4H>|<bull|bear>|<YYYY-MM-DD>|<HH>` from the key's nominal bar close (`_norm_sym` returns `(sym, exch)`, `dashboard/wiki_data.py:1081`).
- Field mapping: `entry` = `outcome.entry` if set, else `entry_ref.price`; `outcome` = `outcome.status`; `r`, `mfe_r` from `outcome`; `reason` = `judge.reason` for judged verdicts, `judge.error` or "cap" for unjudged, `prefilter_detail` for pre-filter results; the rest copied.
- `reports`: wiki-relative paths (what `/api/doc` and `openDoc` expect, `server.py:88`), listed from `wiki/reports/tat_analysis/signal_judge/` or env `SIGNAL_JUDGE_REPORT_DIR` if set (test instances); the returned path form is always `reports/tat_analysis/signal_judge/<name>`.
- `stats`: `signal_judge_stats.scorecard(...)` over 30 days.
- No shard → `{"status": {"ledger": false, ...}, "entries": [], "reports": {}, "stats": {}}`; unreadable → `status.error`. Read-only; no write endpoint.

UI (`viewSignals`, `dashboard/static/app.js:481`):
- Range → query: today/3d/7d/30d → `since` = range start; `all` → since = today − 89; `custom` → `since=until=f.day`. One `api()` fetch per render.
- **Signal Judge** card between "Multi-timeframe alignment" and "All signals": header = the 30-day scorecard on one line (take / wait / skip / filtered: resolved · TP1 % · avg R) + "Open report ↗" (`openDoc(path, 'Signal Judge ' + date)`) for the newest date in `reports`; body = entries with a verdict other than null/`pending`, filtered by the Source filter (1H/4H) and the search box (`matches(q, sym, signal, reason)`); columns Time · Instrument (`symChip`) · TF · Signal (`sigSpan`) · Verdict badge (· retest level) · Entry/SL/TP1 · R:R · Outcome (status + R, or "untracked") · Reason (one line, full text in `title`); 50 rows then "Show more" (+100). Empty states: "No judged signals in this range" / "Signal Judge ledger not found".
- **Judge** column in All signals: JS key `${r.sym}|${r.src}|${r.dir}|${r.date}|${hh}` (`hh` = `r.time` floored to the hour, zero-padded) → verdict badge, else the prefilter code in muted text, else blank.
- Narrow (< 820 px): both tables in `.tbl-wrap`; the scorecard line wraps.

## Judge protocol (goes into the skill verbatim)

### Subagent prompt template

```
You are the Signal Judge for a TAT/Wash & Rinse trading wiki. You rule on each signal in a brief
using two sources only: the doctrine checklist and the precedents attached to each signal (Binni's
own past calls, as summarised in the session notes). You have no other context and must not invent
any.

Read, in this order:
1. The doctrine checklist: <CHECKLIST_PATH>
2. The brief: <BRIEF_PATH>. Its title line says how many survivors it holds (sections S1..SN).
   Read the whole file (use Read with offset/limit if needed) and confirm you have every section.
3. For any survivor whose "Chart image" line names a file, that image (Read tool).

For EVERY survivor, decide one verdict:
- take: the doctrine raises no blocking rule, the entry location is acceptable now, and the
  precedents support the direction and setup (or there are none and the checklist alone supports
  it; then confidence must be low).
- wait_retest: the setup is valid but entering now is poor (e.g. the impulse bar itself on 4H,
  room consumed > 0.5, price more than ~1 ATR from the broken level, or a controlling precedent
  says wait for the pullback). Give retest_level (the broken trigger level, the Tflow pivot or the
  near edge of the @Zone; it must lie strictly between SL and the entry) and retest_window_bars
  (1H: 1-12, 4H: 1-6).
- skip: a blocking rule applies (HTF opposed, counter-trend into intact structure, Red Folder
  imminent, Binni's recent call on this instrument goes the other way or says skip), or the trade
  is not worth its risk.
- no_ruling: the precedents genuinely conflict and the checklist does not settle it, or the
  features are too incomplete to judge. Put the question you would ask Binni in
  question_for_binni.

Confidence: high = checklist and at least two precedents agree and htf is aligned; medium = one of
those is missing; low = checklist only, or conflicting evidence.

Each precedent carries hindsight: what price did in the 10 trading days after Binni's call
(favourable / adverse / flat / unscored, with mfe/mae in ATR). It is a rough daily-bar check that
ignores her conditions, entries and stops, so it does not overrule the setup match. You may follow
an adverse precedent, but say so in the reason and lower your confidence one step for it. A
favourable precedent does not raise confidence by itself.

Precedence when sources disagree: a same-instrument call from the last 21 days ([recent]) outweighs
a similar case; a higher-similarity case outweighs a lower one; a later case outweighs an earlier
one; doctrine rules scoped to the signal's timeframe outweigh general ones. Say which precedent you
followed (controlling_cases, max 3) and why any conflicting one does not apply (distinguished).
Cite checklist rules by their R-ids.

Write <VERDICTS_PATH> as JSON exactly in this shape (no other text in the file):
{"run_id": "<RUN_ID>", "verdicts": [{"key": ..., "verdict": ..., "confidence": ...,
 "retest_level": number|null, "retest_window_bars": int|null, "controlling_cases": [ids],
 "distinguished": [{"case_id": id, "why": text}], "doctrine": ["R01", ...],
 "reason": "<= 400 chars, no | or newlines", "dissent": text|null, "question_for_binni": text|null}]}
Use each survivor's key exactly as written in its section heading, one verdict per survivor, and
only case ids that appear in that survivor's precedents. Then reply with one line:
"verdicts written: N of N".
```

If the slot session cannot spawn a subagent, the slot agent follows the same template inline.

### Doctrine checklist acceptance

`reference/doctrine-checklist.md` is acceptable when:
- it has at least 15 rules with ids `R01…`, each one line ending with a citation to a concept-page claim (`wiki/concepts/<page>.md`, claim number or section) or a session note;
- it covers signal tiers and Tflow / `@Zone` strength, retest rules per timeframe (including the retest-execution claim 16 vs 2/6/17 conflict, stated as a scoped pair), HTF permission, structure / break of structure, room to target and R:R, Wash & Rinse wash-line confirmation (marked "not machine-checked in v1"), D-Zones as take-profit/stop references, Red Folder news, and Friday / late-week entries;
- ids are never reused. Sources: `wiki/concepts/{tat,tflow,wash-and-rinse,d-zones,market-structure,retest-execution,trading-confluence}.md` and the session notes (the h4-signal-validation `reference/doctrine.md` lives only on the MacBook and is not required).

## UX flow

Unattended slot (Mac mini, after the user applies the Orca prompt change), inside each "TAT Combined 1H+4H Review" run:
1. 1H leg + its new-alert screenshots; 4H leg + its new-alert screenshots (unchanged).
2. **Signal Judge**: `python3 scripts/signal_judge.py run` (foreground, Bash timeout 600000 ms) → `PACKET <path>` (or `SKIPPED …`, exit 10, at 17:01 and on weekends).
3. If `run` exited 0 and the packet has survivors: spawn **one** `general-purpose` subagent with the template (brief path, checklist path, verdicts path, run id), or judge inline if spawning isn't possible.
4. If `run` exited 0: `python3 scripts/signal_judge.py apply --packet <path>` (foreground, Bash timeout 600000 ms), with or without survivors.
5. My-Watchlist 4H sweep, then the 4H currency-strength scan (unchanged steps, now after the judge).

Manual run (Claude Code session, "run the signal judge"): steps 2–4. On the MacBook use `run --dry-run --out <scratch dir>` and stop there, or set both `SIGNAL_JUDGE_DATA_DIR` and `SIGNAL_JUDGE_REPORT_DIR` to scratch paths to exercise the full loop without touching synced files.

Ingest (new step 7 in `trading-transcript-ingest`, for note types matched by `pending`), after the hot-cache rewrite:
1. Extract cases per `reference/case-extraction.md` into `scripts/signal_judge_runs/cases_<note-stem>.json`.
2. `python3 scripts/signal_cases.py add --note <path> --file <that file>`; delete the staged file on exit 0.
3. `python3 scripts/signal_cases.py score`.

Backfill (one-off, during implementation, on the Mac mini): `pending` → subagents, 5 notes each, up to 4 in parallel, each writing staged files → `add` per note → `score`.

Mac mini setup (before enabling): create `scripts/signal_judge_config.json` with `{"writer_host": "pepper"}`; run `python3 scripts/signal_judge.py run --dry-run --ignore-skip-window --out <dir>` once; do the Orca permission check (§Unattended).

## Timing

- Inside 4 of the 5 Combined runs (06:01 / 09:01 / 13:01 / 21:01 SGT), right after the 4H leg; not at 17:01 and not on weekends (`run` enforces both with skip windows, exit 10, so the single shared Orca prompt stays the same for every slot). No new schedule.
- The 06:01 run starts while the 05:01 Daily Brief (~30–35 min) and the 05:45 Daily Signals (~45 charts) may still hold TradingView; the slot's own TAT legs already queue behind them. The judge's chart pass then waits at most 120 s for the lock and, if still busy, skips (retryable); the 09:01 run picks those alerts up.
- Bars come from TradingView and entry is measured at run time, so slot alignment to bar closes doesn't matter. In winter the latest FX 4H bar at a 09:01 run closed at 06:00; the judge rules on the price at ~09:20.
- Freshness: 1H alerts ≤ 6 market hours old, 4H ≤ 12, at the run. The overnight gap (21:01 → 06:01) makes most late-evening 1H alerts `STALE` (recorded and counted, not tracked).
- Runtime per run: fresh chart candidates are typically 10–25 unique symbols (capped at 24).
  - `run`: sheet ~20 s, session start ~30–60 s (≤ 360 s worst case, then the pass is skipped), pass ≈ 8–12 s per symbol ≈ 1.5–4 min (≤ 300 s), Yahoo ~10–30 s, stop ~15 s → typically 3–6 min, hard-capped at 540 s.
  - Judge: ~2–4 min. `apply`: tracker ~30–90 s (≤ 150 s) + report ~5 s.
  - Total ~6–11 min, delaying the watchlist sweep by the same amount. The Monday 06:01 run (after a weekend of alerts) is the likeliest to hit the cap; unreached alerts stay retryable for 09:01.

## Data contract

Reads: the H1 and 4H sheet tabs (+ the Tflow extract sheet, via `fetch_with_service_account`); TradingView via `tv_judge_pass.mjs`; the Yahoo chart API (1H, 1D); `~/tradingview-mcp/daily_brief/<date>.json`; `wiki/notes/economic-calendar.md`; session notes and `raw/` transcripts (extraction / quote checks); `wiki/images/*_chart.png` (reuse); `.agents/skills/signal-judge/reference/doctrine-checklist.md` (judge + validation).

Writes:

| Output | Format | Writer | Consumers |
|---|---|---|---|
| `wiki/notes/signal-judge/cases.jsonl`, `notes_done.json` | JSONL / JSON | `signal_cases.py add` + `score` (the ingesting machine) | `signal_judge.py` (read), `signal_cases.py` |
| `wiki/notes/signal-judge/ledger-YYYY-MM.json` | JSON, monthly shards | `signal_judge.py` on the writer host | `signal_judge.py`, `signal_judge_stats.py`, `dashboard/wiki_data.py signal_judge()` |
| `scripts/signal_judge_runs/<run_id>_packet.json`, `_brief.md`, `_verdicts.json` | JSON / MD | `run`, the judge | the judge, `apply`; pruned after 90 days |
| `scripts/signal_judge_runs/cases_<stem>.json` | JSON array | extraction subagent | `signal_cases.py add`; deleted after exit 0 |
| Pass temp files `$TMPDIR/sj_pass_<pid>_{req,out}.json` | JSON | `run` / `tv_judge_pass.mjs` | `run`; deleted after the pass |
| `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md` | Markdown, same-day append | `apply` on the writer host | user, `update_weekly_index.py`, dashboard (`openDoc`) |
| `wiki/log.md` | `append_log.py` (actions `report`, `error`) | writer host | user |
| `wiki/index.md` weekly section | `update_weekly_index.py` | writer host | user |

Not touched: the TAT alert report, `scripts/h4_signal_watches.json`, existing dashboard parsers, `binni_alert_analysis.py`, `wiki/index.md`'s category sections (`update_index.py` has no reports category; reports reach the index through the weekly section, like the TAT and Daily Signals reports).

**Sync**: `fcntl` locks are local; safety comes from single writers (ledger + report: the Mac mini; case files: whichever machine is ingesting, one ingest at a time). The judge runs on the Mac mini, so the only cross-machine dependency is case files written by a MacBook ingest. If the sync test shows `.jsonl`/`.json` files don't sync: case extraction (ingest step 7) runs on the Mac mini only, via `pending` at the start of each ingest session there, and the MacBook dashboard shows "ledger not found". No other change.

## TradingView session use

One batch per `run`: `tv_session.sh start` (lock wait ≤ 120 s, fail-on-timeout, owner token) → one `tv_judge_pass.mjs` process over ≤ 24 symbols (2–3 timeframes each, ~8–12 s per symbol) → `tv_session.sh stop` (owner-checked) in `finally` and in the signal handler, whenever start was invoked and did not exit 75. No screenshots. It sits in the slot after the 4H leg's screenshot batch has stopped and before the watchlist sweep starts; the lock and owner token cover any collision with another job.

## Unattended behaviour

- No prompts, no retry loops inside a run; retryable alerts are picked up by later runs (up to 3 attempts).
- The scripts log their own failures on the writer host (§6). The Orca prompt does not log again.
- On a non-zero `run` the prompt skips the judge and `apply`: exit 10 silently; exit 6 → the message goes into the slot's final summary; anything else → continue with the next step.
- `run` is bounded at 540 s with per-call timeouts; Node is killed by process group; a SIGTERM still stops TradingView if this run owns the lock. `apply` is bounded by its tracker budget.
- If `apply` never runs, the next `run` ages `pending` entries to `unjudged_error`.
- Interpreter: plain `python3` from the repo root (what Orca uses).
- Orca permission check (Mac mini, before enabling), in a session started the way the automation starts (`claude --model sonnet --effort high`, workspace `/Users/chriseah/obsidian/wiki-trades`): the session can spawn a `general-purpose` subagent; the subagent can Read a PNG under `wiki/images/` and **Write** a file under `scripts/signal_judge_runs/` without a permission prompt. If spawning is refused, use the inline fallback; if Read of images prompts, the template's step 3 is skipped (images are optional); if Write prompts, add the allow rule to the project's `.claude/settings.local.json` (with the user's OK).

## Docs to update

- **AGENTS.md** (additive edits; the Mac mini copy has uncommitted changes of its own, which are kept):
  - New Workflow note **Signal Judge Rule**: when it runs (after the 4H leg in the Combined runs, not 17:01, not weekends), the writer host and config file, the outputs, advisory only, that the slot step lives in the Orca prompt, and the Related finding as one line.
  - Correct the Combined-slot times (06:15 → 06:01, one automation `38849272`; the 06:15 automation is disabled) where AGENTS.md describes them.
  - Edit the **My-Watchlist 4H Screenshot Rule** ("Immediately after the 4H leg…" → "after the 4H leg and the Signal Judge step…").
  - Categories: `wiki/reports/tat_analysis/signal_judge/` and `wiki/notes/signal-judge/`. Lint exceptions: `wiki/notes/signal-judge/*.json*` are data files, not pages. Tooling: the four scripts.
- **New** `.agents/skills/signal-judge/SKILL.md`: when to use; Run / Judge / Apply; the prompt template and inline fallback (verbatim from this doc); verdict semantics; writer host + config + setup; the Orca snippet; the observed bar-close hours once Verification 5 records them. Plus `reference/doctrine-checklist.md` (acceptance criteria above) and `reference/case-extraction.md` (protocol, JSON schema, the §1 vocabulary, two worked examples from `wiki/AHH Session Notes/2026-10-27-ahh-access-time.md`: GBPAUD short; GBPJPY "not yet").
- `.agents/skills/trading-transcript-ingest/SKILL.md`: bookkeeping step 7 (case extraction + score). That skill's steps 1 and 5 still file session notes to `wiki/sources/` with `--category sources` (moved to `wiki/AHH Session Notes/` on 2026-09-27) — reported to the user, not fixed here.
- `.agents/skills/tat-alert-analysis/SKILL.md` §4: new rule 8 "Signal Judge step"; edit rule 7's "Immediately after that 4H leg completes" to "after the 4H leg and the Signal Judge step (rule 8) complete".

**Orca prompt change** (automation "TAT Combined 1H+4H Review", `38849272`; the user applies it with `orca automations edit`). Insert, right after the sentence ending "…in two sequential batches (1H symbols first, then 4H symbols - …)." and before "After the 4H leg completes and its new-alert screenshots are captured, run the My-Watchlist…":
> Then run the Signal Judge step per `.agents/skills/signal-judge/SKILL.md` §Run: (1) `python3 scripts/signal_judge.py run` as one foreground Bash call (timeout 600000 ms). If it exits 10 (17:00 slot or weekend), skip the rest of this step silently. If it exits 6, include its message in your final summary and skip the rest of this step. On any other non-zero exit, skip the rest of this step. (2) If it exited 0 and the packet has survivors, spawn one general-purpose subagent with the skill's prompt template (or judge inline if you cannot spawn). (3) If it exited 0, run `python3 scripts/signal_judge.py apply --packet <path>` (foreground, timeout 600000 ms). The scripts log their own errors.

and change "After the 4H leg completes and its new-alert screenshots are captured, run the My-Watchlist 4H Screenshot Protocol" to "After the Signal Judge step, run the My-Watchlist 4H Screenshot Protocol". (Per the prompt-drift memory, the prompt points at the skill rather than copying it.)

## Failure modes

| Breakage | What the user sees |
|---|---|
| One sheet tab fails | Run section with a ⚠️ line; the other tab is judged |
| Both tabs fail | No run section; `wiki/log.md` error entry; exit 3 |
| Extract sheet unreadable (Tflow supplement skipped) | ⚠️ "Tflow / @Zone tags unavailable this run"; plain signals judged; error logged |
| TradingView lock busy > 120 s / start fails / budget short | ⚠️ "chart pass skipped"; candidates retryable `NO_DATA`, judged by the next run while fresh; the other job is untouched (owner token) |
| Pass overruns / symbol cap | Unreached symbols retryable `NO_DATA` "run budget exceeded" / "chart pass cap" |
| TradingView serves the wrong symbol or timeframe | That read discarded ("symbol / timeframe not confirmed", "bar spacing mismatch"), retryable |
| Market closed at read (daily break, holiday) | `CLOSED`, retried next run, not counted as an attempt |
| 17:01 run, weekend run | `run` exits 10; nothing judged until the next eligible run |
| Delayed alert batch | Matched to the bar that closed before it; `delayed_alert_min` shown to the judge |
| Yahoo down | Tracked metals/indices `NO_DATA` (retryable); FX unaffected at `run`; the tracker leaves entries OPEN |
| Judge fails / invalid JSON / misses a survivor | ⚠️ "judge unavailable" or "no verdict returned"; those entries `unjudged_error`, still tracked |
| One invalid verdict | ⚠️ Unjudged with the validation error |
| No cases yet / cases didn't sync | Precedents empty; the judge rules from the checklist at low confidence, or no_ruling |
| Ledger shard corrupt | `run`/`apply`/`track` exit 5 without writing; the dashboard shows the read error |
| Not the writer host / config missing on the mini | Exit 6; the slot's final summary shows it |
| Futures roll changes basis mid-trade | Entries spanning a roll can be off by the roll gap; accepted for v1, noted in the skill |
| Hallucinated extraction quote | `add` rejects the case |

## Verification criteria

1. **Fixture checks** `scratch/check_signal_judge.py` (plain `python3`, no network, no TV; it imports the modules and replaces `fetch_with_service_account`, `yahoo_bars`, the TV session command and the Node pass with stubs), each an assert:
   - **Signal bar**: a 4H series with a 3-hour session-end bar as the last bar → a 05:00:04 alert maps to it (accepted although last); a Sunday-open 1H bar maps; a 1H alert delayed to 15:16 maps to the bar closing 15:00 with `delayed_alert_min` 16; an alert with no bar → `NO_DATA` "no TradingView bar" retryable once.
   - **Read validation**: a read whose `state.resolution` is `60` when `240` was requested → discarded "timeframe not confirmed"; a 240 read with 1-hour bar spacing → "bar spacing mismatch"; a read with exactly 500 labels → `labels_capped` true.
   - **Market open**: a metal read during the 17:00–18:00 NY break (last bar start > 2 T old) → `CLOSED`, attempts unchanged.
   - **Tflow regex** on these real Event strings:
     - EURNZD `Tflow Bullish Signal @Zone (Support Zone x5 (M,W), Zone High: 1.95478, Zone Low: 1.94507): D Level: 1.96230, LL: 1.95398. Filtered: None.` → at_zone, count 5, tfs `M,W`, high 1.95478, low 1.94507, d_level 1.96230, LL 1.95398.
     - NZDCHF `Tflow Bullish Signal @Zone (Support Zone x1 (W), Zone High: 0.46350, Zone Low: 0.46290): D Level: 0.46873, LL: 0.46328. Filtered: None.` → count 1, tfs `W`.
     - AUDCHF `Tflow Bullish Signal: D Level: 0.58238, LL: 0.57036. Filtered: None.` → at_zone false.
     - JPN225 `Tflow Bearish Signal: D Level: 64316.07, HH: 64576.07. Filtered: None.` → bearish, HH.
     - `Tflow Bullish Signal broken text` → parse_error.
   - **Dedupe**: US30 `OptBear` 2:00:06 + `LBear` 2:00:04 → one alert (OptBear, also_fired [LBear]); XAUUSD `Tflow SBull 02:01:03` + `SBull 2:01:02` → one alert (`Tflow SBull`).
   - **Market hours / window / STALE**: with the run at Monday 2026-11-09 06:01 SGT (EST, so the weekend closure is Sat 06:00 → Mon 06:00 SGT): a 1H alert closing Friday 2026-11-06 21:00 SGT → 57.02 − 48 = 9.02 market hours, inside the 12 h window but > 6 → recorded as `STALE`; a 4H alert closing Saturday 02:00 SGT → 4.02 → candidate; a 4H alert closing Friday 14:00 SGT → 16.02 → outside the window, not looked at. A run at Saturday 10:00 SGT → exit 10 "weekend". A run at Tuesday 17:20 SGT → exit 10; with `--ignore-skip-window` it runs.
   - **Rank**: two Tflow LBull @Zone survivors with R:R 1.5 and 3.0 plus a plain OptBull with R:R 5 → order: @Zone 3.0, @Zone 1.5, plain OptBull; with a 2-slot judge cap the plain one is `unjudged_cap` and appears in `capped`.
   - **Tag mapping** from two hand-built feature dicts (Tflow @Zone with-trend; counter-trend with an ahead level at 0.6 ATR and a Red Folder row) → exact expected tag sets, incl. location exclusivity and the ATR-null case; an index alert → `cross_pair.score` null; a higher-TF read without the TAT study → `htf.bias` null and the daily-brief fallback is used; the `friday` flag true for a bar closing Saturday 02:00 SGT (Friday 13:00 NY) and false for Friday 13:00 SGT (Friday 00:00 NY).
   - **find_precedents** on a 5-case fixture: expected order; a case below 0.45 dropped; unspecified components excluded from the max; a same-day case excluded; instrument_recent limited to 21 days; `US100` and `NASDAQ` cases match an `NDQ100` signal.
   - **Verdict validation**: a wrong enum, a retest beyond SL, an unknown case id, an unknown R-id, no_ruling without a question, `|` in the reason, and a survivor with no verdict each → `unjudged_error`; a valid file passes.
   - **Tracker** on synthetic Yahoo 1H bars: TP1 first; SL first; same bar SL + TP → SL; EXPIRED R sign for a short; OPEN_RUN_EXPIRED; wait_retest fill then TP on the fill bar; NO_FILL with `mfe_r` in units of `|retest − sl|`; basis subtraction; bars before the first full hour after entry ignored; 10-day NO_DATA; an untracked-class entry never walked.
   - **Scorecard**: a fixture with TP1_HIT, SL_HIT, EXPIRED, OPEN_RUN_EXPIRED, NO_FILL, OPEN and NO_DATA entries → exact resolved / TP1 % / Avg R / no_fill values.
   - **Run control**: a stub `tv_session.sh` start exiting 75 → `chart_pass.ok=false`, stop never called, packet written, exit 0; a stub start exiting 1, and one timing out → stop called with the owner token; a stub stop invoked with a non-matching token leaves the stub "TradingView" running; a stub pass sleeping past its deadline → Node group killed, unreached symbols retryable `NO_DATA`; `budget.remaining() < 300` before the pass → pass skipped; both sheet stubs raising → exit 3; a captured `Tflow supplement skipped` line → sheet status `ok, tflow skipped`; a held ledger lock → exit 4; a corrupt shard → exit 5 with the file unchanged; non-writer host → exit 6; only one env dir → exit 6; stdout of `run` is exactly one line.
   - **Retry**: a retryable `NO_DATA` entry (attempts 1, fresh) → candidate next run, updated in place (one entry, attempts 2), outcome reset to OPEN when it becomes PASS; after 3 attempts, or once stale, not retried.
   - **Brief**: a packet with 8 survivors × 8 precedents → brief has sections S1..S8, no line over 400 chars, under 300 lines.
   - **Case store**: an invalid enum skipped; a fabricated quote rejected; a quote with `[[USDJPY]]`/`**` markup accepted; an empty staged array → exit 0 and the note leaves `pending`; a second add without `--replace` → exit 1; `--replace` carries hindsight only when instrument, direction and verdict match; `score` retries `fetch_failed` but not `no_ticker`; the raw-transcript lookup finds `raw/2026-10-27-ahh-access-time.md` for the 2026-10-27 AHH note and picks the TAW Pro file for `2026-10-21-taw-pro` when both an AHH and a TAW file share the date.
   - **Ledger**: a `pending` entry older than 2 h → `unjudged_error` on the next run; a verdict for an aged entry is ignored with a warning; entries land in the shard of their nominal bar-close month.
2. **Sync test**: confirm with the user whether `wiki/notes/signal-judge/sync-test.jsonl` (and the `.md` control) reached the MacBook; record the answer in the skill; delete both files. Apply the §Data contract contingency if needed.
3. **Case pilot + feasibility gate** (on the Mac mini): extract the 10 most recent notes (incl. the 2026-10-27/28 Tflow sessions), `add`, `stats`, `coverage --days 14`. Report to the user and **stop for a go/no-go before backfilling the rest**. Recommendation threshold: go if ≥ 60% of replayed alerts have ≥ 1 instrument_recent case or ≥ 2 similar cases at ≥ 0.45; otherwise report the never-matched tags and propose vocabulary changes first. The user decides either way.
4. **Dry run with TradingView** (with the user's OK to open it, at a time no slot or other job is due): `run --dry-run --ignore-skip-window --out <scratch dir>`.
   - The packet and brief are written; every PASS survivor has levels, SL, TP1 (or OPEN RUN) and precedents; `chart_pass.ok` true; no read was discarded for timeframe/spacing.
   - For 2–3 survivors, compare the packet's signal-bar OHLC and trigger level against the chart (`tv ohlcv` and the TAT labels read directly).
   - For 3 FX symbols, XAUUSD and NDQ100: compare basis-adjusted Yahoo 1H closes with TradingView 1H closes over the last 24 bars; median absolute difference < 0.05% FX, < 0.15% metals/indices. Report the numbers.
   - `wiki/notes/signal-judge/`, the report directory and `wiki/log.md` mtimes unchanged.
5. **Bar closes after the US clock change**: from the dry-run packet(s), list the observed 4H bar-close hours (SGT) per class and confirm no in-scope alert hit "no TradingView bar". Record the hours in the skill.
6. **Full loop into scratch paths**: `SIGNAL_JUDGE_DATA_DIR` + `SIGNAL_JUDGE_REPORT_DIR` → scratch; `run` → judge subagent → `apply` → `track` → `stats`. Check the scratch report, including `lint_images.py` on it; ledger entry count = `counts.recorded`; the verdicts file has one entry per survivor; one embedded image opened with Read when present; `cases.jsonl` mtime unchanged.
7. **Orca permission check** (§Unattended) in a session started like the automation.
8. **Dashboard**: start a second instance, `SIGNAL_JUDGE_LEDGER_DIR=<scratch ledger dir> SIGNAL_JUDGE_REPORT_DIR=<scratch report dir> .venv/bin/python3 dashboard/server.py --port 8799`; `curl -s 'http://127.0.0.1:8799/api/judge?since=2026-11-01' | head -c 400`; ego-browser on `http://127.0.0.1:8799/#signals` at desktop width and < 820 px: the card renders, Judge-column badges appear, "Open report ↗" is present and requests `/api/doc?path=reports/tat_analysis/signal_judge/<date>-signal-judge.md` (network log; the 404 there is expected because `/api/doc` serves only `wiki/`; a real report is opened once the first unattended run has written one), the empty state shows with the ledger dir pointing at an empty folder, and the console is clean. Then stop the instance, restart the LaunchAgent instance (`launchctl kickstart -k …`) and check `/api/judge` returns the "ledger not found" shape.
9. **Unattended**: `env -i HOME=$HOME PATH=/usr/bin:/bin python3 scripts/signal_judge.py run --no-chart --dry-run --ignore-skip-window --out <scratch dir> </dev/null` from the repo root exits 0 with one `PACKET` line; without `--dry-run` and without the config file it exits 6.
10. `py_compile` on all touched Python, `bash -n scripts/tv_session.sh`, `node --check scripts/tv_judge_pass.mjs dashboard/static/app.js`; a diff review confirming `tv_session.sh` behaves exactly as before when none of the three new env vars is set.

## Out-of-scope follow-ups

- Moving the Combined slots (and other fixed-SGT assumptions) for winter time (Related finding).
- Wash-line and D-Zone box prices for all signals (needs an unrounded CDP reader for pine lines/boxes; `tv_judge_pass.mjs` is the natural place).
- Tracking the untracked class from TradingView bars.
- "Prosecutor at the order ticket": run the judge from `journal.py new` / the dashboard Log-trade form.
- Calibration report once ~200 resolved entries exist (take vs skip vs filtered, similarity vs outcome).
- Marking superseded (pre-v3) cases; weighting "affirmed/reversed" follow-ups in Weekly Reviews.
- Fixing the stale `wiki/sources/` wording in `trading-transcript-ingest`.

## Revision log

Revision 5 (2026-11-02, Mac mini) — after the user chose one more full round:
- Round-4 critic: market-hours window (C1); signal bar by close time with short bars accepted, delayed alerts, retry-once (C2); timeframe and bar-spacing read validation (C3); lock owner token + budget gate before start (C4); sync test + monthly shards under 5 MB + contingency (C5); weekend skip window + `CLOSED` market check (C6); `fetch_with_service_account` (C7); one scorecard definition (C8); brief.md for the judge (C9); `score` retries fetch failures (C10); `friday` in New York time (C11); aliases incl. US100/US500/JP225/NIKKEI225 (C12); 05:30 claim removed (C13); untracked class judged (C14, user decision); Write permission check (C15); `max_labels: 500` (C16).
- Round-4 readiness: one rank key (Q1); tracked set and outcome reset on retry (Q2); `capped` list in the packet (Q3); `_norm_sym(...)[0]`.
- Mac mini facts: 06:01 slot (one automation, daily), Equity News — Asian is an Orca automation using the lock, writer host `pepper`, dependencies already committed, the exact Orca prompt insertion point.
- Revision 4 (MacBook, never copied here) is folded in: retryable NO_DATA, Budget object, stop rule, 17:01 skip, hindsight in the prompt, Tflow-skipped detection, raw lookup, coverage without bars, cross_pair FX only, htf_bias null, per-symbol cost and cap, API cap, NO_FILL unit, dashboard field mapping, import fix.

Revisions 2–3 (2026-11-02): New York session model → replaced by TradingView bars; entry at run time; fail-on-timeout lock; budget; writer host; dedupe; case-store robustness; dashboard keys; judge prompt template and rubric.

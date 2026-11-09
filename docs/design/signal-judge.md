# Design: Signal Judge Phase 2 — the live judge

Status: **revision 11 (2026-11-03, Mac mini `pepper`), design check closed by user override** (see "Revision 11 — binding decisions"). Phase 1, the case store, is built and committed (`24de086`; design `docs/design/signal-cases-phase1.md`). This doc covers only Phase 2: the judge itself, its ledger and tracker, the report and the dashboard. Revision 5 (parked 2026-11-02) is the base; the revision log at the end lists what changed. Origin: `/eg-brainstorm` → "Case Reporter + pre-filter", then `/eg-new-feature` scope answers.

## Why

A fired TAT alert is not a trade. Nothing today turns the doctrine in the wiki (TAT, Tflow, Wash & Rinse, D-Zones, multi-timeframe, retest execution) into a consistent take / wait / skip call per signal, so the user decides by eye, sometimes at FOMO 3+ (journal: AUDUSD opened 13:19, 18 min after the 13:01 report).

The one earlier attempt, `h4-signal-validation` (`scripts/validate_h4_signals.py`), is a rules-only judge (six hard gates + a 0–10 score, 4H FX only, on demand). It ran once (2026-09-19), rejected 7/7 signals, every score was capped by a 37-day-stale Daily brief, and its 7 forward watches are still `OPEN` because nobody ran `--track`. Lessons:

1. Hard gates must be few and mechanical; judgment belongs to a judge that can weigh conflicting doctrine.
2. The best record of Binni's judgment is her own calls in the session notes (now 1,255 quote-verified cases, Phase 1), not the concept pages, which generalise and contradict themselves (`wiki/concepts/retest-execution.md` claim 16 "H1: no retest needed" vs claims 2/6/17 "wait for the retest").
3. Measurement must run with no human step.

User decisions:
- **Judged signals** (2026-11-03): **forex on the 4H only; gold, silver, WTI oil and indices on the 1H only.** Forex 1H alerts and metal/oil/index 4H alerts are counted (`out_of_tf`) and not judged. Oil = WTI only (`USOUSD`).
- **No Binni precedent → the judge does its own analysis** (2026-11-03) from the TAT signal and chart features, and the verdict is labelled `own_analysis` and scored in its own scorecard rows; its confidence comes from the doctrine checklist, not capped (2026-11-03).
- **Tflow is never skipped** (2026-11-03): if the Tflow extract sheet can't be read, alerts are held for the next run rather than judged without their Tflow rows.
- **All five slots, including 18:01** (2026-11-03; supersedes the 2026-11-02 "no judge at 17:01"). Weekends skipped.
- Instruments the tracker can't follow (no 24-hour Yahoo series) are judged but marked untracked (2026-11-02).
- Output: own report + dashboard; the TAT alert report is untouched (2026-11-01, "one home per output").
- Outcome scoring: TP1 vs SL, plus MFE in R (2026-11-01).
- Phasing: full loop, on demand first; the Orca prompt change is written here and applied by the user after a few good manual runs (2026-11-01).
- Machines: `wiki/` syncs via Obsidian Sync; the Mac mini is the only writer of the ledger and the report (2026-11-02).
- Slot order: the judge runs right after the 4H leg and its new-alert screenshots, before the My-Watchlist sweep and the 4H currency-strength scan (2026-11-02).
- Hindsight labels are shown and the judge weighs them (2026-11-02): it may follow an adverse precedent but says so and lowers confidence one step; retrieval ranking ignores hindsight.

Facts checked on the Mac mini (2026-11-03):
- Orca "TAT Combined 1H+4H Review" (`38849272-f13f-452c-93f3-2e3c38291d73`), `rrule: 1 7,10,14,18,22 * * *`, Asia/Singapore, every day incl. weekends, `--model sonnet --effort high`, workspace `existing` at `/Users/chriseah/obsidian/wiki-trades`, `reuseSession: false`. The prompt sentence the judge step goes after is quoted in §Docs.
- Other TradingView users: Equity News — US/EU 05:31 Mon–Sat, Daily Brief 06:01, Daily Signals 06:45, Equity News — Asian 17:30 Mon–Sat, `portfolio-snapshot` 20:15 Mon–Fri (launchd). Central Bank Ingest uses no TradingView.
- US standard time since 2026-11-01: forex 4H bars close 02/06/10/14/18/22 SGT; `scan_fake_breakout_setups.bar4h_start()` (commit `f002e4f`) gives the New-York-anchored 4H grid in both seasons.
- Alert volumes (last ~1,200 H1 rows / ~250 4H rows): non-FX H1 rows include XAUUSD 22, XAGUSD 20, USOUSD 18, NDQ100 24, SPX500 25, US30 23, US2000 23, JPN225 31, plus untracked GER40 23, UK100 26, FRA40 15, CN50 14, HK50 13, USDX 11, XAUJPY 31, XAUGBP 24, XAUAUD 21; out of scope: crypto, XCUUSD (copper), UKOUSD (Brent). Sheet columns: `Date, Time, Symbol, Name, Direction, Signal Type, Signal Price, Event, Subject`.
- `python3` on the Mac mini = 3.10 with gspread (what Orca runs); `/usr/bin/python3` = 3.9 without gspread; there is no `.venv`.

## Scope

In:
1. **Candidate selection + pre-filter** over the H1 tab (gid 0) and 4H tab (gid 1105950672), including the Tflow rows folded in from TAT Alert Extract_v2, limited to the judged (class, timeframe) pairs below.
2. **Chart pass**: one TradingView batch per run reading exact Eightcap bars, TAT labels, study values and the quote for each candidate symbol on its signal timeframe and the next one up.
3. **Precedents** from the Phase 1 case store via `signal_cases.find_precedents()`.
4. **Judge**: the Orca slot session itself (inline, no subagent) rules take / wait_retest / skip / no_ruling for up to 8 survivors per run, guided by the `signal-judge` skill; every verdict carries `basis` = `precedent` or `own_analysis`.
5. **Ledger + forward tracker**: tracked alerts followed to TP1 / SL / expiry with R and MFE/MAE in R on Yahoo 1H bars.
6. **Report**: `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md`, one appended section per run.
7. **Dashboard**: read-only `GET /api/judge`, a "Signal Judge" card and a Judge column on the Signals tab.
8. **Docs**: AGENTS.md, the `signal-judge` skill (extended), `tat-alert-analysis` skill, weekly index, Orca prompt text for the user.

Judged (class, timeframe) pairs:

| Class | Instruments | Judged TF | Tracked |
|---|---|---|---|
| fx | 6-letter pairs of AUD NZD GBP EUR USD CAD CHF JPY SGD CNH (`is_in_scope`) | **4H** | yes (Yahoo `<SYM>=X`) |
| metal | XAUUSD (`GC=F`), XAGUSD (`SI=F`) | **1H** | yes |
| oil | USOUSD (`CL=F`) | **1H** | yes |
| index | NDQ100 (`NQ=F`), SPX500 (`ES=F`), US30 (`YM=F`), US2000 (`RTY=F`), JPN225 (`NIY=F`) | **1H** | yes |
| untracked | GER40, HK50, UK100, FRA40, CN50, USDX (index kind); XAUJPY, XAUAUD, XAUGBP (metal kind) | **1H** | no: outcome `UNTRACKED` |

Every other symbol (crypto, copper, Brent, stocks) is counted `out_of_scope`. An in-scope symbol on the other timeframe is counted `out_of_tf`. Neither is recorded in the ledger.

Out (v1):
- Order placement.
- Daily-timeframe signals (Daily Signals owns them).
- Wash-line prices and D-Zone boxes for non-Tflow signals: the CLI's `getPineLines`/`getPineBoxes` round prices to 2 decimals (`~/tradingview-mcp/src/core/data.js:371`, `:443`), and so do label prices (`data.js:396`). `wash_lines: null`; D-Zones only from the Tflow `@Zone` text; levels are parsed from the label **text** (`parse_tat_levels`), never the rounded `price` field. Known limitation: `nearest_level` uses every TAT level label in the ≤ 500 slice with no recency filter; Verification 4 compares `tp1` / `trigger_level` with the chart to see whether superseded labels distort them.
- New screenshots: the judge reuses those the slot already captured (§4).
- Changes to `validate_h4_signals.py` and `scan_fake_breakout_setups.py` (imported only).
- Scheduling: the Orca prompt change is written, not applied (user applies it).

## Surfaces touched

New:
- `scripts/signal_judge.py`: `run` / `apply` / `track` / `stats`.
- `scripts/signal_judge_stats.py`: `scorecard()`, shared by the report, `stats` and the dashboard.
- `scripts/tv_judge_pass.mjs`: one Node process reading bars, TAT labels, study values, quote and chart state for a list of symbol × timeframe pairs.
- `.agents/skills/signal-judge/reference/doctrine-checklist.md`, `reference/judge-protocol.md` (the judging template, verbatim from §Judge protocol).
- `scratch/check_signal_judge.py`: fixture checks (tracked in git like `scratch/check_signal_cases.py`).
- Data: `wiki/notes/signal-judge/ledger-YYYY-MM.json` (monthly shards), `judge.lock`. Local: `scripts/signal_judge_runs/` (packets, briefs, verdicts; already gitignored).

Changed:
- `scripts/signal_cases.py` (Phase 1), one shared alert loader for both phases:
  - **Oil class**: `OIL = {"USOUSD"}`; `instrument_class()` returns `"oil"` for it (checked after index, before untracked); `class_kind` passes it through; `YAHOO["USOUSD"] = "CL=F"`; `instrument_currencies("USOUSD") = ["USD"]`; aliases `USOIL`, `WTI`, `CRUDE`, `CL1!` → `USOUSD`. `run_coverage`'s class tuples (`signal_cases.py:1024`, `:1029`) gain `"oil"`. With the ticker in place, the next `score` hindsight-scores the stored USOUSD cases (expected; they were `no_ticker` before). No `similarity()` change: `class_kind("USOUSD")` already returns `oil` for those cases.
  - **New `nominal_close(sym, tab, at)`** (§2 rule) replaces the hour-floor at `signal_cases.py:831`, so Phase 1's `coverage` and Phase 2 key alerts the same way. Non-FX 4H rows (Phase 1 `coverage` only; Phase 2 never judges them) use the 1H rule on the hour grid with the symbol's minute offset: an approximation that only affects the replay.
  - **`load_alerts(rows_by_tab, since)`** keeps its signature, return value `(alerts, skipped)` and Phase 1 semantics (`direction` long/short, `alert_time` = the group's earliest row), and gains: `nominal_close` keying, the delayed-row split (§2), and `row_times` (list of `[Date, Time, Symbol]` raw sheet strings of the group's rows) plus `signal_price` / `signal_price_kind` (§2) on each alert.
  - **New `load_judged_alerts(rows_by_tab, cutoff, context_since)`** for Phase 2 → `{"alerts": [...], "context": [...], "skipped": int, "counts": {"rows_in_window", "out_of_scope", "out_of_tf"}}`. `context` = every deduped group of an in-scope class on either tab (judged pair or `out_of_tf`) whose nominal close is ≥ `context_since` (Phase 2 passes `run_start − 24 h`, calendar hours), built with the same grouping and before any ledger drop; `other_tf_alert`, `cross_pair` and `laggard` (§4) read it, never `alerts`. Order per row: parse Date/Time (skip unparseable → `skipped`); signal minus `Tflow ` in `SIGNAL_TIER` and `Direction` ∈ Bullish/Bearish, else ignored; nominal close ≥ `context_since` (else ignored) → eligible for `context`; nominal close ≥ `cutoff` → counted in `rows_in_window` and eligible for `alerts`; class/TF filter (§Scope table) → `out_of_scope` / `out_of_tf`; then the same grouping as `load_alerts`. Each alert also carries `direction_tv` (Bullish/Bearish), `alert_dt` (the chosen row's time) and the chosen row's `tv_symbol`. Phase 2 maps `direction` long → Bullish, short → Bearish for the helpers, keys and ledger.
  - **New `market_cutoff(run_dt, hours)`**: the instant `hours` market hours before `run_dt` (walking back over weekend closures, §2); Phase 2 passes `cutoff = market_cutoff(run_start, 12)`.
  - `coverage --judged-only` uses that filter. It stays a sheet-only replay (Phase 1 tags: no location or structure), so it is a lower bound on the live hit rate; the live rate is reported by `signal_judge.py stats` (§5).
  - Reused unchanged by Phase 2: `fetch_tabs()` (the try/except + Tflow-skipped capture described in §2), `load_calendar()`, `find_precedents()`. Not reused: `alert_tags()` (the sheet-only tagger; Phase 2 tags from the chart, §4) and `brief_bias_lookup()` (Phase 2 needs the age; it uses its own `daily_brief_entry`, §4).
- `scripts/tv_session.sh` (defaults unchanged for every other caller; all are opt-in env vars):
  - `TV_LOCK_DIR` (default `/tmp/tradingview-desktop-cdp.lock`), tests only.
  - `TV_LOCK_MAX_WAIT_SECS` (default 600) replaces the hard-coded `LOCK_MAX_WAIT_SECS=600`.
  - `TV_LOCK_FAIL_ON_TIMEOUT=1`: when the wait runs out, print the holder's `info` and `exit 75` without launching or touching the lock (today `tv_session.sh:77-80` proceeds anyway).
  - `TV_LOCK_OWNER=<token>`: `start` appends ` owner=<token>` to the `info` line. If `start` then fails after launching TradingView (the "Refusing to proceed" layout branch, `tv_session.sh:150-156`, or any later `exit 1`) and the variable is set, it quits TradingView itself (the same osascript → 3 s → `pkill -9` sequence as `stop`) before `release_tv_lock`, so a failed start never leaves TradingView open. `stop` with the variable set first checks the lock: if `$LOCK_DIR` is missing or its `info` has no `owner=<token>`, print `not the lock owner; leaving TradingView alone` and exit 0 without saving the layout, quitting or killing anything. Without the variable both behave as today.
- `scripts/force_tv_visible.mjs`: export `forceVisible()`; standalone use unchanged.
- `scripts/update_weekly_index.py` (build on the working tree, which already has uncommitted user edits — stage only this feature's hunks): a Signal Judge block in `scan_reports_for_date()` and an `r_type == "signal_judge"` branch in `extract_report_summary()`.
- `dashboard/wiki_data.py` (`signal_judge(since, until)`; imports `scripts.signal_judge_stats` via the repo-root `sys.path` insert it already does at `wiki_data.py:1178`; `_norm_time` AM/PM conversion), `dashboard/server.py` (route), `dashboard/static/app.js`, `dashboard/static/style.css` (verdict badges).
- `.agents/skills/signal-judge/SKILL.md` (Phase 2 sections), `.agents/skills/tat-alert-analysis/SKILL.md`, `AGENTS.md`.

Imported, unchanged:
- `scripts/validate_h4_signals.py`: `parse_tat_levels(entry, ref)`, `triggering_level`, `nearest_level`, `find_swings(bars, upto_idx, lookback)`, `latest_swing`, `tat_bias`, `ema_from_bars`, `gate_convincing_close`, `gate_room_to_target`, `gate_break_of_structure`, `elbow_invalidation`, `cross_pair_consistency`, `risk_scale_position`, `is_in_scope`, `clean_symbol`, `SIGNAL_TIER`, `TFLOW_PREFIX`. They take bar dicts `{"dt", "open", "high", "low", "close"}` and an `entry` dict shaped like a `tv` read (`{"tatLabels", "indicators"}`); `tv_judge_pass.mjs` output is mapped into that shape (§4).
- `scripts/scan_fake_breakout_setups.py`: `bar4h_start`, `SGT`.
- `scripts/signal_cases.py`: `find_precedents`, `load_cases`, `canon_instrument`, `instrument_class`, `class_kind`, `instrument_currencies`, `yahoo_ticker`, `parse_tflow_event`, `wilder_atr`, `check_writer`-style host check (reimplemented against the same config file, §6).
- `scripts/fetch_google_sheet.py`: `fetch_with_service_account` (the route that folds in Tflow rows).
- `scripts/report_toc.py`: `upsert_toc`; `scripts/append_log.py`, `scripts/update_weekly_index.py` as subprocesses.

External services: Google Sheets (service account), Yahoo chart API (unauthenticated), TradingView Desktop via CDP. No new sources.

Interpreter: `python3` as resolved on the Mac mini's PATH (3.10 with gspread). Code stays 3.9-compatible. Before loading the sheet, `signal_judge.py` checks `importlib.util.find_spec("gspread")`; missing → log + exit 3 `gspread not importable from <sys.executable>` (inside `fetch_tabs` the ImportError would only show as two failed tabs). It sets `socket.setdefaulttimeout(20)` itself before calling `fetch_tabs()`.

## Interfaces

### 1. Phase 1 contract used here

`find_precedents(signal, cases, top=5, threshold=0.45)` with `signal = {"instrument", "direction": "long"|"short", "time": aware datetime (signal bar close), "tags": {...}}` returns `{"instrument_recent": [case + same_direction], "similar": [case + similarity, substantive, same_direction]}` (`scripts/signal_cases.py:756`). Cases carry `presenter`, `hindsight`, `quote`, `verdict`, `condition`. Cases are read once per run with `load_cases()` (env `SIGNAL_CASES_DIR` honoured).

### 2. Candidate selection, dedupe and pre-filter

Load both tabs with `signal_cases.fetch_tabs()` (Phase 1: `fetch_with_service_account("H1")` / `("4H")`, each in try/except inside `contextlib.redirect_stdout(buffer)`, buffer echoed to stderr; the socket timeout is set by `signal_judge.py`). `fetch_tabs` is changed to return the Tflow-skipped flag **per tab** (`{"1H": bool, "4H": bool}` instead of one bool; Phase 1's `run_coverage` and `coverage` output treat it as "any tab"). A tab that raises, returns None or 0 rows is failed.

**Tflow is never skipped** (user decision 2026-11-03). If a tab's Tflow supplement was skipped (the TAT Alert Extract_v2 sheet was unreadable), `run` waits 10 s and fetches that tab once more. Still skipped → that tab is `tflow_unavailable`: none of its alerts is judged this run. They are recorded as retryable `NO_DATA` "Tflow data unavailable" (attempts not counted, §2 Steps), the report shows ⚠️ "Tflow sheet unreadable: <tab> alerts held for the next run", and an `error` is logged. The next run judges them with their Tflow rows while they are still fresh; if the extract sheet stays down long enough, they go `STALE` (stated in the skill).

Parse `Date` + `Time` (`%H:%M:%S`, `%H:%M`, `%I:%M:%S %p`, `%I:%M %p`) as SGT → `alert_dt`. Symbol: `canon_instrument(clean_symbol(Symbol))`; the sheet's `Symbol` as written is `tv_symbol` (e.g. `EIGHTCAP:NDQ100`). Direction: `Direction` column (`Bullish`/`Bearish`).

**Class/TF filter** first: `instrument_class(sym)` and the tab → judged pair per the Scope table, else counted `out_of_scope` / `out_of_tf` and dropped.

**Bar grid** (1H minute offset per symbol, measured on Eightcap 1H bars via TradingView OHLCV on 2026-11-03): `GRID_OFFSET_MIN = {"XAUUSD": 1, "XAGUSD": 1, "XAUJPY": 1, "XAUAUD": 1, "XAUGBP": 1, "GER40": 15, "HK50": 15}`; every other symbol 0 (USOUSD, NDQ100, JPN225 checked on the hour). Metal 1H bars start at hh:01 and close at hh+1:01, which is why every metal alert on the sheet is stamped hh:01. 4H (FX only) follows `bar4h_start` (New York grid). Python derives each symbol's observed grid from its signal-TF read: non-FX → `features.grid_offset_min` = the modal `start` minute of the last 20 `60` bars; FX → whether the last 20 `240` bar starts all equal `bar4h_start(start)` (offset recorded as 0, else null). A mismatch with the table goes into the packet's `grid_mismatch: [{"symbol", "tf", "expected", "observed"}]` and a ⚠️ report line; the matched bar (§4) still decides the key.

**Nominal bar close** (`signal_cases.nominal_close`; for grouping, keys and freshness before the chart pass) = the latest grid close at or before `alert_dt + 120 s`: 1H = `floor_hour(alert_dt + 120 s − offset) + offset`; 4H = `bar4h_start(alert_dt + 120 s)`. Examples: 15:00:04 → 15:00; 14:59:58 → 15:00; 15:16 → 15:00; XAUUSD 10:01:05 → 10:01; GER40 10:15:03 → 10:15; FX 4H 06:00:04 → 06:00 (standard time).

**Market hours** between two instants = calendar hours minus the overlap with each weekend closure, Friday 17:00 → Sunday 17:00 `America/New_York`.

**Window**: rows whose nominal bar close is ≥ `market_cutoff(run_start, 12)`, with a valid tier (both inside `load_judged_alerts`). Older rows are not looked at.

**Dedupe**: group by (symbol, tf, direction, nominal bar close). Inside a group, a row more than 10 min after the group's earliest row is a **delayed row**: it starts its own group with provisional key `<key>#d` (rows of one bar normally arrive within seconds; the sheet shows delayed batches, e.g. 1H rows at 14:54–15:27 on 2026-10-21). One alert per group: `signal` = the Tflow row's if any, else the highest tier (Opt > L > S); `tflow` = `parse_tflow_event(Event)` of that Tflow row; `event`, `alert_dt` from the chosen row; `signal_price` = the Signal Price of the group's plain (non-Tflow) row with the chosen base signal if one exists (`signal_price_kind: "level"`: the TAT level the bar broke, `validate_h4_signals.py:961-965`), else the Tflow row's (`"tflow"`: a pattern/D-level price that can repeat across bars, never used for matching); `also_fired` = the other rows' signals.

**Key** = `<SYMBOL>|<1H|4H>|<Bull|Bear>|<bar close ISO SGT>`, e.g. `GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00`. The pre-pass key uses the nominal close; every ledger entry stores it as `prepass_key`. After the chart pass the alert is keyed on its **matched** signal bar (§4): if that close differs from the nominal one, it is re-keyed (`features.rekeyed_from` = the pre-pass key) and checked against the ledger and this run's other alerts again; if the new key exists, the alert is dropped as `already_seen` (counted). All rows more than 10 min after a group's earliest row go into one `#d` group (no further splitting). A `#d` group whose matched bar equals its parent in this run is a duplicate: dropped, counted `duplicate_delayed`; if it equals a key stored by an earlier run it is `already_seen` (post-pass). In both cases its rows are **merged** into the surviving entry: their `row_times` are appended and their signals added to `also_fired`; if a merged row is a Tflow row and the surviving entry is still `pending`, `unjudged_cap` or retryable, the entry's `signal`, `tflow` and `at_zone` are upgraded to the Tflow row's (a late `@Zone` keeps its rank next run). A judged entry keeps its verdict; the merge only adds the row times so the dashboard badges the late row. A `#d` group that could not be read is stored as `NO_DATA` (retryable) under its `#d` key; when a later run reads and re-keys it, the `#d` entry is deleted and replaced by the re-keyed entry (attempts carried over), or deleted outright if it turns out to be a duplicate.

**Rank** (one sort key, used for the chart-pass order, the symbol cap and the judge cap): `(tflow_at_zone desc, tflow desc, tier desc, rr_group asc, rr desc, bar close desc)`; before the chart pass `rr_group`/`rr` are 0; after it `rr_group` = 0 for a computed R:R, 1 for OPEN RUN.

Steps:
1. **Already seen**: drop alerts whose pre-pass key equals any ledger entry's `key` or `prepass_key` (a retryable entry is matched to its current sheet group the same way, by `prepass_key`) (so a re-keyed alert is not chart-read again), except **retryable** entries: `prefilter` ∈ {`NO_DATA`, `CLOSED`}, `retryable: true`, `attempts < 3` (`CLOSED` doesn't increment `attempts`). A retried entry is rebuilt from the **current** sheet rows of its group (same key); if its rows are no longer in the window or the sheet failed, it is rebuilt from the fields stored on the entry. It is updated in place under its key.
   - Retryable `NO_DATA` reasons: chart pass skipped (lock busy, start failed, not enough budget, pass failed, `--no-chart` on a non-dry run), Tflow data unavailable, chart pass cap, run budget exceeded, symbol not read, symbol/timeframe not confirmed, bar spacing mismatch, labels not refreshed, quote mismatch, no Yahoo price, and "no TradingView bar for this alert" (retried once: `attempts < 2` for this reason).
   - **`attempts`** counts chart reads actually attempted for the alert: it goes up by one when the pass reached its symbol (whatever the read outcome) or when the alert was matched against bars. It does not go up for `CLOSED`, lock busy, start failed, not enough budget, pass failed, `--no-chart`, Tflow data unavailable, chart pass cap or run budget exceeded: those alerts are retried every run until they go `STALE`, so busy slots never use up an alert's attempts. When a retryable entry reaches its limit (`attempts` 3, or 2 for "no TradingView bar"), it is rewritten with `retryable: false`, its last code and detail, and outcome `UNTRACKED`; the report and dashboard then show it without "will retry".
2. **STALE**: market hours since the bar close > 6 (1H) or > 12 (4H) → `STALE`, final, no chart data, outcome `UNTRACKED`. A retryable entry that has gone stale becomes `STALE`.
3. **Chart candidates**: the rest, in rank order; unique symbols capped at **24**. Alerts on symbols beyond the cap → `NO_DATA` "chart pass cap" (retryable).
4. After the pass, per alert:

| Code | Rule |
|---|---|
| `CLOSED` | market closed at read time (§4) |
| `NO_DATA` | not read / read failed validation / no signal bar / no Yahoo price (tracked metal, oil, index) |
| `NO_STOP` | `sl` null, or not on the losing side of `entry_ref.price` |
| `RR_LT_1` | `tp1` exists and R:R = \|tp1 − entry\| / \|entry − sl\| < 1.0 (no level ahead = OPEN RUN, passes with `tp1` null) |
| `PASS` | everything else |

5. PASS alerts, re-sorted by the rank key: the top 8 get verdict `pending` (packet `survivors`); the rest `unjudged_cap` (packet `capped`).

**Tracked** = prefilter `PASS` (any verdict) or `RR_LT_1`, in a tracked class. All others have outcome `UNTRACKED`. When a retried entry becomes `PASS`/`RR_LT_1`, its outcome resets to `OPEN` with the new `entry_ref`.

### 3. `scripts/tv_judge_pass.mjs`

`node scripts/tv_judge_pass.mjs <request.json> <out.json>`.
- Request: `{"deadline_ms": <epoch ms>, "items": [{"symbol": "EIGHTCAP:GBPUSD", "timeframes": ["240", "D"]}, ...]}` in candidate rank order. FX (4H signal) → `["240", "D"]`; metal/oil/index/untracked (1H signal) → `["60", "240"]`.
- Imports `chart.js`, `data.js`, `ui.js` from `~/tradingview-mcp/src/core/` via `await import(pathToFileURL(join(homedir(), "tradingview-mcp/src/core/chart.js")).href)` (likewise the others). Calls `layoutSwitch({name: "0 TAW Layout"})` once, waits 2 s.
- Per item: first the same CDP call `scripts/force_tv_visible.mjs` makes (`Page.setWebLifecycleState({state: 'active'})`; `force_tv_visible.mjs` is refactored to `export async function forceVisible()` while keeping its standalone `node scripts/force_tv_visible.mjs` behaviour for `capture_tv_chart.sh`; the pass imports and awaits it with a 10 s timeout; a failure is recorded in `errors` and the item continues), because the page drops back to hidden and throttles `setSymbol`'s in-page timers (`capture_tv_chart.sh:210` does the same per call); then `chart.setSymbol({symbol})`; per timeframe: `chart.setTimeframe({timeframe: tf})`, wait 900 ms, `chart.getState()`; if `state.resolution` does not equal the requested TF (`D` also accepts `1D`), call `setTimeframe({timeframe: tf})` once more and wait 1500 ms (one retry, `retried_tf: true` recorded); then `data.getOhlcv({count: 300})`, `data.getPineLabels({study_filter: "TAT", max_labels: 500})`, `data.getStudyValues()`, `data.getQuote({})`. **Label refresh check**. All label reads use only the study in `getPineLabels`' `studies` list whose `name` starts with `TATbyBinniOng` (none → empty labels, `tat_study_missing: true`). Fingerprint = (that study's `total_labels`, its last 5 label texts, the TAT study's `getStudyValues` entry). **First timeframe of an item**: if its fingerprint equals the previous item's last fingerprint (TradingView reporting the new symbol while still serving the old symbol's labels, `validate_h4_signals.py:946-950`), or the median TAT level price parsed from the labels is more than 10 % from `quote.last`, wait 1500 ms and re-read once; still so → `labels_stale: true`. **Second timeframe**: if its fingerprint equals the first timeframe's, wait 1500 ms and re-read labels and study values once; still equal → `labels_stale: true` on that read (Python discards it: `NO_DATA` "labels not refreshed", retryable).
- After each item it rewrites `out.json` = `{"items": {"<symbol>": {"<tf>": {"state", "bars", "tatLabels", "indicators", "quote", "read_at", "retried_tf"}}}, "errors": [{"symbol", "tf", "error"}]}` so partial results survive a kill. It starts no new item once `Date.now() > deadline_ms`, records per-read errors instead of throwing, and ends with `process.exit(0)`.
- Cost: `chart.setSymbol` ~3.2 s fixed sleeps + ready-wait (`chart.js:47-99`); each TF adds ~2–3 s. Plan ~8–12 s per symbol.

**Mapping to helper shapes**: bars → `{"dt": SGT-aware datetime from bar.time (epoch s), "open", "high", "low", "close"}` sorted ascending; `entry = {"tatLabels": read.tatLabels, "indicators": read.indicators}` for `parse_tat_levels` / `tat_bias`.

### 4. Features and tags (inside `signal_judge.py`)

Helper alert dict for the imported helpers: `{"symbol": tv_symbol, "clean": SYMBOL, "direction": "Bullish"|"Bearish", "signal", "base_signal", "tflow": bool, "signal_price": float, "event", "alert_dt"}`. Signal TF read = `60` (1H) or `240` (4H); higher-TF read = `240` (1H) or `D` (4H).

**Read validation** (each symbol × TF read; failure discards the read → retryable `NO_DATA` with the reason):
- `state.symbol` ends with the ticker part of `tv_symbol` (the sheet's own name, e.g. `USOUSD` from `EIGHTCAP:USOUSD`), not the canonical alias ("symbol not confirmed");
- `state.resolution` equals the requested TF, `D` ≡ `1D` ("timeframe not confirmed"), after the one retry in §3;
- median spacing of the last 20 bar starts: 3600 s (`60`), 14400 s (`240`), ≥ 72000 s (`D`) ("bar spacing mismatch");
- metal, oil, index and FX when Yahoo answered: `|quote.last − yahoo meta.price| / meta.price ≤ 0.03` ("quote mismatch"); FX with no Yahoo answer: check skipped;
- the `TATbyBinniOng*` study's `total_labels` > 500 (data.js returns `total_labels` per study alongside the 500-label slice) → kept, `labels_capped: true`.

**Bar close times**: `close(i) = min(start_i + T, start_{i+1})` except the last bar, whose close is `start + T`. Short session-end bars (indices, metals and oil before the 17:00 NY break) close at their next bar's start if earlier.

**Signal bar** (matched bar), among closed bars with `start ≥ alert_dt − T − 6 h` and `close ≤ alert_dt + 120 s`:
- **On-time alert** (`alert_dt − nominal close ≤ 10 min`): the bar whose close equals the nominal close (`matched_by: "time"`); if TradingView has no such bar (e.g. a missing bar around the daily break), the latest bar with `close ≤ alert_dt + 120 s` (`matched_by: "time_fallback"`).
- **Delayed alert** (> 10 min, incl. `#d` groups) with `signal_price_kind = "level"`: the latest bar whose close crossed the level in the signal direction (bull: previous close ≤ P < close; bear: previous close ≥ P > close), `matched_by: "cross"`; none → latest by time (`"time_fallback"`). Delayed Tflow-only groups: latest by time.
- Constant `MATCH_DELAYED_BY_CROSS = True` in `signal_judge.py`; Verification 4 decides whether it stays on.
- Accepted even if it is the last bar. Delay > 10 min → `features.delayed_alert_min`. No bar at all → `NO_DATA` "no TradingView bar for this alert". `bar_close` = the matched bar's close.

**Closed bars for calculations**: ATR, EMA, swings and `age_bars` use bars whose close ≤ `read_at` (a forming last bar is excluded unless it is the signal bar). `age_bars` = closed bars after the signal bar.

**Market open** (closed → prefilter `CLOSED`, retryable, attempts not counted):
- the signal-TF read's last bar start is more than `2 × T` before `read_at`; or
- metal, oil, index and untracked classes: `read_at` in New York time falls Monday–Friday 17:00–17:59 (the daily break; the 2 × T rule misses it on 1H); or
- metal, oil, index: Yahoo `meta.regularMarketTime` is more than 30 min before `read_at` (FX: Yahoo is only a cross-check; if Yahoo failed or is stale for an FX symbol, the quote check and this rule are skipped and the alert is not `NO_DATA`).

**Entry reference**: `entry_ref = {"time": read_at of the signal-TF read, "price": quote.last}`. `signal_close` = the signal bar's close.

**Levels**:
- `sig_levels` = `parse_tat_levels(signal-TF entry, ref=entry_ref.price)`.
- `htf_levels_all` = `parse_tat_levels(higher-TF entry, ref=entry_ref.price)` + the `sig_levels` whose `tf` suffix is above the signal TF (1H: h4/D/W/M; 4H: D/W/M).
- `trigger_level` = `triggering_level(sig_levels, signal_close, bull, signal_bar)`.
- `tp1` = `nearest_level(sig_levels, entry_ref.price × (1 ± 0.0005), "up"|"down")`, replaced by the nearest `TP`-kind level on the same side if nearer (as `validate_h4_signals.py:960-983`, anchored on entry_ref).
- `swings` = `find_swings(bars, signal_idx, lookback=L)`, L = 120 (1H) / 60 (4H); `sl` = `elbow_invalidation(alert, signal_bar, bars, swings)`.
- `htf_levels.behind/ahead` = nearest `htf_levels_all` level behind/ahead of entry_ref, with `dist_atr = |level − entry| / ATR`.
- `ATR` = `wilder_atr` (14) on closed signal-TF bars; null with fewer than 15.

**Features** (packet and brief only, not the ledger):
```
features = {
  "close_quality": trigger_level None -> {"excursion": null, "close_pos": null, "crossed_on_bar": null}
                   else g = gate_convincing_close(alert, signal_bar, trigger_level, contemporaneous=(age_bars <= 1))
                        -> {"excursion": g.get("excursion"), "close_pos": g.get("close_pos"), "crossed_on_bar": g.get("crossed")},
  "htf": {"source": "TAT trend 4H" (1H signal) | "TAT trend D" (4H signal), "forming": true,   # read from the higher-TF bar in progress: the trend state the user sees on the chart at judging time (accepted; a forming bar can still flip)
          "bias": tat_bias(higher-TF entry), but null when the read is missing or has no study whose name starts
                  "TATbyBinniOng" exposing both "Up Trend" and "Down Trend" values,
          "daily_brief": daily_brief_entry(sym, run_start) -> {"bias", "age_days"} | null},   # files ~/tradingview-mcp/daily_brief/<D>.json whose stem parses as a date (others, e.g. test_brief_10.md, ignored), available once run_start >= max(D 06:30 SGT, file mtime) (Phase 1's availability rule, so a brief the 06:01 job is still writing is skipped), newest such D <= run date; JSON that fails to parse -> try the next older file; entry whose canon_instrument(symbol) matches; bias lower-cased; age_days = run date - D (the tag rule uses it only if <= 3)
  "room_consumed": trigger_level and tp1 -> gate_room_to_target(alert, trigger_level, tp1_level, entry_ref.price).get("consumed") else null (OPEN RUN, no tp1 -> null, not the helper's 0.0),
  "structure": g = gate_break_of_structure(alert, signal_bar, swings) ->
               {"state": g.get("structure", "Mixed"),
                "mode": g["mode"] if g["pass"] else ("counter" if latest_swing(swings, "high" if bull else "low") else "none"),
                "latest_high": price of latest_swing(swings, "high") or null, "latest_low": price of latest_swing(swings, "low") or null},
  "ema20": e = ema_from_bars(closed signal-TF bars, 20) -> {"value": e, "side_ok": entry_ref.price > e (bull) / < e (bear), "dist_atr": |entry_ref.price − e| / ATR (null if ATR null)},
  "cross_pair": fx only: (score, detail) = cross_pair_consistency(alert, X) where X = the `context` FX 4H alerts with the same bar close (before the already-seen and STALE drops) (so a sibling judged in an earlier run still counts) -> {"score", "detail"};
                other classes -> {"score": null, "detail": "not FX"},
  "trigger_level", "tp1_level": {"price", "kind", "tf"} | null,
  "htf_levels": {"behind": {...,"dist_atr"} | null, "ahead": ... | null},
  "tflow": parse_tflow_event(...) | null,
  "other_tf_alert": latest `context` alert on the same symbol in the other tab (incl. out_of_tf): for a 1H signal, a 4H alert within 24 h before its bar close; for a 4H signal, a 1H alert within 8 h -> {"tf", "signal", "direction", "hours_ago"} | null,
  "red_folder_24h": rows of the "This Week" / "Next Week" tables of wiki/notes/economic-calendar.md with Date + Time (SGT) in [entry_ref.time, +24 h] and Currency in instrument_currencies(sym) (untracked: GER40/FRA40 EUR, UK100 GBP, HK50 HKD, CN50 CNY, USDX USD; metal crosses USD + cross; oil USD) -> [{"date","time","ccy","event"}],
  "risk_scale": trigger_level and tp1 -> risk_scale_position(entry_ref.price, lower, upper, bull) with (lower, upper) = (trigger, tp1) for a long, (tp1, trigger) for a short (as validate_h4_signals.py does) else null,
  "age_bars", "delayed_alert_min": int|null, "rekeyed_from": str|null, "matched_by": "time"|"time_fallback"|"cross", "grid_offset_min": int|null, "labels_capped": bool, "retried_tf": bool,
  "wash_lines": null
}
```

**Tag mapping** (signal → case vocabulary, used for `find_precedents` and shown in the brief):
- `tf`: `1h` / `4h`.
- `setup`: `tflow` + `pullback_in_trend` if Tflow; `trend_continuation` if structure.mode = trend; `reversal` if mode = reversal; `breakout` if close_quality.crossed_on_bar; `laggard` (FX only) if among the `context` FX 4H alerts whose bar close is 1–3 bars earlier, a pair sharing a currency expressed the same move for it (GBPAUD bear = AUD strong; an earlier EURAUD bear or AUDCAD bull matches).
- `location`: `at_d_zone` if tflow.at_zone; `htf_level_behind` if behind.dist_atr ≤ 1.0; `htf_level_ahead` if ahead.dist_atr ≤ 1.0; `open_space` if no ahead level or ahead.dist_atr > 3.0 (never with `htf_level_ahead`); `at_ema` if ema20.dist_atr ≤ 0.3; `mid_range` only if none of these. ATR null → only `at_d_zone` and `open_space` (no ahead level) can apply.
- `structure`: trend → `with_trend`; counter → `counter_trend`; reversal → `transition`; none → `unspecified`.
- `htf`: htf.bias = signal direction → `aligned`; opposite → `opposed`; neutral → `ambiguous`; null → the daily-brief bias by the same rule if age ≤ 3 days, else `unspecified`.
- `risk_flags`: `news_pending` if red_folder_24h non-empty; `friday` if the signal bar closes on a Friday in New York time at or after 01:00 NY; `room_consumed` if > 0.5; `counter_trend` if mode = counter; `late_entry` if age_bars ≥ 3; `weekend_gap` if a weekend closure (Friday 17:00 → Sunday 17:00 New York) lies between the signal bar's close and `entry_ref.time`.
- `direction` for `find_precedents`: Bullish → `long`, Bearish → `short`.

**Screenshot reuse**: `chart_image` = the newest `wiki/images/<YYMMDD-HHMMSS>_<symbol lowercase>_<1h|4h>_chart.png` matching the signal TF, timestamped within 45 min before the run start; else null.

**Yahoo fetcher**: `yahoo_bars(ticker, interval, range_=None, period1=None, period2=None) -> (bars, meta)`, `interval` ∈ {`1h`}; ticker from `signal_cases.yahoo_ticker`. Drops bars with null OHLC and 1H bars whose minute ≠ 0. `meta = {"price": regularMarketPrice, "time": regularMarketTime}`. Timeout `min(15, budget)` s, no retry, per-run cache.

**Price basis** (metal, oil, index; FX 0; untracked none): `price_basis = yahoo_close(B) − tv_close(B)` where B = the most recent closed TV `60` bar for which Yahoo has a closed 1H bar starting at `B.start − grid_offset_min` (Yahoo futures bars start on the hour; metal TV bars start at :01, so the pair is 1 minute apart, accepted) (for FX/4H symbols no basis is needed). If no common closed bar in the last 6 → `NO_DATA` "no Yahoo price" (retryable). `price_basis_bar` (ISO) is stored. This replaces revision 5's live-price basis, because Yahoo futures quotes lag ~10 min. For metal/oil/index 1H signals the `60` read already exists; no extra TV read.

### 5. `scripts/signal_judge.py` CLI

```
python3 scripts/signal_judge.py run   [--symbol SYM] [--no-chart] [--dry-run --out DIR] [--force-writer] [--ignore-skip-window]
python3 scripts/signal_judge.py apply --packet PATH [--verdicts PATH] [--force-writer]
python3 scripts/signal_judge.py track [--force-writer]
python3 scripts/signal_judge.py stats [--since YYYY-MM-DD] [--json]
```
Diagnostics → stderr; subprocesses get `stdout=sys.stderr`. `run`'s only stdout is one final line: `PACKET <path> SURVIVORS <n>`, or `SKIPPED <reason>` on exit 10.

**Writer guard**: `run` (without `--dry-run`), `apply` and `track` write only when `scutil --get LocalHostName` (fallback `socket.gethostname().split(".")[0]`) equals `writer_host` in `scripts/signal_judge_config.json` (the Phase 1 file; env `SIGNAL_JUDGE_CONFIG` overrides the path, tests only; a missing or unreadable file = no writer), or with `--force-writer`; else exit 6 `not the Signal Judge writer host (<name>); use --dry-run`. Test redirection: env `SIGNAL_JUDGE_DATA_DIR` (ledger dir; the dashboard reads the same variable) and `SIGNAL_JUDGE_REPORT_DIR` (report dir) both set → guard skipped, `append_log` / `update_weekly_index` not called; only one set → exit 6 "set both"; with them set, `SIGNAL_JUDGE_RUNS_DIR` must be set too (else exit 6 "set SIGNAL_JUDGE_RUNS_DIR with test dirs"), so a scratch loop never writes a packet into the real runs dir. `--dry-run` requires `--out DIR` and writes only the packet and brief there.

**Runs dir**: `scripts/signal_judge_runs/`, or env `SIGNAL_JUDGE_RUNS_DIR` (Phase 1's override, `signal_cases.py:64`; fixtures set it).

**`--symbol SYM`**: applied right after dedupe (before already-seen and retry); everything downstream sees only that symbol's groups, `counts` describe that subset, the ledger is written as normal (non-dry run), the run_id is unchanged. Manual use only.

**`run`** — wall-clock budget 480 s (`Budget`: `deadline = time.monotonic() + 480`; `remaining()`; `cap(x) = max(1, min(x, remaining() − 90))`). No `signal.alarm`; every blocking call has its own timeout. 480 s + the 60 s stop timeout + the 90 s reserve fit inside the slot's 600 000 ms Bash timeout.
0. **Skip window** (unless `--ignore-skip-window`): inside the weekend closure (Friday 17:00 → Sunday 17:00 New York) → `SKIPPED weekend`, exit 10, nothing read or written. (No 17:00 window any more.)
1. Unless `--dry-run`: age entries with `verdict: pending` whose `pending_since` is more than 2 h before now to `unjudged_error` "judge did not run"; delete `*_packet.json`, `*_brief.md`, `*_verdicts.json` and `*_applied.json` older than 90 days from the runs dir (Phase 1's `cases_*.json` / `*.rejects.json` / `presenter_*.txt` are never touched).
2. Load, filter, dedupe, pre-chart steps (§2). Both tabs failed → log + exit 3.
3. Chart pass, unless `--no-chart` or no candidates. If `budget.remaining() < 300`, skip ("not enough budget", retryable). Otherwise:
   - Token `T = <run_id>-<pid>`. `start_invoked = True`, then `subprocess.run(["bash", "scripts/tv_session.sh", "start"], env={…, "TV_LOCK_MAX_WAIT_SECS": "120", "TV_LOCK_FAIL_ON_TIMEOUT": "1", "TV_LOCK_OWNER": T}, timeout=budget.cap(360), stdout=sys.stderr, start_new_session=True)`. On `TimeoutExpired`, kill the start's process group (`os.killpg`, SIGKILL) so no half-run start keeps launching TradingView.
   - Exit 75 → never took the lock: no chart data, `chart_pass.ok=false`, no stop.
   - Exit 0 → `subprocess.Popen(["node", "scripts/tv_judge_pass.mjs", req, out], start_new_session=True, stdout=sys.stderr, stderr=sys.stderr)` with `deadline_ms` = now + `budget.cap(300)` s; poll every 1 s; kill the group (`os.killpg(proc.pid, SIGKILL)`) if alive 20 s past the deadline or `budget.remaining() < 90`; read `out.json` as is.
   - Any other outcome → no chart data.
   - **Stop** in the `finally` of the block that wraps start + pass (so it runs right after the pass, before Yahoo, features and the ledger write, and the lock is held only for the pass) whenever `start_invoked` and start did not return 75: `subprocess.run(["bash", "scripts/tv_session.sh", "stop"], env={…, "TV_LOCK_OWNER": T}, timeout=60, stdout=sys.stderr)`. The owner check means a stop after a start that never got the lock, or after the lock was cleared by someone else, leaves TradingView alone. If start is killed between `mkdir` of the lock and writing its `info` (`tv_session.sh:57-84`), TradingView has not been launched yet (launch comes after acquire), so leaving it alone is right; the info-less lock is cleared by the next waiter once `LOCK_GRACE_SECS` passes with no TradingView process (existing rule). A SIGTERM/SIGINT handler kills the Node group and the start group (if any), runs the same stop, exits 143 / 130.
   - **Stop timeout** (60 s expired): kill the stop's process group, `pkill -9 -f /Applications/TradingView.app/Contents/MacOS/TradingView`, remove the lock dir only if its `info` contains `owner=T`, log an `error` "tv_session stop hung". So the next job (the watchlist sweep) never waits 600 s on a dead holder.
   - `tv_judge_pass.mjs` fatal errors (CDP connect or `layoutSwitch` throws before the first item): it writes `{"items": {}, "errors": [...], "fatal": "<message>"}` and exits 0; Python then sets `chart_pass.ok=false`, `skipped_reason: "pass failed"`, and every candidate → `NO_DATA` "chart pass failed" (retryable).
4. Yahoo: one 1H fetch (range `5d`) per tracked-class chart-candidate symbol (meta, quote check, basis), skipped once `budget.remaining() < 100` (→ `NO_DATA` "run budget exceeded", retryable).
5. Features, market-open check, re-keying, pre-filter, precedents (cases.jsonl missing → no cases, warning line).
6. Unless `--dry-run`: write all recorded / updated entries to the ledger.
7. Write `scripts/signal_judge_runs/<run_id>_packet.json` and `<run_id>_brief.md` (or into `--out DIR`); print `PACKET <path> SURVIVORS <n>`.

Candidates the pass did not reach → `NO_DATA` "run budget exceeded" (retryable). `run_id` = SGT `YYYY-MM-DD_HHMM` of the run start; if `<run_id>_packet.json` already exists, append `_2`, `_3`; the report heading for a suffixed run is `## 🕒 Signal Judge Run — [HH:MM SGT] (2)` so TOC anchors stay unique (the weekly-index parser takes the `HH:MM` and ignores the suffix).

Exit codes: 0 success (incl. zero candidates or a degraded chart pass); 3 both tabs failed; 4 command lock not acquired within 300 s; 5 a ledger shard is invalid JSON (never overwritten); 6 writer guard; 10 skip window (not an error, not logged). Any unexpected exception: a top-level handler prints the traceback to stderr, logs one `error` (`append_log.py`, writer host, not when the test dirs are set), runs the TradingView cleanup in `finally`, and exits 1.

**`apply`**:
1. Read the packet (missing/unreadable → exit 2; `"dry_run": true` → exit 2 "dry-run packet; nothing applied"). The packet records `data_dir`, `report_dir` and `runs_dir` as resolved by `run`; if the current resolution differs → exit 2 "packet belongs to another data dir". If `<run_id>_applied.json` exists next to the packet → print "already applied" and exit 0 without writing anything (idempotent; a re-run of the slot's step 4 is harmless). After the report section is written, `apply` writes `<run_id>_applied.json` (`{"applied_at", "report"}`) before the log/index calls.
2. Read the verdicts (default `packet["verdicts_path"]`). Survivors present and the file missing/unparseable → all survivors `unjudged_error` "judge unavailable".
3. Validate (§6) and write verdicts into entries still `pending`; entries already aged to `unjudged_error` are left alone (⚠️ line in the report). Entries the latest `run` aged to `unjudged_error` (from earlier packets) are listed in this section as one ⚠️ line: "N signals from earlier runs were never judged: <SYM TF signal>, …".
4. Tracker (§7, budget 150 s), remembering the keys it resolved.
5. Append the report section (§8); `report_toc.upsert_toc`.
6. `append_log.py --action report --title "Signal Judge Run — <date> <HH:MM> SGT" --body "<run summary line>"`; `update_weekly_index.py`.

Exit 0 when the report is written (zero survivors included); 2 unreadable packet; 4 / 5 / 6.

**`track`**: standalone tracker (§7, budget 300 s); prints the resolved count. Exit 0 / 4 / 5 / 6.

**`stats`**: the §8 scorecard over `--since` (default 30 days back), plus the live precedent hit rate (share of judged entries with `has_precedents` true, and of those with `judge.basis` = precedent), table or JSON; read-only, any host.

**Command lock**: `run` (non-dry), `apply` and `track` each hold an `fcntl.flock` on `judge.lock` in the ledger dir (`wiki/notes/signal-judge/`, or `SIGNAL_JUDGE_DATA_DIR`) for the whole command (wait ≤ 300 s, else exit 4 "another Signal Judge command is running"). This serialises a manual run against a late Orca catch-up slot, and covers this feature's ledger, report file and its own `append_log` / `update_weekly_index` calls. It does not cover other jobs: the Central Bank Statement Ingest (:10/:25/:40/:55) and the slot's own bookkeeping also call `append_log.py` / `update_index.py` / `update_weekly_index.py`, a residual risk the scheduled slots already carry today (those scripts read-modify-write in one step; no new lock is added). `--dry-run` takes no lock.

**Ledger writes** (inside the command lock): re-read the shard(s), merge by key (new keys appended; existing keys updated field by field; a re-key or `#d` replacement deletes the old key from its shard and writes the new entry to the shard of its own bar-close month in the same write), temp files in the same dir, `os.replace` each shard (new-key shard first). On load, two entries sharing a `prepass_key` (a crash between the two replaces) are collapsed to the one with the later `run_id`.

**Error logging** (writer host only): `append_log.py --action error` for exits 3/4/5, a skipped or failed chart pass (lock-busy exit 75 only when the newest other `*_packet.json` in the runs dir, which never holds dry-run packets, also has `skipped_reason` "lock busy"), an exceeded budget, "judge unavailable", Tflow-skipped. Exit 6 can't log; the Orca prompt puts it in the slot summary.

### 6. Packet, brief and verdict files

**Packet** (`<run_id>_packet.json`):
```json
{
  "run_id": "2026-11-03_1001",
  "created_at": "2026-11-03T10:21:40+08:00",
  "doctrine_checklist": ".agents/skills/signal-judge/reference/doctrine-checklist.md",
  "brief_path": "scripts/signal_judge_runs/2026-11-03_1001_brief.md",
  "verdicts_path": "scripts/signal_judge_runs/2026-11-03_1001_verdicts.json",
  "dry_run": false,
  "data_dir": "wiki/notes/signal-judge", "report_dir": "wiki/reports/tat_analysis/signal_judge", "runs_dir": "scripts/signal_judge_runs",
  "counts": {"rows_in_window": 40, "out_of_scope": 4, "out_of_tf": 9, "groups": 20, "duplicate_delayed": 0,
             "already_seen_pre": 6, "already_seen_post": 0, "retried": 2, "stale": 3, "chart_candidates": 11, "recorded": 14,
             "closed": 0, "no_data": 0, "no_stop": 0, "rr_lt_1": 2, "pass": 9, "judged": 8, "unjudged_cap": 1,
             "by_tf": {"1H": 5, "4H": 9}},
  "chart_pass": {"ok": true, "symbols": 9, "read_ok": 9, "failed": [], "budget_exceeded": false, "skipped_reason": null},   # skipped_reason ∈ null | "lock busy" | "start failed" | "not enough budget" | "no-chart" | "no candidates" | "pass failed"
  "sheet": {"1H": "ok", "4H": "ok"},   # per tab: "ok" | "failed" | "tflow_unavailable"
  "grid_mismatch": [],
  "survivors": [{
    "key": "GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00", "n": 1,
    "symbol": "GBPUSD", "tv_symbol": "EIGHTCAP:GBPUSD", "asset_class": "fx", "tracked": true, "tf": "4H", "direction": "Bullish",
    "signal": "Tflow LBull", "also_fired": ["LBull"], "alert_time": "2026-11-03T10:00:12+08:00",
    "bar_close": "2026-11-03T10:00:00+08:00",
    "entry_ref": {"time": "2026-11-03T10:18:02+08:00", "price": 1.34012},
    "sl": 1.33551, "tp1": 1.34903, "rr": 1.93,
    "features": {}, "tags": {"tf": "4h", "setup": ["tflow", "pullback_in_trend"], "location": ["at_d_zone"], "structure": "with_trend", "htf": "aligned", "risk_flags": []},
    "precedents": {"instrument_recent": [], "similar": []},
    "has_precedents": false,
    "chart_image": "wiki/images/261103-101502_gbpusd_4h_chart.png"
  }],
  "capped": [{"key", "symbol", "tf", "direction", "signal", "entry_ref", "sl", "tp1", "rr"}],
  "filtered": [{"key", "symbol", "tf", "direction", "signal", "prefilter": "RR_LT_1", "detail": "1:0.64 from entry 1.08120", "retryable": false}]
}
```
**Counts** (all per run; "groups" are deduped alerts):
- `rows_in_window`: sheet rows in the 12-market-hour window with a valid tier; `out_of_scope` / `out_of_tf`: of those, rows dropped by the class/TF filter.
- `groups`: deduped alerts after the filter (incl. `#d` groups), plus `retried` = ledger retry entries re-entering (they are part of `groups`).
- `already_seen_pre` (pre-pass) and `already_seen_post` (re-keyed onto an existing key) are separate counts; `chart_candidates` is the pre-pass value and includes alerts beyond the 24-symbol cap (recorded as `NO_DATA` "chart pass cap").
- `groups` = `already_seen_pre` + `stale` + `chart_candidates`.
- `chart_candidates` = `already_seen_post` + `duplicate_delayed` + (`closed` + `no_data` + `no_stop` + `rr_lt_1` + `pass`).
- `recorded` = ledger entries written or updated = `stale` + `closed` + `no_data` + `no_stop` + `rr_lt_1` + `pass`; `pass` = `judged` + `unjudged_cap`; `by_tf` splits `recorded`.
`has_precedents` = either precedent list non-empty.

**Brief** (`<run_id>_brief.md`, what the judge reads), one section per survivor:
```
# Signal Judge brief — run 2026-11-03_1001 — 8 survivors

## S1 — GBPUSD 4H Tflow LBull (Bull) — key GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00
- Entry 1.34012 (10:18 SGT) · SL 1.33551 · TP1 1.34903 · R:R 1:1.93 · tracked: yes
- Tags: tf 4h · setup tflow, pullback_in_trend · location at_d_zone · structure with_trend · htf aligned · risks none
- Features: one line each (close quality, htf + daily brief, room consumed, structure, EMA20, cross-pair, trigger/TP levels, HTF levels with dist_atr, Tflow zone, other-TF alert, Red Folder 24 h, risk scale, age, delay, labels capped)
- Chart image: wiki/images/261103-101502_gbpusd_4h_chart.png
### Precedents
- [recent] 2026-10-27-ahh-access-time-usdjpy-1 · 2026-10-27 · binni · USDJPY 4h long · take · cond: — · levels: 157.20 support · in transcript: yes · hindsight favourable (+1.8 ATR / −0.4 ATR) · "Dollar yen is my best candidate … for a long"
- [similar 0.62] <id> · <date> · <presenter> · <instrument tf direction> · <verdict> · cond: <condition or —> · levels: <levels ≤ 80 chars or —> · in transcript: yes|no|unknown (`quote_in_raw`) · hindsight <label (mfe/mae)>, or "unscored" when hindsight is null · "<quote ≤ 200 chars>"
(or: "- None — own analysis required (see the protocol's Own analysis section).")
```
Lines ≤ 400 chars (quotes truncated to 200 with `…`); ≤ 8 survivors × ≤ 8 precedents keeps the brief under ~250 lines.

**Verdicts** (written by the judge):
```json
{
  "run_id": "2026-11-03_1001",
  "verdicts": [{
    "key": "GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00",
    "verdict": "take | wait_retest | skip | no_ruling",
    "basis": "precedent | own_analysis",
    "confidence": "low | medium | high",
    "retest_level": null, "retest_window_bars": null,
    "controlling_cases": ["2026-10-27-ahh-access-time-usdjpy-1"],
    "distinguished": [{"case_id": "...", "why": "..."}],
    "doctrine": ["R07", "R12"],
    "reason": "1–400 chars, no | or newline",
    "dissent": null, "question_for_binni": null
  }]
}
```

`doctrine-checklist.md`: numbered rules with stable ids `R01`, `R02`, …, each one line `- **R07** <rule> — (see [<page>](../../../../wiki/concepts/<page>.md) claim N / [<note>](...))`; ids never reused.

Validation in `apply` (a failing verdict → that entry `unjudged_error` with the error text; others proceed):
- exactly one verdict per survivor key ("no verdict returned" otherwise); unknown keys ignored with a warning;
- enums as above;
- `no_ruling`: `basis` = `precedent` if it names any controlling case, else `own_analysis` (conflicting precedents go in `distinguished`; the 2-R-id rule below still applies to own_analysis);
- `basis = "precedent"` ⇔ `controlling_cases` non-empty; `basis = "own_analysis"` ⇒ `controlling_cases` empty and `doctrine` has ≥ 2 R-ids;
- `wait_retest`: `retest_level` strictly between `sl` and `entry_ref.price`; a level on or beyond `sl` by less than 0.1 ATR is moved to `sl ± 0.1 ATR` (towards the entry) with a warning instead of failing; further beyond → `unjudged_error`. `retest_window_bars` 1–12 (1H) / 1–6 (4H); other verdicts: both null;
- `controlling_cases` (0–3) and `distinguished[].case_id` are ids in that survivor's packet precedents;
- `doctrine` entries match `^R\d{2,3}$` and exist in the checklist;
- `no_ruling` needs a non-empty `question_for_binni`;
- `reason` 1–400 chars, no `|` or newline.

### 7. Ledger and tracker

**Shards** `wiki/notes/signal-judge/ledger-YYYY-MM.json` (SGT month of the bar close) = `{"version": 1, "entries": [...]}`. Entries are compact (no `features`; ~0.8–1 KB), so a month stays well under Obsidian Sync's 5 MB per-file limit. `run`/the tracker read the current and previous month's shards; the dashboard and `stats` read the shards covering their range.

Entry:
```json
{
  "key": "GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00", "run_id": "2026-11-03_1001",
  "symbol": "GBPUSD", "tv_symbol": "EIGHTCAP:GBPUSD", "asset_class": "fx", "tracked": true, "tf": "4H", "direction": "Bullish",
  "signal": "Tflow LBull", "also_fired": ["LBull"], "tflow": true, "at_zone": true,
  "alert_time": "...", "bar_close": "...", "signal_close": 1.33990, "signal_price": 1.33985, "event": "...",
  "entry_ref": {"time": "...", "price": 1.34012}, "sl": 1.33551, "tp1": 1.34903, "rr": 1.93,
  "prepass_key": "GBPUSD|4H|Bull|2026-11-03T10:00:00+08:00", "signal_price_kind": "level", "has_precedents": false,
  "price_basis": 0.0, "price_basis_bar": null, "row_times": [["2026-11-03", "10:00:11", "EIGHTCAP:GBPUSD"], ["2026-11-03", "10:00:12", "EIGHTCAP:GBPUSD"]], "pending_since": "2026-11-03T10:21:40+08:00",
  "prefilter": "PASS", "prefilter_detail": "", "retryable": false, "attempts": 1,
  "tags": {}, "precedent_ids": ["..."],
  "verdict": "take", "retest_level": null, "retest_window_bars": null,
  "judge": {"basis": "precedent", "confidence": "medium", "controlling": [{"id", "presenter", "verdict", "quote", "hindsight"}], "doctrine": ["R07"], "reason": "...", "dissent": null, "question_for_binni": null, "error": null},
  "outcome": {"status": "OPEN", "entry": null, "fill_time": null, "resolved_time": null, "bars": 0, "r": null, "mfe_r": null, "mae_r": null, "reported": false}
}
```
- `verdict` ∈ {`take`, `wait_retest`, `skip`, `no_ruling`, `pending`, `unjudged_cap`, `unjudged_error`, null (prefilter not PASS)}.
- `outcome.status` ∈ {`OPEN`, `TP1_HIT`, `SL_HIT`, `EXPIRED`, `OPEN_RUN_EXPIRED`, `NO_FILL`, `NO_DATA`, `UNTRACKED`}.
- The stored `signal_price`, `event`, `alert_time`, `tv_symbol` are what a retry rebuilds from when its rows have left the sheet window (§2). `row_times` = the raw sheet `[Date, Time, Symbol]` strings of every row in the group (the dashboard matches on them, §9). `has_precedents` = the packet value (either precedent list non-empty), stored so `stats` can report the live precedent hit rate. `pending_since` = the packet's `created_at` when the entry got `verdict: pending`, else null. `outcome.reported` = false until a report's Resolved table has listed the resolution.

**Tracker**, per tracked `OPEN` entry, grouped by Yahoo ticker: one `yahoo_bars(ticker, "1h", period1 = oldest OPEN entry_ref.time − 1 h, period2 = now)` per ticker. Yahoo prices are compared after subtracting the entry's `price_basis`. Only bars whose start ≥ the first full hour after `entry_ref.time`. Accepted bias: a stop or target touched between `entry_ref.time` and the next full hour is not seen (Yahoo has no partial bars; reading TradingView again would need another session); the skill states it.
- Entry point: `wait_retest` → the first bar within `retest_window_bars × (1 for 1H, 4 for 4H)` 1H bars whose range contains `retest_level` fills there (`fill_time` = bar start); SL/TP1 checked on that bar (stop first). No fill → `NO_FILL`, r = 0, `mfe_r` = favourable move from `entry_ref.price` over the window in units of `|retest_level − sl|`. Other verdicts: entry = `entry_ref.price`. For a filled `wait_retest` the SL/TP walk below starts at the fill bar (bar 1) and `bars` counts from it; the retest window is counted separately before it.
- `risk = |entry − sl|`. Walk up to 24 1H bars (1H signal) or 120 (4H signal):
  - range reaches SL → `SL_HIT`, r = −1 (before TP on the same bar);
  - range reaches TP1 → `TP1_HIT`, r = |tp1 − entry| / risk;
  - window exhausted → `EXPIRED`, r = (last close − entry) / risk in the trade direction; `tp1` null → `OPEN_RUN_EXPIRED`.
- `mfe_r` / `mae_r` up to resolution; `bars` = bars walked. Window not exhausted → stays `OPEN`; still `OPEN` 10 calendar days after `entry_ref.time` → `NO_DATA`.
- Budget (150 s in `apply`, 300 s standalone) stops fetching new tickers when exceeded; the rest stay `OPEN`.

### 8. Report: `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md`

Written only by `apply` on the writer host (or into `SIGNAL_JUDGE_REPORT_DIR`). The date is the run's SGT date. First run of the day creates:
```
---
type: report
date: "2026-11-03"
---

# ⚖️ Signal Judge — 2026-11-03 [10:21 SGT]

<!-- TOC:START -->
<!-- TOC:END -->
```
Each `apply` appends a section, then `report_toc.upsert_toc` regenerates the TOC. The H1 carries the first run's time and is never rewritten (Header Timestamp Rule). Every section time `[HH:MM SGT]` is the packet's `created_at` (when the judge looked), not the `apply` time:
```
## 🕒 Signal Judge Run — [10:21 SGT]

**Run summary:** run `2026-11-03_1001` · 40 alerts in window · 14 recorded (1H 5 · 4H 9) · 9 passed the pre-filter · 8 judged (precedent 5 · own 3) · verdicts: take 2 · wait 2 · skip 3 · no ruling 1 · unjudged 1 · 13 out of scope/TF · chart pass 9/9 (read_ok / symbols requested)

### Verdicts — [10:21 SGT]
| Instrument | TF | Signal | Verdict | Basis | Entry / SL / TP1 | R:R | Controlling precedent |
|---|---|---|---|---|---|---|---|
| [[GBPUSD]] (🟢 Bull) | 4H | Tflow LBull @Zone | ✅ Take (medium) | Binni | 1.34012 / 1.33551 / 1.34903 | 1:1.93 | [AHH Access Time 2026-10-27 · USDJPY](<link>) |
| [[XAUUSD]] (🔴 Bear) | 1H | LBear | ⛔ Skip (high) | Own analysis | … | … | — |
(`<link>` = the case's `note` path made relative to the report dir, written as an angle-bracket destination so the space in the folder name renders in both Obsidian and the dashboard's marked: `[AHH Access Time 2026-10-27 · USDJPY](<../../../AHH Session Notes/2026-10-27-ahh-access-time.md>)`; TAR cases → `<../../../sources/…>`.)

### Opinions — [10:21 SGT]
#### GBPUSD 4H Tflow LBull — Take
- **Reason**: … **Followed**: <case id · presenter · quote · hindsight> **Distinguished**: … **Doctrine**: R07, R12 **Dissent**: …
- ![GBPUSD 4H Chart Screenshot](../../../images/261103-101502_gbpusd_4h_chart.png)   (only when chart_image)

### Pre-filter — [10:21 SGT]
<details><summary>6 alerts filtered</summary>

| Instrument | TF | Signal | Code | Detail |
</details>

### Resolved Since Last Run — [10:21 SGT]
| Instrument | TF | Verdict | Basis | Outcome | R | MFE R |      (every tracked entry resolved with `outcome.reported` false, whoever resolved it — this apply's tracker or a standalone `track`; apply then sets `reported` true. "None." when empty)

### Questions for Binni — [10:21 SGT]                 (only when any no_ruling)

### 30-Day Scorecard — [10:21 SGT]
| Group | Resolved | TP1 % | Avg R | Avg MFE R | No fill |
```
- Pre-filter list (`filtered`, and the report's "N alerts filtered" block): every entry recorded this run with a non-PASS code (`STALE`, `CLOSED`, `NO_DATA`, `NO_STOP`, `RR_LT_1`); retryable ones marked "will retry".
- Verdicts table: every `survivors` + `capped` entry (`unjudged_cap` → ⚠️ Unjudged "cap"; `unjudged_error` → ⚠️ Unjudged with the error). Basis cell: `Binni` (precedent; `Pauline` if every controlling case has presenter pauline) or `Own analysis`; blank for unjudged. Controlling precedent cell: every controlling case (≤ 3) as a link, joined by `; `; link text = `SESSION_LABEL[session_type]` (`ahh-access-time` AHH Access Time, `ahh-session` AHH Session, `taw-pro` TAW Pro, `weekly-review` Weekly Review, `3tt` 3TT, `tar-session` TAR Session) + ` <date> · <instrument>`; `—` when none. Untracked rows add "(untracked)" after the R:R.
- Opinions: one `####` block per judged survivor (take / wait_retest / skip / no_ruling) in verdict-table order; one plain line per `unjudged_error` naming the error; capped entries get no block.
- Questions for Binni: one bullet per `no_ruling`: `- [[SYM]] (🟢 Bull) TF Signal — <question_for_binni>`.
- Icons: ✅ Take · ⏳ Wait for retest @ <level> · ⛔ Skip · ❔ No ruling · ⚠️ Unjudged.
- Per-instrument direction rule in instrument cells; no `[[...]]`, brackets or backticks in headings or image alt text except the `[HH:MM SGT]` timestamp.
- Zero survivors → summary, Resolved, Scorecard only. A failed tab, Tflow-skipped or skipped chart pass adds a ⚠️ line under the summary.

**Scorecard** (`signal_judge_stats.scorecard(entries, since) -> {"window_days", "rows": {group: {"resolved", "tp1_pct", "avg_r", "avg_mfe_r", "no_fill"}}}`):
- Entries: tracked entries with `alert_time ≥ since`.
- Groups: `take (precedent)`, `take (own)`, `wait_retest (precedent)`, `wait_retest (own)`, `skip (precedent)`, `skip (own)`, `no_ruling`, `unjudged` (cap + error), `filtered` (`RR_LT_1`). Report and dashboard show the rows with ≥ 1 entry. Excluded from every group: entries still `pending`, and every untracked outcome (`STALE`, `NO_DATA`, `CLOSED`, `NO_STOP`, untracked class) — they have outcome `UNTRACKED`/`NO_DATA`.
- `resolved` = status ∈ {`TP1_HIT`, `SL_HIT`, `EXPIRED`, `OPEN_RUN_EXPIRED`}; `TP1 %` = TP1_HIT / resolved × 100 (rounded int); `Avg R`, `Avg MFE R` = means over resolved (2 dp); empty → "—"; `no_fill` = count of `NO_FILL`, excluded from resolved. `OPEN`, `NO_DATA`, `UNTRACKED` excluded.

**Weekly index**: `scan_reports_for_date()` adds `{"category": "Signal Judge", "title": "Signal Judge (<first> initial, latest <last>)", "rel_path", "summary"}` when the file exists, where `<first>` / `<last>` are the `HH:MM` of the first and last `## 🕒 Signal Judge Run — [HH:MM SGT]` headings; `extract_report_summary(fpath, "signal_judge")` returns `("<last HH:MM> SGT", summary)` with summary = the day's `**Run summary:**` lines summed into `N judged · take X · wait Y · skip Z · no ruling W` (same tuple shape as the other branches).

### 9. Dashboard

`GET /api/judge?since=YYYY-MM-DD[&until=YYYY-MM-DD]` (defaults since = today − 6, until = today, SGT) → `W.signal_judge(since, until)`. Ledger dir `wiki/notes/signal-judge/` or env `SIGNAL_JUDGE_DATA_DIR` (same variable as the script); report dir likewise with `SIGNAL_JUDGE_REPORT_DIR`. Invalid date params → 400 `{"error": "bad date"}`. The parsed shards are cached in memory keyed on each shard's (path, mtime) and re-read only when one changes, so the dashboard's auto-refresh costs a `stat` per shard.

```json
{
  "status": {"ledger": true, "mtime": "2026-11-03T10:21:52+08:00", "error": null, "truncated": null},
  "entries": [{"key", "match", "symbol", "tf", "direction", "signal", "alert_time", "prefilter", "verdict", "basis",
               "retest_level", "entry", "sl", "tp1", "rr", "tracked", "outcome", "r", "mfe_r", "reason"}],
  "reports": {"2026-11-03": "reports/tat_analysis/signal_judge/2026-11-03-signal-judge.md"},
  "stats": {"window_days": 30, "rows": {"take (precedent)": {"resolved": 12, "tp1_pct": 58, "avg_r": 0.41, "avg_mfe_r": 1.3, "no_fill": 0}}}
}
```
- `entries`: entries any of whose `row_times` dates (else the `alert_time` date) fall in [since, until], newest first, max 5000; beyond that `status.truncated` = total. Shards read: every month from the month before `since` to the month of `until` (an alert near a month start can sit in the previous month's bar-close shard). `status.mtime` = the newest mtime among the shards read.
- `match` = list of `<_norm_sym(row Symbol, src)[0]>|<1H|4H>|<bull|bear>|<_norm_date(Date)>|<_norm_time(Time)[:5]>`, one per `row_times` entry, built with the dashboard's own `_norm_date` / `_norm_time` on the raw sheet strings (`wiki_data.py:1073`), so it is exactly what the Signals rows carry in `r.date` / `r.time`. `_norm_time` is extended to convert `h:mm[:ss] AM/PM` to 24-hour `HH:MM:SS` (it only zero-pads today), so AM and PM rows can't collide. Exact per sheet row, so delayed, re-keyed, :01 and :15 alerts match.
- Field mapping: `entry` = `outcome.entry` or `entry_ref.price`; `outcome` = `outcome.status`; `basis` = `judge.basis` or null; `reason` = `judge.reason` (judged), `judge.error` or "cap" (unjudged), `prefilter_detail` (pre-filter results).
- `reports`: wiki-relative paths (what `/api/doc` and `openDoc` expect, `server.py:88`).
- `stats`: `scorecard(...)` over 30 days.
- No shard → `{"status": {"ledger": false, ...}, "entries": [], "reports": {}, "stats": {}}`; unreadable → `status.error`. Read-only.

UI (`viewSignals`, `dashboard/static/app.js:481`):
- Range → query: today/3d/7d/30d → `since` = range start; `all` → today − 89; `custom` → `since=until=f.day`. The `/api/judge` fetch runs alongside the existing signals data and is awaited after the `if (!rows.length) … return;` early exit (`app.js:513`): with no sheet rows, the tab shows its existing empty state and no judge card. Fetch failure (404 before the LaunchAgent restart, 500, network) → the card body shows "Signal Judge unavailable (<status or error>)" and the Judge column stays blank; the rest of the tab renders. The client keeps the last `/api/judge` response in `S.judge` keyed by `since|until` and re-fetches only when the range changes or on the tab's existing auto-refresh; filter and search changes re-render from the cache.
- **Signal Judge** card between "Multi-timeframe alignment" and "All signals": header = 30-day scorecard rows on one line each (`take · Binni`, `take · own`, …: resolved · TP1 % · avg R) + "Open report ↗" (`openDoc(path, 'Signal Judge ' + date)`) for the newest date in `reports`; body = entries with a verdict other than null/`pending`, filtered by the Source filter (1H/4H) and the search box (`matches(q, sym, signal, reason)`); columns Time · Instrument (`symChip`) · TF · Signal (`sigSpan`) · Verdict badge (+ retest level) · Basis (`Binni` / `Own`) · Entry/SL/TP1 · R:R · Outcome (status + R, or "untracked") · Reason (one line, full text in `title`); 50 rows then "Show more" (+100). Empty: "No judged signals in this range" / "Signal Judge ledger not found".
- **Judge** column in All signals: key `${r.sym}|${r.src}|${r.dir}|${r.date}|${r.time.slice(0,5)}` looked up in a map built from every entry's `match` list → verdict badge ("own" suffix for own analysis), else the prefilter code muted, else blank. (FX 1H and non-FX 4H rows stay blank: not judged.)
- Narrow (< 820 px): both tables in `.tbl-wrap`; scorecard lines wrap.

## Judge protocol (goes into `reference/judge-protocol.md` verbatim)

The slot session (or a manual Claude Code session) judges **inline**: it reads the files and writes the verdicts itself. It does not spawn a subagent, because an unattended `claude` run cannot wait on a background subagent's notification (it would end the turn "successfully" mid-task).

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

### Doctrine checklist acceptance

`reference/doctrine-checklist.md` is acceptable when:
- ≥ 15 rules with ids `R01…`, each one line ending with a citation to a concept-page claim (`wiki/concepts/<page>.md`, claim number or section) or a session note;
- it covers: signal tiers and Tflow / `@Zone` strength; retest rules per timeframe, including the retest-execution claim 16 vs 2/6/17 conflict stated as a scoped pair; HTF permission (4H trend for 1H signals, Daily for 4H); structure / break of structure; room to target and R:R; the elbow stop; Wash & Rinse wash-line confirmation (marked "not machine-checked in v1"); D-Zones as take-profit/stop references; Red Folder news; Friday / late-week entries; the 1H-for-metals/oil/indices and 4H-for-forex timeframe choice (user decision 2026-11-03);
- sources: `wiki/concepts/{tat,tflow,wash-and-rinse,d-zones,market-structure,retest-execution,trading-confluence}.md` and the session notes; ids never reused.
- **citations resolve**: a fixture parses every `claim N` / section citation and asserts the cited page exists and has a numbered claim N (or that heading) under `## Key claims`; and the author spot-reads 5 rules against their claims before the checklist is used.

## UX flow

Unattended slot (after the user applies the Orca change), inside each "TAT Combined 1H+4H Review" run:
1. 1H leg + its new-alert screenshots; 4H leg + its new-alert screenshots (unchanged).
2. **Signal Judge**: `python3 scripts/signal_judge.py run` (foreground, Bash timeout 600000 ms) → `PACKET <path> SURVIVORS <n>` (or `SKIPPED weekend`, exit 10).
3. If exit 0 and `SURVIVORS` > 0: the session follows `reference/judge-protocol.md` inline with the packet's brief, checklist and verdicts paths and run id.
4. If exit 0: `python3 scripts/signal_judge.py apply --packet <path>` (foreground, timeout 600000 ms), with or without survivors.
5. My-Watchlist 4H sweep, then the 4H currency-strength scan (unchanged, now after the judge).

Manual (Claude Code: "run the signal judge"): steps 2–4. On the MacBook: `run --dry-run --out <scratch>` and stop, or set both `SIGNAL_JUDGE_DATA_DIR` and `SIGNAL_JUDGE_REPORT_DIR` to scratch paths for the full loop.

Mac mini setup: `scripts/signal_judge_config.json` already holds `{"writer_host": "pepper"}` (Phase 1).

## Timing

- Inside all 5 Combined runs (07:01 / 10:01 / 14:01 / 18:01 / 22:01 SGT; 06:01 / 09:01 / 13:01 / 17:01 / 21:01 in US daylight saving), right after the 4H leg. Not on weekends (`run` skip window, exit 10). No new schedule.
- Each slot follows a forex 4H close by 1 minute (06:00 / 10:00 / 14:00 / 18:00 / 22:00 SGT; the 07:01 slot follows the 06:00 close by 61 min), so the newest FX 4H bar is closed. The judge step itself starts ~15–25 min into the slot (after both TAT legs and their screenshots), and every freshness rule uses that `run_start`. Overnight (22:01 → 07:01): with `run_start` ≈ 07:20, 1H alerts closing at or before ≈ 01:20 SGT are > 6 market hours old and become `STALE` (in practice the 23:00, 00:00 and 01:00 closes, and metals' 01:01), recorded and counted, not judged.
- **Late or failed slots**: Orca can start a catch-up run hours late (one 2026-10 run started ~8.8 h after its schedule) and can drop a run (the 2026-11-03 07:01 run ended `dispatch_failed`: "Orca stopped watching this run before it reported completion"; the 20 runs before it completed). The judge accepts any start time: freshness is measured from `run_start`, the command lock serialises overlapping commands, and the TradingView lock covers the chart pass. A session killed mid-run leaves `pending` entries that the next `run` ages to `unjudged_error`, and the SIGTERM handler stops TradingView if it owns the lock.
- Contention: the 07:01 run may meet the Daily Signals run (06:45, ~45 charts) still holding TradingView; the 18:01 run may meet Equity News — Asian (17:30 Mon–Sat). The slot's own TAT legs already queue behind those; by the judge step the lock is normally free. If not, the judge waits ≤ 120 s, then skips its chart pass (retryable) and the next slot picks the alerts up (4H FX stays fresh 12 market hours; 1H non-FX 6).
- Runtime: `run` typically 3–6 min (sheet ~20 s, session start 30–60 s, pass ~8–12 s × ≤ 24 symbols, Yahoo ~10–30 s, stop ~15 s), hard cap 480 s; inline judging ~2–4 min; `apply` ≤ ~3 min. The watchlist sweep starts ~6–11 min later than today. The Monday 07:01 run is the likeliest to hit the cap: market hours exclude the weekend, so Friday-evening alerts are still fresh (an FX 4H bar closing Saturday 06:00 SGT is ~1 market hour old at Monday 07:01) and queue up with Monday's first bars; unreached alerts stay retryable for 10:01.
- 18:01 slot: the 18:00 forex 4H close lands in it; the Asian equity scan at 17:30 finishes before or queues ahead of the slot's own TAT legs.

## Data contract

Reads: H1 and 4H tabs (+ Tflow extract via `fetch_with_service_account`); TradingView via `tv_judge_pass.mjs`; Yahoo chart API (1H); `~/tradingview-mcp/daily_brief/<date>.json` (written by `build_daily_bias.py` in the 06:01 Daily Brief); `wiki/notes/economic-calendar.md` (`pull_economic_calendar.py` / `refresh_actuals.py`); `wiki/notes/signal-judge/cases.jsonl` (Phase 1); `wiki/images/*_chart.png` (the slot's new-alert captures); `doctrine-checklist.md`.

Writes:

| Output | Format | Writer | Consumers |
|---|---|---|---|
| `wiki/notes/signal-judge/ledger-YYYY-MM.json` | JSON, monthly shards, merge-by-key | `signal_judge.py` on the writer host | `signal_judge.py`, `signal_judge_stats.py`, `dashboard/wiki_data.py signal_judge()` |
| `wiki/notes/signal-judge/judge.lock` | empty lock file | same | same |
| `scripts/signal_judge_runs/<run_id>_packet.json`, `_brief.md`, `_verdicts.json` | JSON / MD | `run`, the judging session | the judge, `apply`; pruned after 90 days |
| `$TMPDIR/sj_pass_<pid>_{req,out}.json` | JSON | `run` / `tv_judge_pass.mjs` | `run`; deleted after the pass |
| `wiki/reports/tat_analysis/signal_judge/YYYY-MM-DD-signal-judge.md` | Markdown, same-day append | `apply` | user, `update_weekly_index.py`, dashboard (`openDoc`) |
| `wiki/log.md` | `append_log.py` (`report`, `error`) | writer host | user |
| `wiki/index.md` weekly section | `update_weekly_index.py` | writer host | user |

Not touched: the TAT alert report, `scripts/h4_signal_watches.json`, existing dashboard parsers, `binni_alert_analysis.py`, `wiki/index.md` category sections, `wiki/hot.md` (the slot's own bookkeeping rewrites it; the judge adds nothing to it), `cases.jsonl` (read only).

**Sync**: `fcntl` locks are local; safety comes from the single writer (the Mac mini). The sync test (`wiki/notes/signal-judge/sync-test.jsonl`) is still unconfirmed on the MacBook; if JSON files don't sync, the MacBook dashboard shows "ledger not found" and nothing else changes.

## TradingView session use

One batch per `run`: `tv_session.sh start` (lock wait ≤ 120 s, fail-on-timeout, owner token, own process group) → one `tv_judge_pass.mjs` over ≤ 24 symbols × 2 TFs → owner-checked `tv_session.sh stop` in `finally` and the signal handler, whenever start was invoked and did not exit 75. TAW layout enforced by `tv_session.sh start` and again by the pass. No screenshots (line-chart and image-naming rules don't apply). It sits after the 4H leg's screenshot batch has stopped and before the watchlist sweep starts.

## Unattended behaviour

- No prompts; no retry loops inside a run; retryable alerts are picked up by later runs (≤ 3 attempts).
- The scripts log their own failures on the writer host (§5). The Orca prompt does not log again.
- On a non-zero `run`: exit 10 → skip silently; exit 6 → message into the slot's final summary; anything else → skip the judge and `apply`, continue with the next step.
- `run` ≤ 480 s with per-call timeouts (+ ≤ 60 s stop, inside the 600 s Bash timeout); Node and the start are killed by process group; SIGTERM still stops TradingView if this run owns the lock. `apply` is bounded by its tracker budget.
- If judging or `apply` never happens, the next `run` ages `pending` entries to `unjudged_error`.
- Inline judging needs only Read and Write in the repo, which the slot session already uses for reports; no subagent, so no subagent permission check.

## Docs to update

- **AGENTS.md**: new Workflow note **Signal Judge Rule** (runs after the 4H leg in all 5 Combined runs, not weekends; judged pairs FX 4H / metals-oil-indices 1H; own-analysis label; writer host; outputs; advisory only; the step lives in the Orca prompt); in the **Signal Case Store Rule**, "the live judge, Phase 2, is … not built yet" → built, and "is the go/no-go for Phase 2 (recommend go at ≥ 60%)" → "passed at 83.6% (2026-11-02); `coverage --judged-only` now tracks the Phase 2 scope"; **My-Watchlist 4H Screenshot Rule** "Immediately after the 4H leg…" → "after the 4H leg and the Signal Judge step…"; **4H Currency Strength Scan Rule** unchanged (it already follows the sweep); Categories: `wiki/reports/tat_analysis/signal_judge/`; Lint exceptions: unchanged (there is no `lint_wiki.py` in `scripts/`; the existing `wiki/notes/signal-judge/*.json`, `*.jsonl` line already documents the data files, and `judge.lock` is not a page); Tooling: the "Scripts in `scripts/`" list gains `signal_judge.py`, `signal_judge_stats.py`, `tv_judge_pass.mjs`, `signal_cases.py`; the **TAT Alert Analysis Skill** bullet notes `validate_h4_signals.py` is now a helper library for the Signal Judge and its own CLI (`h4-signal-validation`, MacBook-only skill) is superseded; `tv_session.sh`'s three opt-in env vars noted under the Batch TradingView Session Rule.
- `dashboard/README.md`: the Signals tab section gains the Signal Judge card, Judge column and `/api/judge` (reads `wiki/notes/signal-judge/ledger-*.json`).
- `.agents/skills/signal-judge/SKILL.md`: frontmatter `description` (drop "(planned)", mention the live judge) and the body's "Phase 2 … is not built yet" line; Phase 2 sections (Run / Judge / Apply / Track / Stats, verdict semantics, judged pairs, the Orca snippet, failure handling); new `reference/judge-protocol.md` and `reference/doctrine-checklist.md`.
- `.agents/skills/tat-alert-analysis/SKILL.md`: §2's slot times corrected to the standard-time ones (07:01/10:01/14:01/18:01/22:01, daylight saving in brackets); §4: new rule "Signal Judge step"; its My-Watchlist rule's "Immediately after that 4H leg completes" → "after the 4H leg and the Signal Judge step complete".
- AGENTS.md **Unattended Scheduling** bullet and the **Seasonal Schedule Rule** table: note that the Combined slot now runs ~6–11 min longer (judge step before the watchlist sweep). `CLAUDE.md` is a symlink to `AGENTS.md`, so one edit covers both.
- The disabled "TAT Combined 1H+4H Review — 06:15 AM Slot" automation (`fba46300…`, parked at 07:15) embeds the old step order: noted in the skill; the user applies the same prompt change only if it is ever re-enabled.
- `docs/design/signal-cases-phase1.md`: one line under Out-of-scope: "Phase 2 built, see signal-judge.md" plus the oil class and shared-loader changes.

**Orca prompt change** (automation `38849272`; the user applies it). Insert right after the sentence ending "…in two sequential batches (1H symbols first, then 4H symbols - tv_session.sh start, capture_tv_chart.sh per symbol, tv_session.sh stop, once per batch)." and before "After the 4H leg completes and its new-alert screenshots are captured, run the My-Watchlist 4H Screenshot Protocol":
> Then run the Signal Judge step per `.agents/skills/signal-judge/SKILL.md` §Run: (1) `python3 scripts/signal_judge.py run` as one foreground Bash call (timeout 600000 ms). Exit 10 (weekend): skip the rest of this step silently. Exit 6: put its message in your final summary and skip the rest. Any other non-zero exit: skip the rest. (2) If it exited 0 and printed SURVIVORS greater than 0, judge them yourself, inline, following `.agents/skills/signal-judge/reference/judge-protocol.md` with the packet's brief, checklist and verdicts paths (do not spawn a subagent). (3) If it exited 0, run `python3 scripts/signal_judge.py apply --packet <path>` (foreground, timeout 600000 ms). The scripts log their own errors.

and change "After the 4H leg completes and its new-alert screenshots are captured, run the My-Watchlist 4H Screenshot Protocol" to "After the Signal Judge step, run the My-Watchlist 4H Screenshot Protocol". Also: when the user applies it, `orca automations show` must show the new text (verification 9).

## Failure modes

| Breakage | What the user sees |
|---|---|
| One sheet tab fails | Run section with a ⚠️ line; the other tab is judged |
| Both tabs fail / gspread missing | No run section; `wiki/log.md` error; exit 3 |
| Tflow sheet unreadable (after one retry) | ⚠️ "Tflow sheet unreadable: <tab> alerts held for the next run"; that tab's alerts retryable `NO_DATA` "Tflow data unavailable", nothing judged from it; error logged |
| Lock busy > 120 s / start fails / budget short | ⚠️ "chart pass skipped"; candidates retryable `NO_DATA`; the other job untouched (owner token) |
| Pass overruns / symbol cap | Unreached symbols retryable `NO_DATA` |
| Wrong symbol / timeframe served | Read discarded after one `setTimeframe` retry, retryable |
| Market closed (daily break, holiday) | `CLOSED`, retried next run, not counted |
| Weekend run | exit 10, nothing judged |
| Delayed alert batch | Matched to the bar that closed before it, re-keyed if needed; `delayed_alert_min` shown |
| Yahoo down | Tracked metals/oil/indices `NO_DATA` (retryable); FX unaffected at `run`; tracker leaves entries OPEN |
| Judge never runs / invalid JSON / misses a survivor | ⚠️ "judge unavailable" or "no verdict returned"; entries `unjudged_error`, still tracked |
| One invalid verdict (e.g. own_analysis with a controlling case) | ⚠️ Unjudged with the validation error |
| No precedents | Judge does own analysis, labelled; scored separately |
| Ledger shard corrupt | exit 5 without writing; dashboard shows the read error |
| Not the writer host | exit 6; slot summary shows it |
| Futures roll mid-trade | Basis off by the roll gap for that entry; accepted for v1, noted in the skill |

## Verification criteria

1. **Fixture checks** `scratch/check_signal_judge.py` (plain `python3`, no network, no TV; stubs for `fetch_with_service_account`, `yahoo_bars`, the TV session command and the Node pass), each an assert:
   - **Class/TF filter**: EURUSD 4H → candidate; EURUSD 1H → `out_of_tf`; XAUUSD 1H, USOUSD 1H, NDQ100 1H, GER40 1H → candidates (GER40 untracked); XAUUSD 4H → `out_of_tf`; BTCUSD, XCUUSD, UKOUSD → `out_of_scope`.
   - **Nominal close / keys**: 4H EURUSD alert 2026-11-03 06:00:04 → bar close 06:00 (standard time) and 2026-10-28 05:00:03 → 05:00 (daylight saving); 1H 15:00:04, 14:59:58 and 15:16 → 15:00; GER40 1H 10:15:03 → 10:15. Delayed rows: a group with rows at 15:00:04, 15:16:20 and 15:27:10 → one parent (15:00:04) and one `#d` group holding both later rows. Stub 1H bars 13:00–14:00 (close 1.0990), 14:00–15:00 (close 1.1010), with level P = 1.1000 for a bull alert: the `#d` group's cross rule picks the 14:00–15:00 bar (previous close 1.0990 ≤ P < 1.1010) — the parent's bar in the same run → `duplicate_delayed`; the same stub with the parent already stored by an earlier run → re-keyed onto that key → `already_seen`; with P crossed only by the 13:00–14:00 bar → re-keyed to …T14:00 with `rekeyed_from`; a `#d` group whose symbol wasn't read → `NO_DATA` under its `#d` key.
   - **Grid offsets**: XAUUSD 1H alert 10:01:05 → nominal 10:01, matched to a stub bar 09:01–10:01, not re-keyed; HK50 11:15:02 → 11:15.
   - **Signal Price kind**: a group with `Tflow LBull` (price 1.8668) + `LBull` (1.87606) → `signal_price` 1.87606, kind `level`; a Tflow-only group → kind `tflow`, delayed copy matched by time only.
   - **Pre-pass skip of re-keyed alerts**: an alert re-keyed in run 1 (ledger `key` ≠ `prepass_key`) is dropped as `already_seen` in run 2 before the chart pass (the stub pass is not called for it).
   - **`#d` replacement**: a `#d` entry stored as `NO_DATA` in run 1 and re-keyed in run 2 → exactly one ledger entry, under the new key, attempts 2.
   - **Apply idempotence / dirs**: a second `apply` on the same packet → "already applied", exit 0, report and log unchanged; a packet whose `data_dir` differs from the current env → exit 2; test dirs set without `SIGNAL_JUDGE_RUNS_DIR` → exit 6.
   - **Late-row merge**: a late Tflow `@Zone` row merged into a stored `unjudged_cap` entry upgrades its signal and `at_zone`; merged into a judged entry it only adds `row_times`.
   - **Retry end**: an entry at its third attempt failing again → `retryable: false`, outcome `UNTRACKED`.
   - **Weekend gap / retest snap / no_ruling basis**: a Saturday-06:00 FX bar judged Monday → `weekend_gap`; a retest 0.05 ATR beyond SL → snapped with a warning; 0.3 ATR beyond → `unjudged_error`; a no_ruling with a controlling case → basis precedent, without → own_analysis.
   - **First-TF stale labels**: stub labels identical to the previous symbol's → re-read, then `NO_DATA` "labels not refreshed"; median level 15 % from the quote → same.
   - **Label refresh**: stub pass output where the second TF's fingerprint equals the first's after the re-read → that read discarded `NO_DATA` "labels not refreshed".
   - **Attempts**: lock busy three runs in a row → `attempts` stays 0 and the alert is retried until STALE; a read that fails validation → `attempts` +1.
   - **Command lock**: a second `apply` while the first holds `judge.lock` waits, then exits 4 after the (shortened, fixture) timeout.
   - **Month boundary**: an entry stored under `#d` in `ledger-2026-11.json` re-keyed to a bar closing 2026-10-31 → removed from the November shard, present in the October shard; a simulated crash between the two writes → the duplicate collapsed on the next load.
   - **Stop timeout**: a stub stop that sleeps past its timeout → pkill called, lock removed only when owned, `error` logged.
   - **Daily brief**: a non-date file ignored; today's brief with mtime after `run_start` skipped; a corrupt newest file → the previous day's used.
   - **Fatal pass**: stub `out.json` with `fatal` → `chart_pass.ok` false, `skipped_reason` "pass failed", all candidates retryable `NO_DATA`.
   - **Helpers**: `market_cutoff(Mon 2026-11-09 07:01 SGT, 12)` = Fri 2026-11-06 19:01 SGT (1 h 01 m back to the Mon 06:00 SGT reopen, then 10 h 59 m before the Sat 06:00 SGT close); `daily_brief_entry` picks the newest file ≤ run date and reports `age_days` 5 for a 5-day-old file (tag falls back to `unspecified`).
   - **Delayed matching**: a 1H alert 2 h late whose level P was crossed by the bar two bars back → matched to that bar, `matched_by: "cross"`, `delayed_alert_min` ≈ 120; no crossing bar → latest by time, `"time_fallback"`; an on-time alert whose nominal bar is missing from the stub → `"time_fallback"`.
   - **Signal bar**: a 1H index series with a short session-end bar (16:00–17:00 NY) as the last bar → the alert at its close maps to it; a Sunday-open 1H bar maps; no bar → `NO_DATA` retryable once.
   - **Read validation**: a `D` request answered `1D` → accepted; TAT `total_labels` 612 → `labels_capped`; an FX read with the Yahoo stub failing → quote check skipped, not `NO_DATA`; an XAUUSD read with Yahoo failing → `NO_DATA` "no Yahoo price"; `60` answered for `240` → discarded "timeframe not confirmed" (with `retried_tf` true in the stub output); 240 with 1-hour spacing → "bar spacing mismatch".
   - **Market open**: an XAUUSD read at Tuesday 17:20 New York → `CLOSED`, attempts unchanged; a GBPUSD read at that time → not closed by the break rule.
   - **Basis**: Yahoo 1H closes and TV `60` closes sharing bar 09:00 → basis = their difference; no common closed bar in the last 6 → `NO_DATA` "no Yahoo price".
   - **Market hours / STALE**: run Monday 2026-11-09 07:01 SGT; FX 4H alert closing Saturday 2026-11-07 06:00 SGT (Friday 17:00 NY) → 1.02 market hours → candidate; XAUUSD 1H alert closing Friday 2026-11-06 23:00 SGT → 8.02 → `STALE`; FX 4H closing Friday 14:00 SGT → 17.02 → outside the window. Run Saturday 10:00 SGT → exit 10 "weekend". Run Tuesday 18:01 SGT → not skipped.
   - **Dedupe**: US30 1H `OptBear` 2:00:06 + `LBear` 2:00:04 → one (OptBear, also_fired [LBear]); XAUUSD 1H `Tflow SBull` + `SBull` same bar → one (`Tflow SBull`).
   - **Rank**: two Tflow LBull @Zone survivors R:R 1.5 and 3.0 + plain OptBull R:R 5 → @Zone 3.0, @Zone 1.5, OptBull; with a 2-slot cap OptBull is `unjudged_cap` in `capped`.
   - **Tag mapping**: two hand-built feature dicts → exact tag sets incl. location exclusivity and ATR-null; index → `cross_pair.score` null; missing TAT study → `htf.bias` null, daily-brief fallback; `friday` true for a bar closing Saturday 02:00 SGT, false for Friday 13:00 SGT.
   - **Shared loader**: Phase 1 `coverage` on a fixture sheet keys alerts with `nominal_close` (same keys as Phase 2); `run_coverage` reports an `oil` class row.
   - **Oil in Phase 1**: `instrument_class("USOUSD") == "oil"`, `canon_instrument("USOIL") == "USOUSD"`, `yahoo_ticker("USOUSD") == "CL=F"`; a stored `commodity` WTI case scores the class point against a USOUSD signal; `check_signal_cases.py` still passes.
   - **Verdict validation**: wrong enum, retest beyond SL, unknown case id, unknown R-id, no_ruling without question, `|` in reason, missing verdict, `own_analysis` with a controlling case, `own_analysis` with one R-id, `precedent` with no controlling case → each `unjudged_error`; a valid precedent verdict and a valid own-analysis verdict pass.
   - **Tracker** on synthetic Yahoo 1H bars: TP1 first; SL first; same bar SL+TP → SL; EXPIRED R sign for a short; OPEN_RUN_EXPIRED; wait_retest fill then TP on the fill bar; NO_FILL `mfe_r` in units of `|retest − sl|`; basis subtraction; pre-entry bars ignored; 10-day NO_DATA; untracked never walked; 1H-signal window 24 bars vs 4H-signal window 120.
   - **Scorecard**: fixture with take (precedent) and take (own) entries across TP1_HIT, SL_HIT, EXPIRED, OPEN_RUN_EXPIRED, NO_FILL, OPEN, NO_DATA → exact per-group resolved / TP1 % / Avg R / no_fill, with precedent and own rows separate.
   - **Run control**: stub start exiting 75 → `chart_pass.ok=false`, stop never called, exit 0; start exiting 1 and one timing out → start group killed, stop called with the token; stub stop with a non-matching token (or no lock dir) leaves the stub "TradingView" running; stub pass past its deadline → Node group killed, unreached symbols retryable; `remaining() < 300` → pass skipped; both sheet stubs raising → exit 3; a stub tab whose Tflow supplement is skipped twice → `tflow_unavailable`, its alerts retryable `NO_DATA` "Tflow data unavailable" with attempts unchanged, nothing from it judged; skipped once then fetched → judged normally; held ledger lock → exit 4; corrupt shard → exit 5, file unchanged; non-writer → exit 6; one env dir only → exit 6; `run` stdout exactly one line; a second run in the same minute → `_2` run id; a stub raising inside feature building → traceback on stderr, one `error` log call, cleanup ran, exit 1; `apply` on a packet with `"dry_run": true` → exit 2, report dir untouched; the prune deletes an old `_packet.json` but keeps an old `cases_x.json` and `x.rejects.json`; `--symbol EURUSD` → only EURUSD groups in `counts`.
   - **Retry**: a retryable `NO_DATA` entry (attempts 1, fresh) → candidate next run, rebuilt from the current sheet row, updated in place (attempts 2), outcome reset to OPEN on PASS; with its rows gone from the stub sheet → rebuilt from stored fields; after 3 attempts or once stale → not retried.
   - **Brief**: 8 survivors × 8 precedents → S1..S8, no line > 400 chars, < 300 lines; a survivor with no precedents shows the "None — own analysis required" line.
   - **Counts**: the fixture run's counts satisfy every identity in §6 Counts.
   - **Resolved table**: an entry resolved by a standalone `track` before `apply` appears in that apply's Resolved table once, and not in the next one.
   - **Ledger**: `pending_since` older than 2 h → `unjudged_error` next run; a verdict for an aged entry ignored with a warning; entries land in their bar-close month shard.
2. **`tv_session.sh` regression**: with none of the three env vars set, `bash -n` passes and a diff review shows start/stop paths unchanged; with `TV_LOCK_OWNER=x` and a lock dir whose `info` lacks `owner=x` (and with no lock dir), `stop` prints "not the lock owner" and does not call `osascript`/`pkill`; with `TV_LOCK_OWNER=x` and a stub `node` whose `layout switch` fails, `start` calls the quit sequence before releasing the lock and exits 1. All against a stub PATH (`osascript`, `pkill`, `pgrep`, `open`, `node` echo their arguments to a log) and a temp `LOCK_DIR` (new env override `TV_LOCK_DIR`, tests only).
3. **Coverage for the Phase 2 scope**: `python3 scripts/signal_cases.py coverage --days 14 --judged-only` → report GATE and the share of alerts with no precedent (= expected own-analysis share) to the user. No gate threshold; informational.
4. **Dry run with TradingView** (user OK, outside slots and their current run length: not within 05:25–07:55, 09:55–10:55, 13:55–14:55, 17:25–18:55, 21:55–22:55 SGT or 20:10–20:40 Mon–Fri; check `orca automations runs --id 38849272…` and `pgrep -f TradingView` first): `run --dry-run --ignore-skip-window --out <scratch>`.
   - Packet + brief written; every PASS survivor has levels, SL, TP1 (or OPEN RUN) and a precedents block; `chart_pass.ok` true; no read discarded for TF/spacing.
   - For 3 survivors, compare the packet's signal-bar OHLC, `trigger_level` and `tp1` against `tv ohlcv` and the TAT labels read directly. More than 1 of 3 levels wrong (superseded labels) → report to the user before the full loop; the design then needs a recency filter.
   - For XAUUSD, USOUSD and NDQ100: basis-adjusted Yahoo 1H closes vs TV 1H closes over the last 24 bars, median abs difference < 0.15%; report the numbers.
   - **Cross-rule check**: dry-run packets carry `"diagnostics": {"cross_rule": [{"key", "time_bar_close", "cross_bar_close", "agree": bool}], "cross_agree_pct": float}` built from every on-time plain alert in the window (the cross rule run alongside the time match). Pass: the cross rule picks the same bar for ≥ 90 % of them → `MATCH_DELAYED_BY_CROSS` stays `True`. Below 90 % → set it to `False` (delayed alerts then match by time only), report the rate and the misses to the user, and note it in the skill. Either way list every `#d` / re-keyed alert with its rows.
   - Grid: every symbol's observed `grid_offset_min` equals `GRID_OFFSET_MIN`; any mismatch → update the table before the full loop.
   - Orca runs: `orca automations runs --id 38849272-f13f-452c-93f3-2e3c38291d73` — report the last 20 runs' outcomes and the 2026-11-03 `dispatch_failed` to the user before the Orca change is proposed; the user decides whether to enable the step.
   - Orca run limit: `orca automations edit --help` / `show` checked for a per-run timeout; report the slot's current duration from `orca automations runs` and whether +10–15 min fits; if it doesn't, report to the user, who decides (e.g. drop the judge from the busiest slot).
   - `wiki/notes/signal-judge/`, the report dir and `wiki/log.md` mtimes unchanged; TradingView quit afterwards (no `TradingView` process, lock dir gone).
5. **Full loop into scratch**: both env dirs → scratch; `run --ignore-skip-window` → inline judging in this session per the protocol → `apply` → `track` → `stats`. Check the scratch report (incl. `lint_images.py` on it), ledger entry count = `counts.recorded`, one verdict per survivor, at least one own-analysis verdict if any survivor lacked precedents, one embedded image opened with Read when present, `cases.jsonl` mtime unchanged.
6. **Dashboard**: second instance `SIGNAL_JUDGE_DATA_DIR=<scratch> SIGNAL_JUDGE_REPORT_DIR=<scratch> python3 dashboard/server.py --port 8799`; `curl -s 'http://127.0.0.1:8799/api/judge?since=2026-11-01' | head -c 400`; `curl` with `since=bad` → 400; ego-browser on `http://127.0.0.1:8799/#signals` desktop and < 820 px: card renders with precedent/own scorecard rows, Basis column, Judge-column badges on FX 4H and non-FX 1H rows only, "Open report ↗" requests `/api/doc?path=reports/tat_analysis/signal_judge/<date>-signal-judge.md` (404 expected for a scratch report), empty state with an empty ledger dir, the "Signal Judge unavailable" state with a ledger dir holding a corrupt shard, a GER40 :15 row and a delayed row badged via `match`, clean console. Stop it; restart the LaunchAgent; `/api/judge` returns the "ledger not found" shape until the first real run. Quit ego lite afterwards.
7. **Unattended shape**: from the repo root, `env -i HOME=$HOME PATH="$(dirname "$(command -v python3)"):/usr/bin:/bin" python3 scripts/signal_judge.py run --no-chart --dry-run --ignore-skip-window --out <scratch> </dev/null` exits 0 with one `PACKET … SURVIVORS n` line; with `SIGNAL_JUDGE_CONFIG=<missing path>` and no `--dry-run` it exits 6. (`SIGNAL_JUDGE_CONFIG` env overrides the config path, tests only.)
8. `py_compile` on touched Python, `bash -n scripts/tv_session.sh`, `node --check scripts/tv_judge_pass.mjs dashboard/static/app.js`, `python3 scratch/check_signal_cases.py`.
9. **First real slot** (after the user applies the Orca change): the next weekday slot writes a report section, ledger entries and a `wiki/log.md` `report` line; the watchlist sweep and currency-strength scan still run after it.

## Out-of-scope follow-ups

- Wash-line and D-Zone box prices for all signals (needs an unrounded CDP reader).
- Tracking the untracked class from TradingView bars.
- Running the judge from `journal.py new` / the dashboard Log-trade form.
- Calibration report once ~200 resolved entries exist (precedent vs own, take vs skip vs filtered, similarity vs outcome).
- Marking superseded (pre-v3) cases; weighting "affirmed/reversed" follow-ups in Weekly Reviews.
- Historical economic-calendar source for `news_pending` in hindsight.
- The stale `wiki/sources/` wording in `trading-transcript-ingest`; the dead 05:00 race guard in `scan_daily_signals.py:273`.

## Build notes (2026-11-04, implementation)

Found and fixed while running against live TradingView (Verification 4):
- `chart.setSymbol` can return without switching right after `tv_session.sh start` (the chart stayed on a leftover `BATS:FTXL`). `tv_judge_pass.mjs` now checks `getState().symbol` after the switch and retries once; Python still discards an unconfirmed read.
- The first 1H read after a switch can arrive before the TAT study has calculated (no labels, no trend values). The first full dry run judged those survivors as "open run" with no trigger level. The pass now re-reads up to twice (2 s apart) until the `TATbyBinniOng*` study is present, and `validate_read` treats a signal-timeframe read with no TAT study as retryable `NO_DATA` "TAT study not loaded".
- The pass's own `layoutSwitch` can time out on `getSavedCharts` right after start; `tv_session.sh start` already confirms the layout, so that second switch is now non-fatal.

Verification 4 results (dry run 2026-11-04 00:01 SGT, 9 symbols, 64 s end to end, TradingView quit and lock released, `wiki/` untouched):
- Every read confirmed its symbol and timeframe and carried the TAT study; no grid mismatch (metals observed at :01).
- Signal bars match `tv ohlcv` exactly (NZDUSD 4H, XAUAUD 1H); trigger and TP1 levels are real TAT labels (NZDUSD `MajD 0.56089 FiRet h4` / `TP : 0.56695`; XAUAUD `MinD 5621.54 FiRet h1`).
- Cross rule on on-time alerts: found a crossing bar for 8 of 9 and agreed with the time match on all 8 (the ninth, UK100, had no crossing bar and falls back to time). `MATCH_DELAYED_BY_CROSS` stays on; the dry-run diagnostics now report found % and agree-when-found % separately.
- Basis-adjusted Yahoo vs TradingView 1H closes over 24 bars: XAUUSD median 0.045 % (max 0.118 %), SPX500 0.093 % (0.106 %), JPN225 0.059 % (0.080 %), NZDUSD 0.013 % (0.032 %); Yahoo futures lag ~8 min.

## Revision 11 — binding decisions (override, 2026-11-03)

After round 5 the user chose **"Override and proceed anyway"**: the points below were still open and are settled here by the author. They override anything above that disagrees, and the final report lists them as decisions the user can overturn.

Pipeline and data:
1. `unjudged_cap` is final (tracked, never retried). The late-row merge upgrades `signal` / `tflow` / `at_zone` only on entries still `pending` or retryable; on `unjudged_cap` and judged entries it only appends `row_times` and `also_fired`.
2. `features.atr` (signal-TF Wilder ATR or null) is added, and every survivor carries `atr` at top level, so `apply` can snap a retest level.
3. `run` writes the keys it aged to `unjudged_error` into the packet as `aged_unjudged: [keys]`; `apply` lists them in its ⚠️ line.
4. Alerts held as "Tflow data unavailable" are counted in `chart_candidates` and `no_data` (the identities hold). A `tflow_unavailable` tab's groups still feed `context`.
5. Step 4's Yahoo budget skip: FX → quote check skipped (never `NO_DATA`); metal/oil/index → `NO_DATA` "run budget exceeded".
6. `weekend_gap` is a judge-only flag: it is shown in the brief's risks but **not** passed to `find_precedents` (it is not in the Phase 1 vocabulary).
7. `out.json` per-read record: `{"state", "bars", "tat": {"name", "total_labels", "labels"} | null, "indicators", "quote", "read_at": <epoch ms>, "retried_tf": bool, "relabel_retry": bool, "fingerprint": str}`. Node only compares fingerprints (with the previous item's last read and, on the second TF, with the first TF) and re-reads once after 1500 ms; it marks nothing stale. Python decides: fingerprint still equal after the re-read, or the median TAT level parsed from the labels more than 10 % from `quote.last` → read discarded, `NO_DATA` "labels not refreshed". No regex is ported to JS.
8. `GRID_OFFSET_MIN` lives in `signal_cases.py` next to `nominal_close`; `signal_judge.py` imports it.
9. Hindsight rendering: the label is `hindsight["status"]` (missing or null → `unscored`), the numbers `mfe_atr` / `mae_atr` (shown when not null).
10. A Yahoo 1H bar is closed when `start + 1 h ≤ read_at` (price basis) or `≤ now` (tracker); the forming bar Yahoo returns is ignored.
11. `run --dry-run` without `--out` → argparse error, exit 2.
12. Market open: the Yahoo `regularMarketTime` age **no longer** marks anything `CLOSED` (thin series such as `NIY=F` would hold JPN225 forever). Closed = the TradingView last-bar rule or the New York daily break (non-FX). The Yahoo age is reported as `features.yahoo_lag_min`.
13. Non-FX market hours use the same weekend closure as FX (Sunday 17:00 NY reopen; their real reopen is 18:00 and the daily break is not subtracted): their 6 h / 12 h windows are ~1 h generous. Accepted.
14. FX Yahoo coverage: Verification 4 fetches one 1H series for every FX symbol seen in the window; any `<SYM>=X` with no bars goes into `UNTRACKED_FX` in `signal_cases.py` (judged, outcome `UNTRACKED`), and the list is reported.
15. `load_judged_alerts` counts rows with an unparseable time, empty Signal Type or a Direction other than Bullish/Bearish as `skipped`, exactly as `load_alerts` does (`signal_cases.py:822-824`).
16. Two or more verdicts for one survivor key → all of them rejected, that entry `unjudged_error` "duplicate verdicts".

Report and dashboard:
17. Crash-safe append: every run section starts with `<!-- signal-judge-run:<run_id> -->`; `apply` checks the report for that marker first and, if present, skips the append (then still writes `_applied.json` and continues with log/index only if `_applied.json` was missing).
18. Screenshot reuse matches the timeframe token case-insensitively (`_1h_` / `_1H_`, `_4h_` / `_4H_`), and accepts any capture of that symbol and TF within 45 min before `run_start`, including a My-Watchlist sweep capture (same chart, same TF).
19. Dashboard `/api/judge` cache on the client: `S.judge = {key: since|until, at: ms, data}`, re-fetched when the key changes or `at` is older than 60 s; filter and search changes re-render from it.
20. `/api/judge` with `status.error` set (corrupt shard) → the card shows "Signal Judge unavailable (<error>)", same as a failed fetch. Bad `since`/`until` → `server.py` returns 400 `{"error": "bad date"}`: the GET dispatch gains support for a handler returning `(data, status)` (only `/api/judge` uses it).
21. `_norm_time` is **not** changed: all 1,544 timed rows on both tabs are 24-hour `H:MM:SS` (checked 2026-11-03; 32 H1 rows have an empty Time and are skipped). `match` uses `_norm_time` as it is.

TradingView and docs:
22. `tv_session.sh start` with `TV_LOCK_OWNER` set arms `trap '<quit sequence>; release_tv_lock' EXIT` right after TradingView is launched, so an unguarded `set -e` failure also quits it; the trap is disarmed with `trap - EXIT` immediately before start's successful end. Without the variable nothing changes.
23. The checklist citation fixture matches `## Key claims` case-insensitively (`retest-execution.md` uses `## Key Claims`).
24. `.agents/skills/tat-alert-analysis/SKILL.md`: every slot-time mention is replaced with the standard-time times (daylight saving in brackets), including §2.1, §5, §7 and §8, the "typically the 06:15 run" line and "captures all 16" (→ "every instrument in `my_watchlist.json`").

## Revision log

Revision 11 (2026-11-03) — round 5 (critic 13 gaps, readiness 14 questions) closed by user override; 24 binding decisions added above the revision log.

Revision 10 (2026-11-03) — after round 4 hit the 3-revision cap; user chose "clarify in chat", took the proposed defaults and decided Tflow is never skipped:
- Tflow sheet unreadable → retry once, else that tab's alerts are held (retryable, no attempt) and nothing is judged without Tflow; `fetch_tabs` reports Tflow-skipped per tab; sheet keys `1H`/`4H`.
- `apply` idempotent (`_applied.json`); packets record their dirs and `apply` refuses a mismatch; test dirs require `SIGNAL_JUDGE_RUNS_DIR`.
- First-timeframe stale-label check (previous symbol's fingerprint, level-vs-quote distance); labels only from the `TATbyBinniOng*` study; `force_tv_visible.mjs` exports `forceVisible()`.
- Late rows merged into the surviving entry (row times, also_fired, Tflow upgrade if not yet judged); retry end state; retest level snapped within 0.1 ATR of the stop; `no_ruling` basis rule; `weekend_gap` flag; first partial hour accepted and stated; residual bookkeeping race stated.
- Two cutoffs in `load_judged_alerts`; swing fields are prices; OPEN RUN `room_consumed` null; same-minute heading suffix; `_norm_time` AM/PM; dashboard imports the stats module via its existing repo-root path; checklist citation fixture; dry-run `diagnostics` and thresholds; doc drift adds the Unattended Scheduling / Seasonal lines and the disabled 06:15 automation.

Revision 9 (2026-11-03) — after round 3 (critic 16 gaps, readiness 10 questions):
- Label-refresh check after the timeframe switch; force the page visible per item; stop-timeout fallback (pkill, owned-lock removal, error log).
- `context` alerts (24 h, both tabs, incl. out_of_tf) for `other_tf_alert` / `cross_pair` / `laggard`; retries matched by `prepass_key`; `attempts` rules; one `#d` group per parent; pre/post `already_seen` counts with exact identities; grid derivation and `grid_mismatch`; `filtered` contents; controlling-precedent cell; `read_ok`.
- One command lock (`judge.lock`) for `run` / `apply` / `track` covering ledger, report and bookkeeping; cross-month re-key writes and crash collapse.
- Late / dropped Orca slots stated (today's 07:01 `dispatch_failed`); freshness from the real `run_start`; overnight STALE window corrected; Orca run history reported before enabling.
- Null hindsight shown as "unscored"; `daily_brief_entry` availability rule, non-date files, corrupt JSON fallback; gspread `find_spec` check and our own socket timeout; Phase 1 line refs; `row_times` carry the row's Symbol; leftovers from rev 7 removed; no `lint_wiki.py` edit; build on the working-tree `update_weekly_index.py`; aged `unjudged_error` listed in the report.

Revision 8 (2026-11-03) — after round 2 (critic 15 gaps, readiness 12 questions):
- Signal Price is the broken TAT level (plain row) or a Tflow pattern price, not the bar close: on-time alerts match by time; delayed ones by a level-cross rule (plain price only), else time; `MATCH_DELAYED_BY_CROSS` with a measurable pass criterion in Verification 4; `signal_price_kind`.
- Bar grid measured on TradingView: metals and gold crosses :01, GER40/HK50 :15, oil/NDQ100/JPN225 :00; observed offsets checked each pass; price basis pairs Yahoo :00 bars with TV :01 bars.
- `prepass_key` stored and checked so re-keyed alerts are not chart-read every run; `#d` entries replaced on re-key.
- Loader contract: `load_alerts` keeps Phase 1 semantics; new `load_judged_alerts` (order of filters, counts, Bullish/Bearish mapping, chosen-row `alert_dt`) and `market_cutoff`; `daily_brief_entry` replaces the `brief_bias_lookup` reuse; non-FX 4H keying defined for the replay only.
- Judge protocol: what each precedent verdict (take / wait_retest / conditional / watch / skip / already_moved) means, opposite-direction precedents, `quote_in_raw` and `levels` in the brief.
- Run budget 480 s; stop right after the pass; lock-info race explained; fatal pass errors handled; symbol check against the sheet ticker; label prices rounded too (levels from text), superseded-label limitation checked in the dry run.
- Tracker walk from the fill bar; scorecard exclusions; Opinions and Questions formats; weekly-index title and tuple; dashboard shard range, `status.mtime`, client cache, match built with `_norm_date`/`_norm_time` on raw strings, angle-bracket links; drift adds `dashboard/README.md`, the signal-judge skill frontmatter, the tat-alert-analysis slot times, an Orca run-limit check; verification windows widened; new fixtures.

Revision 7 (2026-11-03) — after round 1 (comprehension passed; critic 21 gaps; readiness 12 questions):
- Bar keys: nominal close = latest grid close at or before alert + 120 s (was floor(alert − 120 s) + 1 h, wrong for late alerts); GER40/HK50 :15 grid; delayed rows split into `#d` groups; the signal bar matched by Signal Price first, then time; re-key / `duplicate_delayed` rules; fixtures rewritten to match.
- One alert loader for both phases: `nominal_close` and an extended `load_alerts(judged_only=True)` in `signal_cases.py`; `fetch_tabs`, `load_calendar`, `brief_bias_lookup` reused; `coverage --judged-only` stated as a lower bound, live hit rate from `stats`; oil added to `run_coverage` classes; USOUSD cases get scored; redundant `similarity()` change dropped.
- TradingView: a failed start with an owner token quits TradingView before releasing the lock; `TV_LOCK_DIR` test override; fixtures on a stub PATH.
- Runs dir: prune limited to packet/brief/verdict files; `SIGNAL_JUDGE_RUNS_DIR` honoured. Dry-run packets carry `dry_run: true` and `apply` refuses them. Top-level exception handler logs and exits 1.
- FX with Yahoo down: checks skipped, not `NO_DATA`. `risk_scale` = (trigger, tp1). `ema20` from `entry_ref.price`. HTF bias read on the forming bar, accepted and flagged. `labels_capped` from `total_labels`. `pending_since`, `row_times`, `outcome.reported` added to the ledger; numeric `basis` renamed `price_basis`.
- `counts` defined with identities; `skipped_reason` enum; "previous packet" defined; `--symbol` defined; cross-pair / laggard set taken before drops.
- Dashboard: one env name `SIGNAL_JUDGE_DATA_DIR`; filter by `alert_time` date; exact `match` per sheet row time; error state; mtime-keyed cache; placement after the empty-rows return.
- Report: H1 carries the first run's time; section time = packet `created_at`; precedent links built from the case's `note` path; Resolved table driven by `outcome.reported`.
- Verification window adds 05:25–06:00 (Equity News — US/EU); doc-drift list adds the Lint exception, the Tooling list, `validate_h4_signals.py` superseded CLI, and the Case Store Rule's gate sentence.

Revision 6 (2026-11-03, Mac mini) — Phase 2 only, after Phase 1 shipped (`24de086`) and the 4H grid fix (`f002e4f`):
- User decisions: judged pairs FX 4H / metals-oil-indices 1H (others `out_of_tf`); WTI added (oil class, `CL=F`); own analysis when no precedent applies, labelled `basis: own_analysis`, scored separately, confidence from the checklist; all 5 slots incl. 18:01 (17:00 skip window removed).
- Schedule: US standard-time slots 07:01/10:01/14:01/18:01/22:01; contention with Daily Signals 06:45 and Equity News — Asian 17:30.
- Round-5 open points resolved: `D` ≡ `1D` (§4); one `setTimeframe` retry (§3); short session-end bars via the close formula (§4) with a fixture; the 17:00–18:00 NY break detected explicitly for non-FX (§4); basis from a common closed 1H bar (§4); inline judging in the slot session, no subagent (§Judge protocol); retries rebuilt from current sheet rows, else stored fields (§2); start in its own process group, killed on timeout, and owner-checked stop that leaves TradingView alone when the lock is gone or not ours (§Surfaces, §5); delayed-alert re-keying after the chart pass (§2); interpreter = PATH `python3` with gspread, lazy import → exit 3 (§Surfaces).
- Nominal 4H bar close from `bar4h_start` (NY-anchored); Related finding closed.
- Case-store sections moved to `signal-cases-phase1.md`; Phase 1 is used through `find_precedents`.

Revision 5 (2026-11-02): market-hours window; signal bar by close time; read validation; lock owner token + budget; monthly shards; weekend skip; `fetch_with_service_account`; one scorecard; brief.md; aliases; untracked class judged; `max_labels: 500`. Revisions 2–4: TradingView bars instead of a session model; entry at run time; fail-on-timeout lock; budget; writer host; dedupe; dashboard keys; judge template.

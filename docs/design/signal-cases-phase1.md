# Design: Signal Judge Phase 1 — the Binni case store

Status: revision 3 (implemented 2026-11-02 at the user's instruction — "apply the fixes, build phase 1 and run the pilot here" — without a further review round; the binding clarifications below override earlier text where they differ) · 2026-11-02 · Mac mini (`pepper`). Parent design: `docs/design/signal-judge.md` (the full loop, now parked). The user split the work on 2026-11-02: Phase 1 (this doc) builds and measures the case store; the live judge (pre-filter, TradingView pass, judge, ledger, tracker, report, dashboard) is Phase 2, a separate `/eg-new-feature` designed after Phase 1's pilot numbers and a few manual dry runs.

## Why

The Signal Judge will rule on each new 1H/4H TAT signal by citing Binni's own past calls. That only works if those calls can be pulled out of the session notes in a structured, checkable form, and if enough of them resemble the signals that actually fire. Phase 1 builds the store and answers the second question with numbers before any live pipeline exists:

- **Case store**: every concrete instrument call in the session notes as one structured record (instrument, timeframe, direction, Binni's verdict, setup / location / structure tags, a verified quote).
- **Hindsight**: what price did in the 10 trading days after each call (user decision 2026-11-02: shown to the judge, which weighs it; it does not change retrieval).
- **Retrieval**: `find_precedents()`, the deterministic similarity search Phase 2 will call.
- **Coverage report**: replays recent real 1H/4H alerts against the store and reports how many would have found a meaningful precedent. This is the go/no-go for Phase 2.

User decisions carried from the parent design: the judge's instruments are FX + metals + indices, including ones Yahoo can't track (judged, marked untracked); `wiki/` syncs between machines via Obsidian Sync, and a `.jsonl` sync test is pending (`wiki/notes/signal-judge/sync-test.jsonl`, written on the Mac mini 2026-11-02 14:02 SGT); this work runs on the Mac mini.

## Scope

In:
1. `scripts/signal_cases.py`: CLI `pending`, `add`, `score`, `match`, `coverage`, `stats`, and importable `find_precedents()`, `canon_instrument()`, `instrument_class()`, `instrument_currencies()`, `parse_tflow_event()`, `load_alerts()`.
2. Data: `wiki/notes/signal-judge/cases.jsonl`, `wiki/notes/signal-judge/notes_done.json`.
3. `.agents/skills/signal-judge/SKILL.md` (Phase 1 content) and `.agents/skills/signal-judge/reference/case-extraction.md` (the extraction protocol, verbatim below).
4. The ingest hook: step 7 in `.agents/skills/trading-transcript-ingest/SKILL.md`, **and** a pointer in AGENTS.md's "Market Session Ingest Prompt & Template" workflow note (that skill isn't registered as a slash-command skill and AGENTS.md never names it, so an ingest that follows AGENTS.md would otherwise miss the step).
5. AGENTS.md: a short **Signal Case Store Rule** and a lint exception for the data files.
6. The pilot (below), then stop for the user's go/no-go. Backfilling the remaining notes happens only after a "go".

Out (Phase 2 or later): anything that runs in the Orca slots, opens TradingView, writes under `wiki/reports/`, or touches the dashboard. No change to any existing script.

## Surfaces touched

New: `scripts/signal_cases.py`; `.agents/skills/signal-judge/SKILL.md`; `.agents/skills/signal-judge/reference/case-extraction.md`; `scratch/check_signal_cases.py` (fixture checks; `scratch/` is tracked by git here, so this file is committed); data under `wiki/notes/signal-judge/` (not in git); staged files under `scripts/signal_judge_runs/` (new `.gitignore` entry).

Changed (additive only): `.agents/skills/trading-transcript-ingest/SKILL.md` (step 7); `AGENTS.md` (the rule, the ingest-note pointer, the lint exception); `.gitignore`.

Imported, unchanged: `fetch_with_service_account` from `scripts/fetch_google_sheet.py`; `is_in_scope`, `clean_symbol`, `SIGNAL_TIER`, `TFLOW_PREFIX`, `cross_pair_consistency` from `scripts/validate_h4_signals.py`.

Git: `AGENTS.md` and `scripts/update_weekly_index.py` carry the user's own uncommitted edits on this machine. The feature commit stages only its own files and its own `AGENTS.md` hunks (`git add -p`).

Interpreter: the `python3` on `PATH` here, `/Library/Frameworks/Python.framework/Versions/3.10/bin/python3` (3.10.7, with gspread), which Orca and ingest sessions use. `coverage` needs gspread; the other commands use only the standard library (3.9-compatible). There is no `.venv` on the Mac mini.

## Interfaces

### 1. Data files

**`wiki/notes/signal-judge/cases.jsonl`**, one JSON object per line. Fields set by `add` (not in the staged file): `id`, `note`, `date`, `session_type`, `instrument` (canonicalised), `quote_in_raw`, `extracted_at`, `hindsight` (null until `score`).

| Field | Type / enum | Required in staged file |
|---|---|---|
| `id` | `<note-stem>-<instrument lower>-<n>`, `n` = 1-based order of that instrument's cases in the staged file | — (set by add) |
| `note` | repo-relative path (from `--note`) | — |
| `date` | `YYYY-MM-DD`, the note filename's date prefix | — |
| `session_type` | `ahh-access-time` \| `ahh-session` \| `taw-pro` \| `weekly-review` \| `3tt` \| `tar-session` (from the filename) | — |
| `opportunity_no` | int \| null | yes (may be null) |
| `section` | str, non-empty | yes |
| `instrument` | str (canonicalised by add) | yes |
| `asset_class` | `fx` \| `metal` \| `index` \| `crypto` \| `stock` \| `commodity` | yes |
| `tf` | `m15` \| `1h` \| `4h` \| `d` \| `w` \| `m` \| `unspecified` | yes |
| `direction` | `long` \| `short` \| `neutral` | yes |
| `verdict` | `take` \| `wait_retest` \| `conditional` \| `watch` \| `skip` \| `already_moved` | yes |
| `condition` | str \| null; non-empty required for `conditional` and `wait_retest` | yes (may be null otherwise) |
| `setup` | list ⊂ setup vocabulary (below) | yes (may be empty) |
| `location` | list ⊂ location vocabulary | yes (may be empty) |
| `structure` | `with_trend` \| `counter_trend` \| `range` \| `transition` \| `unspecified` | yes |
| `htf` | `aligned` \| `opposed` \| `ambiguous` \| `unspecified` | yes |
| `risk_flags` | list ⊂ risk vocabulary | yes (may be empty) |
| `signal_named` | str \| null | no (default null) |
| `levels` | str \| null | no (default null) |
| `quote` | str, 1–300 chars and 2+ words, found in the note | yes |
| `timestamp` | str \| null | no (default null) |
| `quote_in_raw` | bool \| null | — |
| `extracted_at` | ISO datetime SGT | — |
| `hindsight` | object \| null (§3 `score`) | — |

Vocabularies: setup = {`breakout`, `retest`, `trend_continuation`, `pullback_in_trend`, `reversal`, `range_bounce`, `range_break`, `trendline_break`, `pattern_hs`, `pattern_double`, `tflow`, `laggard`, `leader`}; location = {`htf_level_behind`, `htf_level_ahead`, `at_d_zone`, `open_space`, `mid_range`, `at_wash_line`, `at_ema`}; risk = {`news_pending`, `ugly_chart`, `friday`, `late_entry`, `room_consumed`, `counter_trend`, `intervention_risk`}. Unknown keys in a staged case are ignored with a warning.

**`wiki/notes/signal-judge/notes_done.json`** = `{"<note-stem>": {"note": path, "extracted_at": iso, "cases": int, "rejected": int}}`.

### 2. Symbol helpers

- `canon_instrument(s)`: strip whitespace, `[[`/`]]` and an exchange prefix (`XXX:`), upper-case; apply the dashboard's `ALIASES` (`dashboard/wiki_data.py:109`, copied into `signal_cases.py`); **then** these overrides (applied after, so they win): `NDX`, `NAS100`, `US100`, `NASDAQ` → `NDQ100`; `S&P`, `SPX`, `US500`, `SP500` → `SPX500`; `JP225`, `NIKKEI`, `NIKKEI225`, `N225` → `JPN225`; `RUSSELL`, `RUT` → `US2000`; `DXY`, `USDX`, `DXYUSD` → `USDX`; `NKY`, `NI225` → `JPN225`; `NQ1!`, `NQ100` → `NDQ100`; `SPXUSD` → `SPX500`; `FCHI` → `FRA40`; `HSIINDEX`, `HKSE` → `HSI`; `TESLA` → `TSLA`; `HGUSD`, `COPPER` → `XCUUSD`; `BITCOIN` → `BTCUSD` (aliases added from the backfill's names).
- `instrument_class(sym)` (on a canonical symbol): `fx` (`is_in_scope` and 6 letters), `metal` (XAUUSD, XAGUSD), `index` (NDQ100, SPX500, US30, US2000, JPN225), `untracked` (GER40, HK50, UK100, FRA40, CN50, USDX, XAUJPY, XAUAUD, XAUGBP), else `out`. Retrieval compares an `untracked` symbol by its kind: indices and USDX → `index`, metal crosses → `metal`.
- `add` checks a staged case's `asset_class` against `instrument_class` when the class is fx / metal / index / untracked (kind as above): a mismatch rejects the case. `out` instruments accept any asset_class.
- `instrument_currencies(sym)`: FX → both legs; XAUUSD, XAGUSD → `["USD"]`; XAUJPY/XAUAUD/XAUGBP → `["USD", <cross>]`; NDQ100, SPX500, US30, US2000, USDX → `["USD"]`; JPN225 → `["JPY"]`; GER40, FRA40 → `["EUR"]`; UK100 → `["GBP"]`; HK50 → `["HKD"]`; CN50 → `["CNY"]`; crypto (`…USD`) → `["USD"]`; else `[]`.

### 3. CLI

All diagnostics go to stderr. Env `SIGNAL_CASES_DIR` replaces `wiki/notes/signal-judge/` (fixtures). `cases.jsonl` and `notes_done.json` are only ever written under an `fcntl` lock on `<dir>/cases.lock` (wait up to 60 s, else exit 4), by re-reading inside the lock, merging, writing a temp file and `os.replace`.

```
python3 scripts/signal_cases.py pending [--json]
    Note set: wiki/AHH Session Notes/*.md and wiki/sources/*.md whose stem fully matches
    ^\d{4}-\d{2}-\d{2}-(ahh-access-time|ahh-session|taw-pro|weekly-review(-binni)?|3tt|tar-session)(-.*)?$
    (weekly-review-binni -> weekly-review). Prints the paths whose stem is not in notes_done.json,
    newest first. mtime is not used. Exit 0.

python3 scripts/signal_cases.py add --note "<path>" --file <staged.json> [--replace]
    Exit codes:
      2  staged file or note unreadable / not a JSON array. Nothing written.
      1  note already in notes_done.json and no --replace. Nothing written.
      3  the array is non-empty but every case was rejected. Nothing written; the note stays pending.
      4  lock timeout.
      0  written: the valid cases (possibly none, when the array is empty) are stored, the note is
         recorded in notes_done.json (cases, rejected counts).
    Rejected cases (any exit 0 or 3) are written with their reasons to
    scripts/signal_judge_runs/cases_<stem>.rejects.json for review; the staged file itself is never
    deleted by add. Prints "added N of M (K rejected)".
    Validation per case: required keys and enums (§1, incl. every element of the list fields);
    condition non-empty for conditional and wait_retest; asset_class vs instrument_class (§2);
    opportunity_no (§4); the quote check (§5).
    --replace: the note's existing cases are replaced; hindsight carries over only to a new case
    with the same id AND the same instrument, direction and verdict.

python3 scripts/signal_cases.py score [--all]
    Candidates: cases with direction long|short whose hindsight is null, or "unscored" with reason
    fetch_failed or no_bars (retried every time); --all rescores every directional case. Only cases
    whose note date + 14 calendar days < today (SGT). Fetches outside the lock, then takes the lock,
    re-reads cases.jsonl, applies the results by id, writes.
    Bars: yahoo_daily(ticker, note date − 40 d, note date + 30 d) (§6). Entry bar = the first
    daily bar whose exchange-local date is after the note date; entry = its OPEN. ATR = Wilder 14
    on the 15+ bars before the entry bar (fewer → unscored/no_bars). Fewer than 10 bars from the
    entry bar onward → left null (scored on a later run). Walk the 10 bars from the entry bar:
    favourable if a high (long) / low (short) reaches entry + 1 ATR in the called direction before
    a bar reaches entry − 1 ATR against it; adverse if the reverse; both on the same bar → adverse;
    neither → flat. mfe_atr / mae_atr = the maximum favourable / adverse excursion over all 10
    bars, in ATR units. Writes {"status", "mfe_atr", "mae_atr", "horizon_days": 10, "scored_at",
    "reason": null|"no_ticker"|"fetch_failed"|"no_bars"}.
    Ticker map: FX <SYM>=X; XAUUSD GC=F; XAGUSD SI=F; NDQ100 NQ=F; SPX500 ES=F; US30 YM=F;
    US2000 RTY=F; JPN225 NIY=F; crypto <BASE>-USD; anything else → unscored/no_ticker (final).
    Prints counts per status. Exit 0, or 4 on lock timeout.

python3 scripts/signal_cases.py match --signal <json file> [--top 5]
    Prints find_precedents() for one signal object (§7; time as ISO). Exit 0.

python3 scripts/signal_cases.py coverage [--days 14] [--json]
    §8. Exit 0, or 3 if both sheet tabs failed.

python3 scripts/signal_cases.py stats
    Counts by session_type, verdict, tf, asset_class and direction; quote_in_raw true/false/null;
    hindsight status counts; notes done vs pending; total rejected. Exit 0.
```

### 4. `opportunity_no` check

The opportunities section is the first `## ` heading whose text contains `Opportunit` (case-insensitive; covers `📈 Trading Opportunities`, `… Opportunities & Instrument Studies`, `… & Key Level Analysis`, `Trading Instruments & Opportunities`), up to the next `## `. Its items are lines matching `^(\d+)\. ` at the start of a line. A non-null `opportunity_no` must be one of those numbers, and that item's text up to the next item must contain the case's instrument (raw, canonical or any alias mapping to it, case-insensitive). A note without such a section requires `opportunity_no` null.

### 5. Quote checks (in `add`)

- Normalise both texts: strip `[[`, `]]`, `**`, `*`, `_` and backticks; curly → straight quotes; `…` → `...`; en/em dashes → `-`; collapse whitespace; lowercase. The normalised quote must be a substring of the normalised note; else the case is rejected ("quote not found in note").
- `quote_in_raw` (informational, never blocks). Locate the transcript in order:
  1. the note's `raw:` frontmatter: try it relative to the repo root, then relative to the note's folder; use it if the file exists;
  2. else `*.md` under `raw/` (recursively, excluding only `raw/recordings/`) whose lowercased basename, with `_` and spaces turned into `-`, contains the note's date (`YYYY-MM-DD` or `YYYYMMDD`) and a session-type token (ahh-access-time → `ahh-access-time` | `access-time`; ahh-session → `ahh-session`; taw-pro → `taw-pro` | `tat-pro`; weekly-review → `weekly-review`; 3tt → `3-trade-thoughts` | `3tt`; tar-session → `tar-session`); the first by path order if several;
  3. else the single `*.md` under `raw/` with that date, if exactly one;
  4. else none → null.
  
  Match: split the normalised transcript into words; windows of 400 words starting every 50 words; in each window, scan greedily left to right for the quote's words in order (gaps allowed); true if any window matches ≥ 80% of the quote's words; false otherwise.
- This proves fidelity to the note (Claude's summary of the session), and only informationally to Binni's words, an accepted limit.

### 6. Yahoo daily fetcher

`yahoo_daily(ticker, start, end) -> bars`: `GET https://query1.finance.yahoo.com/v8/finance/chart/<ticker>?interval=1d&period1=<unix>&period2=<unix>`, browser User-Agent, timeout 15 s, no retry. Each bar's date = the timestamp converted with `zoneinfo.ZoneInfo(meta["exchangeTimezoneName"])` (not `meta.gmtoffset`, which is the *current* offset and mis-dates bars from before a DST change; e.g. GBPAUD=X bars are stamped 23:00 UTC = 00:00 London in summer). Bars with null OHLC are dropped. Network/HTTP error → `fetch_failed`; empty → `no_bars`.

### 7. `find_precedents`

```python
def find_precedents(signal, cases, top=5):
    """signal = {"instrument": "GBPUSD" (canonical), "direction": "long"|"short",
                 "time": aware datetime (the signal bar's close),
                 "tags": {"tf": str, "setup": [..], "location": [..], "structure": str,
                          "htf": str, "risk_flags": [..]}}
    returns {"instrument_recent": [dict(case, same_direction=bool), ...],
             "similar": [dict(case, similarity=float, same_direction=bool), ...]}"""
```
`asset_class` and `currencies` are derived inside (`instrument_class` by kind, `instrument_currencies`).
- Eligible cases: `date` strictly before the SGT date of `signal["time"]`. Direction is not a filter. Each returned case is marked `same_direction` (the case's direction equals the signal's; `neutral` cases → false), because a recent opposite call is evidence too.
- **instrument_recent**: same canonical instrument, date within the 21 days before, newest first, max 3, no threshold.
- **similar**: every other eligible case (only those already in instrument_recent are excluded). Components count toward the maximum only if the signal has a value for them (non-empty list, or not `unspecified`):

| Component | Points | Substantive |
|---|---|---|
| tf exact / adjacent (m15↔1h, 1h↔4h, 4h↔d, d↔w, w↔m) | 2 / 1 (max 2) | no |
| each shared `setup` tag | 2 each (max 2·\|signal setup\|) | yes |
| each shared `location` tag | 2 each (max 2·\|signal location\|) | yes |
| `structure` equal | 2 | yes |
| `htf` equal | 1.5 | yes |
| each shared `risk_flags` tag | 1 each (max \|signal risk_flags\|) | no |
| same asset class (by kind) | 1 | no |
| shares a currency (both FX) | 1 (in the max only for FX signals) | no |

  A case is kept only if it shares **at least one substantive component** and `similarity = points / max ≥ 0.45`. That keeps matches on timeframe, asset class and currency alone out. Sort by similarity desc, then date desc; top 5.

### 8. `coverage`

**`load_alerts(rows_by_tab, since)`**: `rows_by_tab = {"1H": [...], "4H": [...]}` (rows as returned by `fetch_with_service_account`), `since` = aware datetime. Returns a list of deduped alert dicts:
`{"key", "symbol" (canonical), "tv_symbol" (sheet Symbol), "class", "tf": "1H"|"4H", "direction": "long"|"short", "signal", "also_fired": [...], "event", "tflow": dict|null, "nominal_close": aware dt, "alert_time": aware dt}`.
- Rows: `Date` + `Time` (`%H:%M:%S`, `%H:%M`, `%I:%M:%S %p`, `%I:%M %p`) as SGT; `nominal_close` = alert time floored to the hour; kept if `nominal_close ≥ since`, the signal (minus `Tflow `) is in `SIGNAL_TIER`, and `instrument_class` ≠ `out`. Direction from the sheet's `Direction` (`Bullish` → long, `Bearish` → short).
- Dedupe: group by (symbol, tf, direction, nominal_close); signal = the Tflow row's if any, else the highest tier (Opt > L > S); `also_fired` = the others; `event` from the chosen row; `key` = `<symbol>|<tf>|<Bull|Bear>|<nominal_close ISO>`.

**`parse_tflow_event(event)`**: anchored regex `^Tflow (Bullish|Bearish) Signal(?: @Zone \((Support|Resistance) Zone x(\d+) \(([A-Z,]+)\), Zone High: ([\d.]+), Zone Low: ([\d.]+)\))?: D Level: ([\d.]+), (LL|HH): ([\d.]+)` → `{"direction": "Bullish"|"Bearish", "at_zone": bool, "zone": {"role": "Support"|"Resistance", "count": int, "tfs": "M,W", "high": float, "low": float} | null, "d_level": float, "pivot_label": "LL"|"HH", "pivot": float}`; no match → `{"parse_error": event, "at_zone": false}`.

**Fetch**: `fetch_with_service_account("H1")` and `("4H")`, each in try/except inside `contextlib.redirect_stdout(buffer)` (buffer echoed to stderr). A tab that raises, returns None (no credentials, `fetch_google_sheet.py:125-126`) or returns 0 rows is failed; both failed → exit 3. A buffer containing `Tflow supplement skipped` → the report's first line warns that Tflow tags are missing.

**Tags** per alert, anchored on `nominal_close`:
- `tf`: `1h` / `4h`.
- `setup`: `tflow` + `pullback_in_trend` if the signal is Tflow. `laggard` (FX only): build `prior` = the deduped FX alerts in the same tab whose `nominal_close` is 1, 2 or 3 bar lengths (1 h / 4 h) earlier; call `cross_pair_consistency({"clean": symbol, "direction": "Bullish"|"Bearish"}, [{"clean": a.symbol, "direction": …} for a in prior])`; `laggard` if the returned score ≥ 0.5.
- `location`: `at_d_zone` if `tflow.at_zone`; nothing else (no chart).
- `structure`: `unspecified`.
- `htf`: the daily brief usable at `nominal_close` is `~/tradingview-mcp/daily_brief/<D>.json` for the latest D such that `nominal_close ≥ D 06:30 SGT` (the brief is written ~05:06–06:03 SGT on D, after the 05:00 Daily close), and at most 3 days older than nominal_close. Its entries are matched on `canon_instrument(entry["symbol"]) == symbol` (the brief uses e.g. `TVC:DXY` for USDX). `bias` equal to the direction → `aligned`, opposite → `opposed`, `neutral` → `ambiguous`; no usable file or entry → `unspecified`.
- `risk_flags`: `friday` if `nominal_close` in New York time is a Friday at or after 01:00. `news_pending` is computed only when the 24 h after `nominal_close` lies inside the date range of the "This Week" or "Next Week" tables of `wiki/notes/economic-calendar.md` (the note holds no history): set if a row there has Date + Time (SGT) within that 24 h and a Currency in `instrument_currencies(symbol)`. Outside that range the flag is left off and doesn't count toward the maximum (no penalty for missing data).

**Report** (text; `--json` prints the same as one object):
```json
{
  "generated_at": iso, "days": 14,
  "alerts_range": {"first": iso, "last": iso},          (what the sheet actually returned; the 4H tab only goes back to 2026-10-19)
  "sheet": {"1H": "ok|failed", "4H": "ok|failed", "tflow_skipped": bool},
  "alerts": {"total": n, "by_tab": {"1H": n, "4H": n}, "by_class": {"fx": n, "metal": n, "index": n, "untracked": n}},
  "cases": {"total": n, "first_date": "YYYY-MM-DD", "last_date": "YYYY-MM-DD"},
  "rates": {"instrument_recent_ge1": pct, "similar_ge2": pct, "either": pct},
  "rates_by_tab": {"1H": {...same keys}, "4H": {...}},
  "rates_by_class": {"fx": {...}, ...},
  "similar_component_mix": {"setup": n, "location": n, "structure": n, "htf": n},   (how often each substantive component produced a kept match)
  "top_cases": [{"id": str, "as_recent": n, "as_similar": n}],   (10, by as_recent + as_similar)
  "never_matched_tags": {"setup": [..], "location": [..], "htf": [..], "risk_flags": [..]},   (values present on alerts that no returned similar case shared)
  "gate": {"metric": "either", "value": pct, "recommend_go_at": 60}
}
```
Text mode prints these as labelled lines and ends with `GATE: <pct>% (recommend go at >= 60%)`.

## The extraction protocol (`reference/case-extraction.md`, verbatim)

```
# Case extraction

Turn one session note into a JSON array of cases: one case per concrete call Binni makes about an
instrument. Write the array to scripts/signal_judge_runs/cases_<note-stem>.json. Do NOT run add
yourself when you are a backfill subagent; the session that started you runs add for each note,
one at a time. In an ingest session, run:
python3 scripts/signal_cases.py add --note "<note path>" --file <that file>

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
```

(Both quotes are substrings of the note after normalisation; the `**4H broke the uptrend line**` markup is stripped.)

## UX flow

- **Ingest** (step 7 of `trading-transcript-ingest`, after the hot-cache rewrite, for notes whose stem matches the `pending` regex): follow `reference/case-extraction.md`, then run `add`.
  - Exit 0: run `score`, and delete the staged file.
  - Exit 3 or 2: leave the staged file, mention it in the ingest summary; the note stays pending.
  - Exit 1: the note was already extracted; nothing to do.
  - Either way, if `cases_<stem>.rejects.json` exists, mention its count in the summary.
- **Pilot** (this feature, on the Mac mini): the 10 newest pending notes **plus** the 5 newest pending notes dated at least 21 days ago (so `score` runs on real data). Two extraction subagents, run one after the other in the foreground, each given a list of notes and the protocol, each only writing staged files. This session then runs `add` per note, `score`, `stats`, `coverage --days 14`, reports, and stops.
- **Backfill** (after a "go"): the same for the rest of `pending`, up to 4 subagents of 5 notes at a time writing staged files, then `add` per note by the main session.

## Data contract

Reads: session notes (`wiki/AHH Session Notes/`, `wiki/sources/`); `raw/` transcripts; the H1/4H sheet tabs and the Tflow extract sheet (coverage only); Yahoo daily bars (score only); `~/tradingview-mcp/daily_brief/*.json`; `wiki/notes/economic-calendar.md`.

Writes: `wiki/notes/signal-judge/cases.jsonl` and `notes_done.json` (only `add` and `score`, under the lock); `scripts/signal_judge_runs/cases_<stem>.json` (extraction; deleted after `add` exit 0 by the ingest step / pilot) and `cases_<stem>.rejects.json` (`add`; kept for review). Consumers today: `signal_cases.py` itself; Phase 2 later. No existing output changes.

Sync: cases are written on whichever machine ingests (one ingest at a time). If the sync test shows `.jsonl` doesn't sync, ingest step 7 is done on the Mac mini only (the skill and the AGENTS.md rule say so), since Phase 2 runs there.

## Timing / TradingView / unattended

No schedule, no TradingView, no Orca change. Everything runs by hand or inside an ingest session. `coverage`: 2 sheet reads (~10–20 s). `score`: one Yahoo call per candidate case (~0.5 s each).

## Docs to update

- `.agents/skills/signal-judge/SKILL.md` (new): what the case store is; the CLI and exit codes; the extraction protocol pointer; the coverage gate; "Phase 2 (live judge) is designed separately — see `docs/design/signal-judge.md`".
- `.agents/skills/signal-judge/reference/case-extraction.md` (new, verbatim above).
- `.agents/skills/trading-transcript-ingest/SKILL.md`: step 7 (the UX flow above). Its steps 1 and 5 still say `wiki/sources/` / `--category sources` for session notes (moved to `wiki/AHH Session Notes/` on 2026-09-27); reported to the user, not fixed here.
- `AGENTS.md`:
  - **Signal Case Store Rule** under Workflow notes: what it is, where it lives, the CLI, that every session ingest ends with case extraction, the sync caveat.
  - In the "Market Session Ingest Prompt & Template" note: one added item, "6. After the bookkeeping, extract cases per `.agents/skills/signal-judge/reference/case-extraction.md` and run `python3 scripts/signal_cases.py add` (Signal Case Store Rule)."
  - Lint exceptions: `wiki/notes/signal-judge/*.json*` are data files, not pages.

## Failure modes

| Breakage | What the user sees |
|---|---|
| Some quotes not in the note | Those cases rejected, listed in `cases_<stem>.rejects.json`; the rest stored |
| Every case rejected | `add` exit 3; nothing stored; the note stays pending; the staged file is kept |
| Staged file malformed | `add` exit 2; the note stays pending |
| Note edited later | Nothing automatic (mtime isn't used); `add --replace` re-extracts on request |
| Yahoo down during `score` | Cases stay `unscored/fetch_failed`, retried on the next `score` |
| Sheet unavailable during `coverage` | Exit 3, or a per-tab "failed" in the report |
| Tflow extract sheet unreadable | `coverage` warns on its first line |
| Concurrent writers on one machine | The lock serialises them; > 60 s wait → exit 4 |
| `.jsonl` doesn't sync | MacBook ingests' cases don't reach the Mac mini; contingency above |

## Verification criteria

1. `scratch/check_signal_cases.py` (run with `python3`, no network; stubs for `fetch_with_service_account` and `yahoo_daily`; `SIGNAL_CASES_DIR` pointed at a temp dir), each an assert:
   - `canon_instrument`: `[[US100]]`, `NASDAQ`, `EIGHTCAP:NDQ100` → `NDQ100`; `JP225` → `JPN225`; `DXY`, `TVC:DXY`, `USDX` → `USDX`; `GOLD` → `XAUUSD`. `instrument_class`: GBPUSD fx, XAUUSD metal, US30 index, GER40 untracked, BTCUSD out. `instrument_currencies`: XAUJPY → USD, JPY; JPN225 → JPY.
   - Quote check: both worked-example quotes pass against the real 2026-10-27 note; a fabricated quote fails; a quote containing `[[GBPJPY]]` or `**` markup passes.
   - `add` exit codes: an all-rejected non-empty array → 3, note still pending, rejects file written; an empty array → 0, note done with 0 cases; a mixed array → 0 with N stored and a rejects file; a second add without `--replace` → 1; an unreadable staged file → 2. Validation: an unknown list element (`setup: ["moonshot"]`) rejected; `conditional` without condition rejected; `asset_class: "index"` for GBPUSD rejected; an `opportunity_no` whose item doesn't mention the instrument rejected; ids follow `<stem>-<instrument>-<n>`; `--replace` keeps hindsight only for same id + instrument + direction + verdict.
   - `opportunity_no` sections: `## 📈 Trading Opportunities & Key Level Analysis` and `## Trading Instruments & Opportunities` both found; a note without such a heading accepts only null.
   - `pending`: the regex matches `2026-10-24-3tt-week-of-26-oct`, `2026-03-07-weekly-review-binni`, `2026-08-13-tar-session`, not `2026-10-23-tat-v3-user-guide`.
   - Raw lookup: the 2026-10-27 AHH note (no `raw:` key) → `raw/2026-10-27-ahh-access-time.md`; the 2026-10-21 TAW Pro note → `raw/2026-10-21-taw-pro.md` although an AHH file shares the date; a note whose `raw:` points to a missing file falls through to step 2; a `raw/archives/` transcript is found.
   - `quote_in_raw` match: a quote with 1 of 10 words missing → true; with 3 of 10 missing → false; words out of order → false.
   - `yahoo_daily` dating: a stubbed response with `exchangeTimezoneName` `Europe/London`, `gmtoffset` 0, and timestamps at 23:00 UTC on 2026-10-20 and 00:00 UTC on 2026-10-27 dates them 2026-10-21 and 2026-10-27.
   - `score` on synthetic daily bars: favourable, adverse, flat, same-bar both → adverse; entry = the next day's open; mfe/mae over all 10 bars; 14 bars before entry → `no_bars`; 8 bars after → left null; `fetch_failed` retried on the next call, `no_ticker` not; a concurrent `add` written between fetch and write survives (lock + re-read).
   - `find_precedents` on a fixture: expected order; a case at similarity ≥ 0.45 that shares only tf + asset class + currency is dropped (no substantive component); a case below 0.45 dropped; unspecified components excluded from the max; a same-day case excluded; instrument_recent limited to 21 days and to the canonical instrument (a `US100` case matches an `NDQ100` signal); `same_direction` set correctly, including for a `neutral` case.
   - `parse_tflow_event` on the real Event strings: EURNZD `Tflow Bullish Signal @Zone (Support Zone x5 (M,W), Zone High: 1.95478, Zone Low: 1.94507): D Level: 1.96230, LL: 1.95398. Filtered: None.` → at_zone, zone count 5, tfs `M,W`, high 1.95478, low 1.94507, d_level 1.96230, pivot_label LL, pivot 1.95398; NZDCHF `… @Zone (Support Zone x1 (W), Zone High: 0.46350, Zone Low: 0.46290): D Level: 0.46873, LL: 0.46328 …` → count 1, tfs `W`; AUDCHF `Tflow Bullish Signal: D Level: 0.58238, LL: 0.57036. Filtered: None.` → at_zone false, zone null; JPN225 `Tflow Bearish Signal: D Level: 64316.07, HH: 64576.07. Filtered: None.` → Bearish, HH; a malformed string → parse_error.
   - `load_alerts` dedupe: US30 `OptBear` 2:00:06 + `LBear` 2:00:04 → one alert (OptBear, also_fired [LBear]); XAUUSD `Tflow SBull 02:01:03` + `SBull 2:01:02` → one `Tflow SBull` alert.
   - Coverage tags: the daily brief for D is not used for a 05:00 SGT nominal close on D but is for 07:00; a `TVC:DXY` brief entry matches a USDX alert; `friday` true for a bar closing Saturday 02:00 SGT (Friday 13:00 NY), false for Friday 13:00 SGT (Friday 00:00 NY); `news_pending` not evaluated for an alert outside the calendar note's weeks; `laggard` true for a GBPAUD short with a EURAUD short two 4H bars earlier and false when that alert is four bars earlier.
   - A fetch stub returning None for one tab → that tab "failed", coverage still runs on the other; both failed → exit 3.
2. `python3 -m py_compile scripts/signal_cases.py scratch/check_signal_cases.py`; `python3 scripts/signal_cases.py --help` and each subcommand's `--help`.
3. **Pilot** (real data, with the user's OK to write `wiki/notes/signal-judge/`): as in the UX flow (15 notes).
   - `stats` shows cases from every pilot note, or the report explains the ones with 0.
   - The reject rate across the pilot is under 20%. If not, fix the protocol before continuing.
   - `score` scores the cases from the 5 older notes (non-null status for each directional one, or a stated reason).
   - Spot-check 5 random cases against their notes by reading them, and 2 hindsight results against a chart or the raw Yahoo bars.
   - `coverage --days 14`: report the gate value, the by-tab and by-class rates, `similar_component_mix`, the never-matched tags and the spot-check results. Check the gate isn't inflated: if `similar_component_mix` is dominated by `htf` alone, say so.
   - **Stop for the go/no-go.**
4. Sync: report whether `sync-test.jsonl` and `sync-test.md` reached the MacBook (the user checks); then delete both.

## Out-of-scope follow-ups

Phase 2 (the live judge), with the open points already found in the parent design's round 5: Daily resolution reported as `1D`; `setTimeframe` retry; short session-end bar matching; detecting the 17:00–18:00 NY break; basis from the same closed bar (Yahoo futures lag ~10 min); judging inline in the Orca session instead of via a background subagent; retry entries re-reading their sheet row; start in its own process group and stop quitting TradingView when the lock is gone; delayed-alert keys; the Mac mini's interpreter. Also the stale wording in `trading-transcript-ingest`, and a historical economic-calendar source for `news_pending`.

Phase 2 is built (2026-11-03): see `docs/design/signal-judge.md` rev 11. It adds the oil class (`USOUSD`), the shared `nominal_close` / `load_judged_alerts` loader and a per-tab Tflow-skipped flag to `signal_cases.py`.

## Revision 3 — binding clarifications

From the round-2 critic (C1–C11) and readiness (Q1–Q7):
- **Class order** (C1): `instrument_class` checks metal (XAUUSD, XAGUSD), then index, then untracked, then fx (`is_in_scope` and 6 letters, both legs in FX_CCY). Gold is never fx.
- **Pilot notes** (C2): every pending note dated on or after (replay start − 21 days). For `coverage --days 14` run on 2026-11-02 that is 2026-09-28 → 2026-10-28: 24 notes. Five extraction subagents (≤ 5 notes each, up to 4 at once), writing staged files only; this session runs `add` per note. The ≥ 21-day-old notes in that set exercise `score`.
- **Inflation check** (C3): the report adds `similar_only_htf` = number of alerts whose ≥ 2 kept similar matches all rest on `htf` as their only substantive component. Rates count **alerts**, not alert–case pairs. `similar_component_mix` counts kept (alert, case) matches per substantive component.
- **Gate fixture** (C4): `scratch/check_signal_cases.py` runs `coverage` end to end on stub alerts + a stub store and asserts the exact `rates`, `either`, `similar_only_htf` and `top_cases`.
- **Test isolation** (C5): env `SIGNAL_JUDGE_RUNS_DIR` replaces `scripts/signal_judge_runs/` (staged and rejects files). `note` = path relative to the repo root when the note is inside it, else absolute.
- **Writer host** (C6): `add` and `score` write only when `scutil --get LocalHostName` equals `writer_host` in `scripts/signal_judge_config.json` (gitignored; `{"writer_host": "pepper"}` on the Mac mini), else exit 6 "case store writes run on the Mac mini; the staged file is kept". `SIGNAL_CASES_DIR` set → check skipped (tests). Obsidian Sync doesn't merge non-markdown files, so one writing machine avoids lost cases. An ingest on the MacBook leaves the staged file; `pending` on the Mac mini picks the note up later.
- **score** (C7, Q5): a result is applied only if the re-read case still has the same id, instrument, direction and verdict. A failed fetch (`fetch_failed`/`no_bars`) or too few bars never overwrites an existing scored result (also under `--all`).
- **load_alerts** (C8): rows with an empty or unparseable `Date`/`Time`/`Direction`/`Signal Type` are skipped and counted (`skipped_rows` in the report). The signal column is `Signal Type`. Brief `bias` `bullish`/`bearish`/`neutral` maps to long/short/neutral before comparing.
- **Daily brief availability** (C9): file D is usable from max(D 06:30 SGT, the file's mtime).
- **Ingest order** (C10): step 7 runs after the hot-cache rewrite and **before** the Fireflies deletion step. An `add` exit 2/3/6 does not block deletion (the note persists, so cases can be extracted later). Both the skill and the AGENTS.md ingest note say so.
- **Laggard window** (C11): "1–3 bars earlier" = the previous 1–3 distinct nominal closes that exist in the same tab (any symbol), so weekends and the DST shift don't break it.
- **ids** (Q1): `n` counts accepted cases only, in staged order; `<instrument lower>` is the canonical symbol lower-cased.
- **Unknown note name** (Q2): a `--note` whose stem doesn't match the `pending` regex → exit 2.
- **Word matching** (Q3): words are `[a-z0-9]+` tokens of the normalised text (punctuation dropped) for `quote_in_raw`; the note substring check keeps punctuation.
- **21 days** (Q4): inclusive — case date ≥ signal SGT date − 21 days and < signal date.
- **Rejects file** (Q6): rewritten on every `add`; deleted when there are 0 rejects. Under `--replace`, exit 3 leaves the note's existing cases and notes_done entry untouched.
- **Tflow number capture** (found by the fixture): `[\d.]+` swallows the sentence-ending period (`LL: 1.95398.`); each number group is `\d+(?:\.\d+)?`.
- **Presenter** (user decision 2026-11-02, after the pilot found 10 of 24 notes presented by Pauline): keep Pauline's calls and tag them. Every case and `notes_done` entry carries `presenter` ∈ {`binni`, `pauline`, `unknown`}, set by the required `add --presenter` (chosen from the note header; no auto-detection, because headers mention both names). `stats` counts by presenter; `coverage` adds `precedent_presenter_mix`. Retrieval doesn't filter on it; Phase 2 decides the weighting.
- **alerts_range** (Q7): first/last nominal close of the deduped alerts the report uses.

## Revision log

Revision 2 (2026-11-02): round-1 critic (C1–C12) and readiness (Q1–Q12).
- C1: AGENTS.md ingest-note pointer. C2: add exit 3, rejects file, staged file kept. C3: substantive-component rule and `similar_component_mix`. C4: daily brief usable from D 06:30 SGT. C5: news_pending only inside the calendar note's weeks. C6: exchange-timezone dating.
- C7: raw: resolution and archives included. C8, Q1: `market_hours` dropped. C9, Q9: laggard pre-filter and score ≥ 0.5. C10: None counts as failed, canonical brief matching, the actual alert range reported. C11: score lock + re-read, exit codes, older pilot notes. C12: opportunities-section rule.
- Q2: `load_alerts` signature. Q3: `parse_tflow_event` keys. Q4: add derives note/date/session_type. Q5: required keys and full enum validation, asset_class check. Q6: mfe/mae window, bar minimums. Q7: `instrument_currencies`. Q8: direction kept as `same_direction`, not a filter. Q10: report counts. Q11: window step and greedy scan. Q12: `--json` schema.

---
name: daily-signal-tracker
description: Detects new signals on the Daily-timeframe TAT alert tab, captures a chart screenshot the moment one fires, and keeps capturing one screenshot per day afterward (configurable window, 14 days by default) to track whether price action actually moves in the signaled direction. Flags same-direction 1H/4H confluence as an immediate tactical entry trigger, opposite-direction 1H/4H prints as a pullback to watch, and a subsequent reversal back to the Daily direction after a pullback as "the elbow" — the highest-probability re-entry signal. Also checks the Weekly-chart TAT state directly via TradingView; a Weekly flip against the Daily direction invalidates the whole thesis regardless of 1H/4H. Runs once daily. The Daily-timeframe counterpart to tat-alert-analysis (H1/4H, 4x-daily) and equity-news-finder (equities).
license: MIT
metadata:
  author: AI Trading Team
  version: "2.0.0"
  tags:
    - google-sheets
    - alerts
    - tat
    - daily-timeframe
    - screenshot-tracking
    - confluence
    - pullback
    - invalidation
---

# Daily Signal Tracker Skill

The Daily-timeframe alert tab (`gid=462165474`, same sheet as `tat-alert-analysis`) is only ever checked once per day today, folded into the Daily Brief's own multi-timeframe synthesis — unlike H1 and 4H (reviewed together 4x-daily, the only scheduled TAT alert cadence as of 2026-09-01), it has no dedicated, continuously-updated report and no forward-looking tracking of what happens *after* a Daily signal fires. This skill closes that gap: it runs once per day, detects genuinely new Daily-timeframe signals, and for each one opens a tracked "watch" — a daily screenshot + price check that continues for a configurable number of days (14 by default), so you can visually and numerically see whether price actually followed through in the signaled direction.

---

## 📋 1. Data Sources

- **Daily Alerts Tab**: same sheet as `tat-alert-analysis`, `gid=462165474`. Pull via `python3 scripts/binni_alert_analysis.py --timeframe DAILY`.
- **State file**: [scripts/daily_signal_watches.json](file:///Users/chriseah/obsidian/wiki-trades/scripts/daily_signal_watches.json) — the only source of truth for which signals are being tracked, at what day, and with what configuration. Structure:
  ```json
  {
    "config": {
      "default_watch_days": 14,
      "symbol_overrides": { "XAUUSD": 7 }
    },
    "watches": [
      {
        "symbol": "EURUSD", "direction": "Bearish", "signal_name": "OptBear",
        "signal_date": "2026-08-29", "signal_price": 1.1650,
        "watch_days": 14,
        "days_tracked": [
          {"day": 0, "date": "2026-08-29", "price": 1.1650, "screenshot": "wiki/images/260829-..._eurusd_D_chart.png"}
        ],
        "confluence_triggers": [
          {"day": 3, "timeframe": "1H", "signal_name": "OptBear", "timestamp": "2026-09-01 14:00:24"}
        ],
        "pullback_flags": [
          {"day": 1, "timeframe": "4H", "signal_name": "LBull", "timestamp": "2026-08-30 09:00:00"}
        ],
        "elbow_events": [
          {"day": 2, "timeframe": "4H", "signal_name": "OptBear", "timestamp": "2026-08-31 05:00:00", "note": "Reversed back to Daily direction after the day-1 pullback -- the elbow."}
        ],
        "invalidated": false,
        "invalidated_reason": null,
        "invalidated_day": null,
        "status": "active"
      }
    ]
  }
  ```
  `config.symbol_overrides` lets the user pre-configure a non-default watch length for a specific pair — check it before falling back to `config.default_watch_days` whenever a *new* watch is created. Never write back to `config` yourself; it's user-editable only. An in-progress watch's own `watch_days` field can also be hand-edited by the user directly to shorten/extend that specific watch — always read `watch_days` fresh from the watch entry itself when deciding whether it's complete, never assume it still matches the config.
- **1H/4H confluence/pullback check source**: `wiki/reports/tat_analysis/YYYY-MM-DD-tat-alert-report.md`, maintained by the 4x-daily ("TAT Combined 1H+4H Review") Orca automation — read this directly rather than re-fetching the H1/4H sheet tabs yourself. **Freshness note (updated 2026-09-01)**: the standalone hourly automation was retired, so this report is now only as fresh as the most recent 4x-daily run (09:01/13:01/17:01/21:01 SGT) — the 1H/4H reading this skill picks up may be up to ~4 hours old, or up to ~12 hours old across the overnight 21:01→09:01 gap, not within the last hour as before.
- **Weekly TAT state**: there is no Weekly alerts tab/feed in the Google Sheet (only H1, 4H, and Daily) — this is a real, permanent data-source gap, not something to fetch from the sheet. Instead, read the symbol's *current* Weekly-chart TAT indicator state directly from TradingView, the same live on-chart-read technique CLAUDE.md's "Continuous Trade Monitoring & Execution Protocol" already documents for other timeframes (`data_get_pine_labels`/`data_get_study_values` after setting the chart to Weekly resolution) — this gives the CURRENT weekly bias, which is all the invalidation check in §2 step 3 needs; no historical weekly alert log is required.
- **Screenshot infrastructure**: `scripts/tv_session.sh` (session start/stop, batches everything into one TradingView session per run — see the Batch TradingView Session Rule in `CLAUDE.md`) and `scripts/capture_tv_chart.sh <SYMBOL> D <OUTPUT_NAME>` (Daily timeframe, always). The Weekly-state read above should happen in the *same* batched TradingView session as the screenshot work, not a separate session.

---

## ⚡ 2. Execution Protocol

Runs once per day, scheduled after the Daily Brief (which produces the day's `tat_analysis` H1/4H report content this skill reads for confluence) and before the day's first 1H+4H combined TAT review (09:01 SGT).

0. **Load state**: read `scripts/daily_signal_watches.json` in full. If it doesn't exist, something is wrong — do not silently recreate it from scratch (same discipline as `wiki/log.md`'s own append-only convention); stop and flag it.

1. **Detect new signals**: run `python3 scripts/binni_alert_analysis.py --timeframe DAILY`. For each alert row returned, check whether an entry already exists in `watches` with the same `(symbol, signal_date, signal_name)` — if yes, it's already tracked, skip. If no, it's a new signal:
   - Resolve `watch_days` = `config.symbol_overrides[symbol]` if present, else `config.default_watch_days`.
   - Note `direction` (Bullish/Bearish) and `signal_name` (e.g. `OptBear`, `LBull`) from the alert row.
   - Queue it for a Day-0 screenshot (step 2).

2. **Screenshot batch** (one `tv_session.sh start` / `stop` pair covering everything this run needs — new-signal Day-0 captures AND active-watch daily advancement, step 3, together; never open two separate TradingView sessions in the same run):
   - For each new signal from step 1: `capture_tv_chart.sh <SYMBOL> D <OUTPUT_NAME>`, then read the symbol's current price via the TradingView `state` read (same CDP session, no separate fetch) — this is the Day-0 `signal_price` and the first `days_tracked` entry.
   - For each entry in `watches` with `status: "active"`: capture that day's screenshot the same way, and read the current price.
   - Visually verify at least one capture per run with the Read tool per the wiki's Screenshot Verification Rule before trusting the batch.

3. **Advance active watches**: for every `status: "active"` entry (including ones just created in step 1, which start at day 0 and don't need advancing the same run):
   - Append a new `days_tracked` row: `{"day": N, "date": today, "price": <captured price>, "screenshot": <path>}`, where `N` is `len(days_tracked)` before this append (0-indexed, so the first advancement after Day 0 is day 1).
   - Compute `% move from signal_price` = `(current_price - signal_price) / signal_price * 100`, sign-aware. State whether the cumulative move is **with** or **against** the signaled direction (Bearish signal + price down = with; Bearish signal + price up = against).
   - **1H/4H direction check** — read today's `wiki/reports/tat_analysis/YYYY-MM-DD-tat-alert-report.md` (today's SGT date) for this symbol's current 1H and 4H alert state, then classify against the watch's `direction`:
     - **Same direction as the Daily signal → confluence trigger.** If not already recorded (dedupe by `(day, timeframe, signal_name, timestamp)`), append to `confluence_triggers`: `{"day": N, "timeframe": "1H"|"4H", "signal_name": ..., "timestamp": ...}`. This is the tactical "good day to consider entering" signal — the Daily bias gives direction, the fresh lower-timeframe alert gives timing. Flag prominently in the report.
     - **Opposite direction from the Daily signal → pullback.** If not already recorded (same dedupe key), append to `pullback_flags`: `{"day": N, "timeframe": "1H"|"4H", "signal_name": ..., "timestamp": ...}`. A single pullback print is *expected, normal noise against a real trend* — do not invalidate the watch on this alone. What matters next is whether it reverts (the elbow, below) or persists (real invalidation, below).
     - **Elbow check**: if this watch has at least one entry in `pullback_flags` from an *earlier* day (not today), and TODAY's 1H/4H reading has reverted back to the Daily-aligned direction, this is **the elbow** — the reversal back to trend after a pullback, arguably the single highest-probability re-entry signal this whole system produces. Append to `elbow_events`: `{"day": N, "timeframe": ..., "signal_name": ..., "timestamp": ..., "note": "Reversed back to Daily direction after the day-<M> pullback -- the elbow."}`. Flag this **more prominently than a plain confluence trigger** in the report and in bookkeeping — it's the specific pattern the user described: pullback, then watch for the reversal back to the Daily direction on 1H/4H, that reversal point is the elbow.
     - **Persistence check (real invalidation via lower timeframe)**: if the opposite-direction reading has now been the *prevailing* 1H/4H state for multiple consecutive daily checks (not a one-off blip — use judgment here, the same way this codebase already relies on LLM judgment for the Correction Discount Rule's "reference high" sanity check and the Retest Pullback classification in `tat-alert-analysis`, rather than a hard numeric threshold), treat this as a genuine trend change, not a pullback: set `invalidated: true`, `invalidated_reason`, `invalidated_day`, and set `status: "invalidated"` (a new status value alongside `"active"`/`"complete"` — keep capturing screenshots and tracking price for the remainder of the window even after invalidation, since the price data is still informative, just no longer validating the original thesis).
   - **Weekly invalidation check (highest priority, checked regardless of the 1H/4H state above)**: read this symbol's *current* Weekly-chart TAT state directly from TradingView (see §1 — same batched session, no separate fetch). If the Weekly direction is opposite the watch's Daily `direction`, this **overrides everything else**: set `invalidated: true`, `invalidated_reason: "Weekly TAT signal flipped to <direction>, overriding the Daily <direction> thesis"`, `invalidated_day: N`, `status: "invalidated"` — even if 1H/4H currently show confluence or an elbow. A Weekly-level reversal means the whole higher-timeframe premise the Daily signal depended on no longer holds.
   - If `len(days_tracked)` (after this append) reaches `watch_days + 1` (i.e. day 0 through day `watch_days` all captured) **and the watch was never invalidated**, mark `status: "complete"`. An already-`"invalidated"` watch stays `"invalidated"` at the end of its window rather than flipping to `"complete"` — invalidation is a terminal, more specific outcome.
   - Write the updated state back to `scripts/daily_signal_watches.json` (the whole file, not a partial patch — same discipline as any other JSON state file in this repo).

4. **Report per signal**: `wiki/reports/tat_analysis/daily-signals/<signal_date>-<SYMBOL>-daily-signal.md`, one file per watch, created on Day 0 and appended to on every subsequent advancement — same same-signal-append convention used everywhere else in this wiki (H1, 4H, equity-news all append rather than overwrite). Structure:
   - Title: `# 📅 Daily Signal Watch — [[SYMBOL]] (Bearish/Bullish) — Signal Date`.
   - Table of Contents (per the TOC Maintenance Protocol below — build it last, regenerate on every append).
   - `## 📌 Signal` — signal name, direction, signal-day price, watch length (`watch_days`, and whether it's a symbol-override or the default).
   - `## 📸 Day 0` — screenshot embed + price. Then one `## 📸 Day N` section per subsequent advancement, each with: screenshot embed, price, % move from signal price, with/against verdict, the day's 1H/4H reading, and — depending on what happened — one of:
     - `🎯 Confluence trigger: 1H/4H <signal> fired <time> — same direction as this Daily signal.`
     - `⚠️ Pullback: 1H/4H <signal> fired <time> — opposite direction; watching for the elbow (reversal back to Daily direction).`
     - `💪 Elbow: 1H/4H <signal> fired <time> — reversed back to the Daily direction after the day-<M> pullback. Highest-probability re-entry signal in this window so far.`
     - `🚫 INVALIDATED: <invalidated_reason>` (only on the day invalidation actually triggers — subsequent days should still note the watch remains invalidated, but don't repeat the full reasoning every day).
     - If none of the above, plainly state no notable 1H/4H/Weekly development this day.
   - On completion or invalidation (`status` flips to `"complete"` or `"invalidated"` this run): `## 🏁 Final Verdict` — net % move over the full window, validated/invalidated against the signal direction, a summary list of every confluence trigger and elbow event that fired during the whole window (or "none fired" if empty), and — if invalidated — the exact reason and the day it happened.

5. **TOC Maintenance Protocol**: identical convention to `tat-alert-analysis` and `equity-news-finder` — wrap in `<!-- TOC:START -->...<!-- TOC:END -->`, `[[#Exact Heading Text]]` Obsidian wikilinks (verbatim, no slugs), regenerate on every append, never nest a `[[SYMBOL]]` wikilink inside a `## ` heading line.

6. **Bookkeeping**: log via `scripts/append_log.py` (one entry per run, summarizing new watches opened, watches advanced, any confluence triggers/pullbacks/elbows found, and any watches completed or invalidated this run with their verdict/reason). Add a `wiki/index.md` entry for each *newly created* report file (not on every append — same "one entry per page" convention as the rest of the index). Update `wiki/hot.md` with any newly-started, newly-completed, or newly-invalidated watches — **rank findings by actionability: an elbow event first, then a fresh confluence trigger, then a new invalidation, then a plain pullback flag, then routine day-N advancement** — surface the most actionable ones prominently even if a routine day also happened this run.

---

## 🧭 3. Notes on Interpretation

- "14 days" means Day 0 (signal day) through Day 14 inclusive — 15 total data points per watch by default (or `watch_days + 1` for an overridden pair).
- Multiple concurrent watches on the same symbol are expected and correct (e.g. a second Daily Bearish signal on `EURUSD` while an earlier Bullish one is still mid-tracking) — they're independent entries keyed by `(symbol, signal_date)`, never merged or deduplicated by symbol alone.
- This skill never touches `config` — only `config.symbol_overrides` is read (to resolve a new watch's `watch_days`), never written. If the user wants to change future default behavior, they edit the JSON file directly.
- **The pullback → elbow pattern, explained**: a Daily signal gives the higher-timeframe bias/direction. A 1H or 4H print *against* that direction is not a reason to doubt the Daily thesis by itself — trends pull back against themselves constantly, that's normal. What actually matters is what happens *after* the pullback: if the lower timeframe reverses back to align with the Daily direction, that reversal point is **the elbow** — the highest-probability moment to act on the original Daily thesis, because it confirms the pullback was noise, not a real reversal. If instead the lower timeframe *stays* opposite the Daily direction across multiple checks (a persistent state change, not a blip), that's the real signal the Daily thesis itself is no longer valid — invalidate the watch.
- **Why Weekly overrides everything**: the Daily signal's own validity depends on the higher-timeframe (Weekly) trend still being intact. If the Weekly TAT state flips against the Daily direction, the entire premise the Daily signal was built on has changed — a same-direction 1H/4H confluence trigger or even an elbow event happening on a lower timeframe doesn't matter if the timeframe above the Daily signal itself has already reversed. Check Weekly state every advancement, not just at watch creation, since it can flip mid-window.
- `"invalidated"` is a distinct terminal status from `"complete"` — a watch can still run its full 14-day window after invalidation (the price data stays informative), but it should never silently flip back to reading as a clean `"complete"` validated thesis once invalidated.

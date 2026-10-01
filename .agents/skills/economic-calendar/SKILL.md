---
name: economic-calendar
description: Pulls strictly high-impact (Red Folder events only) from Forex Factory calendar and TradingView API for both This Week and Next Week, formatted in SGT. Also runs the Macro Analysis Specialist persona, which maintains a running Hawkish/Dovish/Neutral tally for the 8 major central banks and flags Divergence Gap / Neutral Hold alerts.
---

# Economic Calendar Skill

This skill tracks weekly high-impact economic news releases (strictly **Red Folder events only**) from Forex Factory and TradingView, formatted in Singapore Time (SGT), maintaining schedule tables for both **This Week** and **Next Week**. It also drives the **Macro Analysis Specialist** persona described below, which turns those Red Folder events (and any primary-source central bank statements the user shares) into a maintained central bank policy tally.

## Red Folder Criteria & Filtering Rules

The skill enforces a strict Forex Factory style Red Folder focus across major currencies (`USD`, `EUR`, `GBP`, `JPY`, `AUD`, `NZD`, `CAD`, `CHF`, `CNY`):

1. **Central Bank Rate Decisions & Policy**:
   - Rate decisions (Fed, ECB, BoE, BoJ, RBA, RBNZ, BoC, SNB)
   - Monetary Policy Statements, Summary, Assessment, and Press Conferences
   - FOMC / Central Bank Meeting Minutes
2. **Inflation & Price Indices**:
   - CPI m/m, CPI y/y, Core CPI, Trimmed Mean CPI, CPI q/q
   - Core PCE Price Index
   - Eurozone (`EU`) aggregate and Germany (`DE`) Flash CPI
3. **Employment & Labor Market**:
   - Non-Farm Payrolls (NFP), Employment Change, Unemployment Rate
   - Average Hourly Earnings, Claimant Count Change
4. **Economic Growth**:
   - US Advance GDP / GDP Growth Rate QoQ
   - Eurozone (`EU`) aggregate and Germany (`DE`) Flash GDP
   - UK, Japan, Canada, Australia, NZ GDP
5. **Retail Sales & Primary PMIs**:
   - Retail Sales m/m, Core Retail Sales m/m
   - ISM Manufacturing & Services PMIs
   - Flash Manufacturing & Services PMIs
   - China NBS Manufacturing & Caixin PMIs

### Exclusions (Non-Red Folder Events)
The skill explicitly filters out medium/low impact indicators including:
- Ifo Business Climate & Consumer Confidence / Sentiment indices (GfK, JPY Consumer Confidence)
- Durable Goods Orders, Personal Income, Personal Spending
- Sub-country regional European releases (France, Spain, Italy) when separate from aggregate Eurozone / German releases
- Housing Starts, Building Permits, Trade Balance, Wholesale Inventories

## Setup & Execution

1. **Execution**: The scraper script pulls from the Forex Factory feed (This Week) and TradingView API (Next Week / fallback), applying strict Red Folder filters. It **fully rewrites** both tables on every run.
2. **Weekly full-pull schedule**: `com.chriseah.wikitrades.econcalendar-weekly` (launchd LaunchAgent, `~/Library/LaunchAgents/`) runs `pull_economic_calendar.py` directly every Sunday at 17:00 SGT (`StartCalendarInterval` Weekday 0 / Hour 17 / Minute 0). Plain `python3`, no Claude session — the pull is fully mechanical. Logs: `~/Library/Logs/wiki-trades-econcalendar-weekly.{log,err.log}`.
3. **Outputs**:
   - Economic Calendar note: `wiki/notes/economic-calendar.md` — each row carries Forecast, Previous, and **Actual** (populated once an event has genuinely released; blank/`—` beforehand, which is normal for anything still upcoming).

## Actual Auto-Refresh (added 2026-10-01)

Between weekly full-pulls, `refresh_actuals.py` keeps the **Actual** column current without waiting for the next Sunday rewrite:

- **Mechanism**: `com.chriseah.wikitrades.econcalendar-actuals` (launchd LaunchAgent, `StartInterval` 120s) runs `python3 .agents/skills/economic-calendar/scripts/refresh_actuals.py` every 2 minutes, unconditionally — pure Python, no Claude session, so the 2-minute cadence costs nothing but a local file parse on the (common) cycles where nothing is due. Logs: `~/Library/Logs/wiki-trades-econcalendar-actuals.{log,err.log}`.
- **Timetable**: on every run it reparses `wiki/notes/economic-calendar.md`'s This Week / Next Week tables and rebuilds a rolling timetable in `actual_watch_state.json` (next to the script) — one entry per still-blank, data-bearing Red Folder row (events with no Forecast/Previous at all, e.g. "X Speaks" or a press conference, are never watched — they never get a numeric Actual). Entries older than 10 days and no longer present in the note are pruned. This is the "note of the next event and subsequent events" the note stays the single source of truth; the state file only remembers what's already been checked.
- **Trigger**: an entry becomes due once `now >= event time + 3 minutes` (`GRACE_MINUTES`). When due, the script re-fetches the Forex Factory feed (same one `pull_economic_calendar.py` uses) once for the whole run, batching all due entries, with a per-date TradingView range fetch as a secondary fallback. One fetch per run covers every due entry, not one fetch per event.
- **Patch, not rewrite**: a match found patches **only that row's** Actual cell via an exact string replace of the row's markdown line — the rest of the file (and any other in-flight edits) is untouched. It then appends one `wiki/log.md` line via `append_log.py` listing everything patched that run. No index/hot-cache rewrite — this is a field refresh, not an ingest.
- **Giving up**: after `MAX_ATTEMPTS` (20, ≈40 minutes of retrying at the 2-minute cadence) with no Actual found, the entry is marked `gave_up` and stops being retried — bounds how hard this hammers Forex Factory's feed for an event whose Actual never posts there (rate-limit note below).
- **Rate-limit note**: Forex Factory's feed (`nfs.faireconomy.media`) 429s under heavy/bursty polling. The script already fetches at most once per run and only when something is due, and fails a given cycle silently (prints a warning, retries next cycle) rather than crashing — but don't add more frequent pollers against the same endpoint without widening this margin.
- **Feeds this**: `scripts/generate_daily_brief.py`'s Central Bank Tally Reminders already gate on the Actual field being populated — this refresher is what makes that gate fire promptly (minutes, not until next Sunday) instead of going stale.

## CLI Commands

To manually trigger a full calendar rewrite:
```bash
python3 .agents/skills/economic-calendar/scripts/pull_economic_calendar.py
```

To manually run one Actual auto-refresh pass (normally driven by the launchd job above):
```bash
python3 .agents/skills/economic-calendar/scripts/refresh_actuals.py
```

## Macro Analysis Specialist Persona

When discussing a Red Folder event, a central bank, or a currency pair's macro backdrop, act as a **Macro Analysis Specialist** — focused on currency markets and central bank policy, maintaining the user's trade journal and providing data-driven updates.

**Purpose:**
- Maintain the organized **Running Tally** below for each major central bank (Fed, ECB, BoE, BoJ, RBA, RBNZ, SNB, BoC): Hawkish, Dovish, or Neutral.
- Track policy shifts immediately following Red Folder events.
- Monitor and alert on **Divergence Gaps** and **Neutral Holds** between central banks.
- Provide data-driven insight into the macro environment to support trading decisions.

**Behaviors:**
1. **Trade journaling and tallying** — upon a Red Folder event (CPI, NFP, an interest rate decision, a statement, a press conference, minutes) for a bank tracked in the Current Stances table, prompt the user to confirm that bank's resulting stance rather than assuming it; keep the tally in the structured table/bullet format in `wiki/notes/central-bank-tally.md`; track changes over time via that note's Recent Stance Changes log.
2. **Alerting and identification** — after every stance update, re-check the full Current Stances table for new or resolved Divergence Gaps and Neutral Holds (see below), and give a brief analysis of which specific currency pairs are affected and why (link the economic indicator — employment, inflation, growth — to the policy shift).
3. **Communication style** — use professional financial terminology (quantitative easing, transitory inflation, yield curve, etc.); keep responses concise and data-first; show your reasoning and do not assume a stance from ambiguous data — ask a clarifying question instead; end each response in this mode with a question about whether the user wants to adjust the journal or look at a specific currency pair.

## Central Bank Policy Tally

The tally lives at `wiki/notes/central-bank-tally.md` — a **living note**, rewritten in place (not a dated append-log): it always reflects the *current* stance per bank, with a trimmed recent-changes log for trajectory, mirroring `wiki/notes/currency-strength.md`'s pattern.

**Stance labels:** `Hawkish`, `Dovish`, `Neutral` (optionally qualified, e.g. `Hawkish Hold`, `Dovish`, `Neutral → Hawkish` when a pending shift is being signaled).

**Update procedure**, on every Red Folder central-bank event or ingested statement (see Source Pages below):
1. Confirm the resulting stance with the user, citing the specific data point that justified it (e.g. "Core CPI m/m 0.4% vs 0.2% forecast" or a quote from an ingested statement).
2. Update that bank's row in the `## Current Stances` table (`Stance`, `Last Changed`, `Trigger Event` — cite the source: a calendar row, or `(see [Source Title](../sources/source-slug.md))` per AGENTS.md's citation style when a primary-source statement was ingested).
3. Prepend a bullet to `## Recent Stance Changes`; trim the list to the last ~10 entries.
4. Re-evaluate `## Active Divergence Gaps` (see below) and update it.
5. Bump the note's `updated:` frontmatter date; register the change via `append_log.py`.

## Central Bank Source Pages

Official primary-source statement pages, ingested when the user shares a URL or asks to check for a new statement — these carry the actual policy language a stance judgment should be based on, not just calendar metadata:

| Bank | Official Statement Page |
| :--- | :--- |
| RBNZ | https://www.rbnz.govt.nz/monetary-policy/monetary-policy-statement/monetary-policy-statement-filtered-listing-page |
| BoJ | https://www.boj.or.jp/en/mopo/mpmsche_minu/minu_2026/index.htm (Monetary Policy Meeting minutes listing — update the year segment each January) |
| Fed | https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (FOMC meeting calendar — links to each meeting's statement/minutes) |
| ECB | https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html (Governing Council decisions index — navigate via the press-conference index for the dated decision URL) |
| RBA | https://www.rba.gov.au/publications/smp/ (quarterly Statement on Monetary Policy — outlook document accompanying Feb/May/Aug/Nov decisions, not a standalone decision press release) |
| BoE | https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/monetary-policy-summary-and-minutes (listing is JS-rendered — needs ego-browser, plain WebFetch only returns the page shell) |
| SNB | https://www.snb.ch/en/the-snb/mandates-goals/monetary-policy/decisions (quarterly assessments — Mar/Jun/Sep/Dec) |
| BoC | https://www.bankofcanada.ca/publications/mpr/ (quarterly Monetary Policy Report — check the Bank's "Policy interest rate" page too, since standalone rate-announcement press releases between MPRs are often more current) |

All 8 banks' official source pages are now on file.

**Ingestion procedure:**
1. Fetch the page and identify the latest published Monetary Policy Statement / decision statement.
2. Create a normal source-summary page under `wiki/sources/` (e.g. `wiki/sources/rbnz-mps-<date>.md`) following AGENTS.md's **Source summary** page structure exactly — one-line summary, key claims with citations, evidence quality, links to existing wiki pages, notable quotes sparingly, open questions.
3. Register it with `update_index.py` (category `sources`) and `append_log.py`.
4. Feed the extracted stance into the **Central Bank Policy Tally** update procedure above, citing the new source page.
5. If the affected currency already has an entity page (e.g. `wiki/entities/nzdusd.md`), update it in place per AGENTS.md's cross-reference-aggressively rule rather than leaving the connection only in the source page.

## Market-Implied Rate Probability Tools

Unlike the Source Pages above (a bank's own after-the-fact statement), these tools show the market's *forward-looking* probability of a bank's next move — useful context going into a Fed decision rather than after one.

| Bank | Tool | Notes |
| :--- | :--- | :--- |
| Fed | [CME FedWatch Tool](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) | Derives implied Fed Funds rate-hike/cut/hold probabilities from 30-Day Fed Funds futures pricing. Page is JS-rendered — needs ego-browser, plain WebFetch only returns the page shell (same caveat as BoE above). |

Check it ahead of a Fed FOMC meeting (see `central-bank-tally.md`'s `## Next Scheduled Updates` for the date) as supporting context for the post-meeting stance call — it doesn't replace reading the actual statement, but a probability that has swung hard into one outcome (e.g. >90% priced for a hike) is a useful sanity check against the eventual decision, and a live read on how "priced in" the outcome already is when discussing [[EURUSD]]/[[USDJPY]]/DXY reaction risk. Does not drive a stance update on its own — the update procedure above still requires the actual decision or statement.

## Divergence Gap & Neutral Hold Alerts

- **Divergence Gap** — one central bank sits Hawkish while another sits Dovish. Name the specific pairs affected (e.g. Fed Hawkish + ECB Dovish → `[[EURUSD]]` downside bias; BoJ Hawkish + Fed Dovish → `[[USDJPY]]` downside bias), using AGENTS.md's currency-nickname translation and instrument-formatting rules (no slashes, double-bracket wrapped).
- **Neutral Hold** — a bank remains on pause longer than the market anticipated, or incoming data suggests a pending shift away from Neutral. Flag it and explain the "why" (which indicator is pointing toward a shift).
- Re-run this check against the full Current Stances table after every tally update, and record the result in `## Active Divergence Gaps`.

## Central Bank Update Cadence

Central bank decisions happen on known, infrequent schedules (roughly every 6–8 weeks). Checking a bank's official source page before it has actually published anything new wastes a fetch (and, for BoE/RBNZ, a full ego-browser session) for nothing — so treat re-ingestion as schedule-gated, not a daily habit:

1. **Before fetching any bank's official source page** (the full statement/minutes ingestion in the Source Pages table above), check `wiki/notes/central-bank-tally.md`'s `## Next Scheduled Updates` table for that bank. If today is before the listed date, skip the fetch — nothing new exists yet.
2. **The authoritative "go ingest now" signal** is the Daily Brief's `## 🏦 Central Bank Tally Reminders` section (see Daily Brief Integration below) actually firing for that bank — which only happens once real **Actual** data has posted for a matching policy event in the economic calendar. Don't proactively re-check a bank's site on a hunch or because the scheduled date "feels close."
3. **After completing a fresh ingestion**, update that bank's row in `## Next Scheduled Updates` too — pull the next date from `economic-calendar.md`'s Next Week table if it's already within the 2-week window, otherwise do a cheap, date-only fetch of the bank's own official meeting calendar (not a full statement read).

## Daily Brief Integration

`scripts/generate_daily_brief.py` flags **staleness**, not stance: on each run it checks whether any bank had a Red Folder policy event (rate decision/statement/press conference/minutes) with a populated **Actual** value today per `wiki/notes/economic-calendar.md` — i.e. the event has genuinely released, not merely that today matches its scheduled date — while that bank's `Last Changed` date in `central-bank-tally.md` still predates today, meaning the conversational tally update was missed. It surfaces this as a `## 🏦 Central Bank Tally Reminders` section in the Daily Brief; it never writes a stance itself, since that judgment requires interpretation. This Actual-gated check is also what backs the Central Bank Update Cadence rule above — it's the one signal precise enough to trust over blindly re-checking on the scheduled date.

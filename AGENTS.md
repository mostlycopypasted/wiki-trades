---
schema_version: 2
---

# Trading Wiki

> A personal LLM-managed wiki using the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Maintained with the `llm-wiki-manager` skill.
> The LLM (Claude) owns all writing in `wiki/`. The user owns `raw/`. This file is the schema.
> `schema_version` tracks the structural conventions this wiki follows; `migrate_wiki.py` uses it to upgrade the wiki when the skill's conventions change. Do not edit by hand.

## Purpose

This wiki serves as a systematic knowledge base for proprietary trading methodologies, specifically tracking the TAT and Wash and Rinse systems. It acts as the LLM rulebook to rigidly enforce technical definitions, instrument naming conventions, and structural ingest formats for all market sessions and reviews.

## Layers

- `raw/` — immutable sources, user-curated. Read but never modify.
- `wiki/` — LLM-managed pages. Owned by Claude. The user reads, doesn't write.
- `AGENTS.md` (this file) — schema. Co-evolved with the user as conventions emerge.

## Structural files

Always in `wiki/` root — maintained by the LLM, never by hand:

- `wiki/index.md` — content catalog by category; updated by `scripts/update_index.py` on every ingest.
- `wiki/log.md` — append-only operation log; updated by `scripts/append_log.py` on every ingest/query/lint.
- `wiki/hot.md` — ~500-word hot cache (vault state, latest ingests, open items, tag inventory); **rewritten entirely** after every ingest.

## Categories

Default layout. Adjust as the wiki grows.

- `wiki/sources/` — one summary page per ingested source.
- `wiki/entities/` — people, organizations, products, forex pairs.
- `wiki/concepts/` — ideas, theories, terms-of-art, frameworks, wash and rinse, support and resistance.
- `wiki/notes/` — anything that doesn't fit a category yet, plus filed-back query answers, trade ideas.
- `wiki/reports/` — auto-generated reports (lint, audit, 1H/4H/3TF TAT analysis in `wiki/reports/tat_analysis/`, daily briefs in `wiki/reports/daily_brief/`, equity news scans in `wiki/reports/equitynews/`, and market sentiment scans in `wiki/reports/market-sentiment/`), dated. Daily Signals snapshots live in `wiki/reports/daily-signals/` (`YYYY-MM-DD_Daily_Signals.md`); the older per-watch files under `wiki/reports/tat_analysis/daily-signals/` are frozen historical artifacts from the retired v2 Daily Signal Tracker and are never written to again. Scripts write the mechanical data skeleton; some report types (TAT analysis, market sentiment) additionally require the LLM to write an interpretive narrative section directly into the file per that skill's instructions — see the **Market Sentiment Report Narrative Rule** below.

- `wiki/images/` — captured chart screenshots, diagrams, and visual trade execution media.

## Conventions

- **Slugs:** lowercase-with-hyphens. `eurusd.md`, not `EURUSD.md`.
- **Source filenames in `raw/`:** `YYYY-MM-DD-session-title.ext` (e.g., `2026-06-22-ahh-session.md`).
- **Instrument Naming:** Instruments must be written without slashes (e.g., `EURUSD`), crypto pairs must end with USD (e.g., `BTCUSD`), and all instruments must be wrapped in double square brackets when referenced in prose, tables, and lists (e.g., `[[EURUSD]]`). **Strict syntax exception:** NEVER put `[[...]]` wikilinks, nested brackets `[...]`, or backticks inside Markdown image alt text (`![alt text](path)`) or Markdown heading anchors (`## ...`). Nested brackets break CommonMark and Obsidian image rendering (`![... [[]] ...]` fails to parse as an image and renders as broken raw text). In image alt text and headings, use plain ticker text without brackets: e.g. `![SK Hynix Inc. Daily Chart](../../images/...)` or `![D05.SI Daily Chart](../../images/...)`.
- **Proprietary Color Coding & Level Definitions:**
  - *Red & Orange lines/labels* = Resistance levels.
  - *Blue & Green lines/labels* = Support levels.
  - *Magenta lines* = Buy setup wash lines.
  - *Green lines* = Sell setup wash lines.
  - *Orange lines* = Retracement/turning points.
  - *Wash Lines* = `Day Buy` (Daily Buy Wash Line), `Day Sell` (Daily Sell Wash Line), `Wk Buy` (Weekly Buy Wash Line), and `Wk Sell` (Weekly Sell Wash Line).
- **Technical Definitions:**
  - *TAT levels* = Horizontal breakout/retracement support and resistance. Usually prefixed with **`MajD`** (Major Daily Level) or **`MinD`** (Minor Daily Level) followed by price, level type, and timeframe suffix:
    - **First Retracement**: `MajD/MinD <Price> FiRet m15/h1/h4/D/W/M` (15m, 1h, 4h, Daily, Weekly, Monthly — e.g. `MajD 1.91058 FiRet h1`, `MajD 1.91058 FiRet h4`, `MajD 1.91058 FiRet D`).
    - **Support / Resistance**: `MajD/MinD <Price> Sup/Res m15/h1/h4/D/W` (15m, 1h, 4h, Daily, Weekly — e.g. `MinD 1.91009 Sup h1`, `MajD 1.90636 Res h1`).
    - **Take Profit**: `TP : <Price>` (e.g. `TP : 1.64055`).
  - *TAT Alerts* = On-chart TAT signal labels indicating trend reversal or continuation:
    - **Bullish**: `OptBull` (Optimal Bull), `LBull` (Large Bull), `SBull` (Small Bull).
    - **Bearish**: `OptBear` (Optimal Bear), `LBear` (Large Bear), `SBear` (Small Bear).
  - *"1+1 Confirmation"* = Confluence of price closing across a horizontal level AND crossing the 20/21 EMA.
  - *Weekly Signal Close Times* = The Weekly TAT signal for a symbol is generated/finalized at that symbol's **last trading session close of the week**, not a uniform calendar boundary:
    - **Forex & US Stocks**: Saturday 05:00 SGT (= Friday NY close).
    - **Singapore & Hong Kong Stocks**: Friday 17:00 SGT (SGX/HKEX local close).
    - **Crypto**: Monday 09:00 SGT (weekly bar rollover, since crypto trades 24/7 with no natural "last session").
    - When labeling a Weekly TAT signal by week number (e.g. in `wiki/reports/weekly_brief/`), attribute it to the week whose close (per the asset-class times above) actually produced that signal.
- **Wiki links:** standard markdown, relative paths. `[Title](../entities/title.md)`.
- **Citation style:** in-line as `(see [Source Title](../sources/source-slug.md))`.

## Tag policy

- Max **4 tags per page**. A tag must apply to **2+ pages** to enter frontmatter — single-use keywords belong in the page body, not in tags.
- Canonical tag list (the only allowed frontmatter tags; extend deliberately, merge synonyms):
  <!-- e.g.: setup, playbook, api, platform, reference, tutorial -->
- New tag = conscious decision: add it here first, then use it. `lint_wiki.py` flags single-use tags and over-tagged pages.

## Hub pages

- A topic cluster with **3+ pages** elects its most encompassing page as the **hub** (a normal wiki page, not a folder — Obsidian calls this a MOC).
- The hub carries a `## Pages in this cluster` section: one line per member page with a short description.
- Mark hubs in the index with `★`. Query navigation: short index → hub → page.
- Fewer than 3 pages = no hub yet; promote when the cluster grows.

## Index rule

- **One entry per page**, grouped by theme/category — a page never appears under multiple headings.
- Entry format: `- [Title](path.md) — one-line summary #tag` (`★` after the link marks a hub).

## Lint exceptions

<!-- Findings the user has consciously decided to ignore. lint_wiki.py output on
     these files/slugs is expected and should not be "fixed". Example:
- raw/general/*-sitemap.md — large reference dumps, scanned only when their page updates
-->

*None yet.*

## External Wiki (optional)

<!-- Fill in if this project wiki connects to a long-lived global wiki (personal
     knowledge base, Obsidian vault, second brain). Required for any multi-wiki
     operation. The agent reads this section on session start and routes writes
     accordingly. See references/multi-wiki-routing.md for the four canonical
     scenarios (write-to-global, pull-from-global, promote, dual-lint).

Global knowledge base path: ~/Documents/obsidian/
(Change to your actual path, or delete this whole section if you only use one wiki.)

Routing rules:
- Project-specific code decisions, architecture, bugs, API contracts → this wiki
- General concepts, frameworks, patterns reusable across projects → global wiki
- Source summaries for internal/project docs → this wiki
- Source summaries for books, papers, general articles → global wiki
- When the user says "global wiki", "obsidian", "my notes" → use global path
- When routing is ambiguous → ask one clarifying question before writing
- Scripts always need `--path` pointing to the right wiki root

Cross-wiki link convention:
- Use absolute paths: ~/Documents/obsidian/wiki/concepts/foo.md
- Never use relative paths that cross wiki boundaries (they break under directory
  moves and git history rewrites)
-->


## Page structure

### Source summary (`wiki/sources/<slug>.md`)

1. One-line summary at the top
2. Key claims (bullets, each with location citation — page, timestamp, paragraph)
3. Evidence quality / methodology
4. How it relates to existing wiki pages (explicit links)
5. Notable quotes (sparingly)
6. Open questions

### Entity (`wiki/entities/<slug>.md`)

1. One-line description
2. Background
3. Key positions / contributions / events (each with source citation)
4. Disputes (when sources disagree)
5. Sources (list of source-summary pages cited)

### Concept (`wiki/concepts/<slug>.md`)

1. Definition (one or two sentences)
2. Origin
3. Key claims
4. Disputes
5. Related concepts (links)
6. Sources

## Bookkeeping discipline

Apply on every operation:

1. **Log every operation.** Use `scripts/append_log.py`. Format: `## [YYYY-MM-DD] action | title`.
2. **Update the index** for every new or substantially-updated page. Use `scripts/update_index.py`.
3. **Rewrite `wiki/hot.md` after every ingest.** Do not append — rewrite entirely. Update vault state, active knowledge (latest ingest at top), open work items, tag inventory.
4. **Cross-reference aggressively.** When ingesting a source about an entity that already has a page, update that page in place. Don't leave the connection in the source summary alone.
5. **Cite back to sources.** Every claim should be traceable to a specific source.
6. **Flag contradictions.** When new sources disagree with existing claims, add both with citations and note the conflict. Never silently overwrite.

## Workflow notes

- **Market Session Ingest Prompt & Template:** Whenever a "Weekly Review", "AHH Session", "TAW Pro", "TAR Session", or similar transcript is ingested, act as a trader looking for trading opportunities and extract:
  1. The list of instruments traded (forex, commodities, indices, crypto, or stocks).
  2. The Key Levels discussed (Support/Resistance/Wash Lines/TAT levels).
  3. The Direction of trade (Long/Short/Neutral).
  4. List these opportunities in **numbered bullet form**.
  5. Any technical trading rules emphasized must be added to the **bottom**.
- **Normalization & Formatting Rules:**
  - Remove slashes from forex, crypto, and commodities pairs: write `EURUSD`, not `EUR/USD`.
  - Crypto pairs MUST end with `USD`: `BTCUSD`, `ETHUSD`, `SOLUSD`.
  - Wrap all instruments in double square brackets: `[[EURUSD]]`, `[[BTCUSD]]`.
  - Standardize `tad`, `tat`, or `ted` to **TAT**.
  - Translate spoken currency nicknames: "Aussie" -> `AUD`, "Kiwi" -> `NZD`, "Sterling" or "Pound" -> `GBP`, "Yen" -> `JPY`, "Loonie" or "Cad" -> `CAD`, "Swissy" -> `CHF`.
- **Same-Day 1H Analysis Iteration Rule:** When running a 1H TAT analysis on a date that already has a report file for that same date (`wiki/reports/tat_analysis/YYYY-MM-DD-tat-alert-report.md`), do not overwrite or delete the previous run. Append a new timestamped iteration section (`## 🕒 Intraday Update Run — [HH:MM SGT]`) to the existing report and include an explicit **Differences & Changes Highlights** table comparing prices, bias shifts, TAT signals, and structural changes since the previous run.
- **5x-Daily 1H+4H Combined Review Rule (updated 2026-09-10 — added the 05:31 SGT slot; now the day's only scheduled TAT cadence):** At **05:31, 09:01, 13:01, 17:01, 21:01 SGT** — the day's five scheduled runs (the standalone hourly-only cadence was retired 2026-09-01; there is no hourly baseline anymore) — run a combined 1H+4H TAT signal review via `python3 scripts/binni_alert_analysis.py --timeframe H1_4H`. The 05:31 slot is offset 30 minutes past the Daily Brief / Morning Pipeline automation's 05:01 SGT start (rather than sharing that exact minute) to avoid the two automations racing on the same TradingView session and wiki bookkeeping files. The 1H fetch + narrative must fully resolve before the 4H fetch + narrative starts (the script enforces this internally; capture 1H's new-alert screenshots, then 4H's, never interleaved). If a report for today already exists, append an intraday section headed `## 🕒 Intraday Update Run — [HH:MM SGT] (1H + 4H Combined Review)`; if this is the first report of the day (typically the 05:31 run), start a fresh report with a top-level header instead (see the tat-alert-analysis skill's §4.5 for the exact format). Either way it must include the 4H cluster/theme narrative plus the 4H+1H confluence/retest classification (⭐⭐⭐ dual-alignment and retest-pullback buckets) alongside the normal 1H content, all within the same single daily report file — no separate 4H report file is created for these 5 runs. The standalone `--timeframe H1`, `--timeframe 4H`, and `--timeframe 3tf` modes remain available separately for ad hoc/on-demand use only.
- **Market Sentiment Report Narrative Rule:** `scripts/market_sentiment.py` (Apple Silicon original) / `scripts/market_sentiment_x86.py` (Intel fork — same logic, pinned to older transformers/numpy since torch has no wheels past 2.2.2 for x86_64 macOS; `generate_daily_brief.py` calls whichever matches the running machine) (see the `market-sentiment` skill) appends a run section to `wiki/reports/market-sentiment/YYYY-MM-DD-market-sentiment.md` on every invocation — same-day reruns (whether ad hoc single-instrument checks or the Daily Brief's own automatic call) append rather than overwrite, mirroring the Same-Day 1H Analysis Iteration Rule above. Each run section leads with a summary table (one row per instrument, columns `Instrument | Articles | Positive | Negative | Neutral | Summary`), with headline detail trimmed to the top 5 per instrument and tucked in a collapsible block below so the table stays the primary content. Every `Summary` cell starts as `_pending_`; immediately after every run (including runs triggered by `generate_daily_brief.py`), the agent MUST replace each instrument's `_pending_` cell with its own ~200-word prose summary of that instrument's news flow (single line, no `|` or line breaks) before considering the operation complete.

- **Central Bank Tally Rule (added 2026-09-12; updated 2026-09-13 — Actual-gated reminders + update-cadence discipline):** The `economic-calendar` skill also drives a **Macro Analysis Specialist** persona that maintains a living Hawkish/Dovish/Neutral stance tally for the 8 major central banks (Fed, ECB, BoE, BoJ, RBA, RBNZ, SNB, BoC) at `wiki/notes/central-bank-tally.md` (rewritten in place, like `currency-strength.md` — not a dated append-log). The tally updates conversationally: when a Red Folder central-bank event (rate decision, statement, press conference, minutes) is discussed, or when a primary-source monetary policy statement is ingested as a normal `wiki/sources/` summary page (official statement pages are listed in the skill's Central Bank Source Pages table — all 8 banks are now on file), confirm the resulting stance with the user, cite the specific triggering data point, and update the note's Current Stances row plus its trimmed (~10-entry) Recent Stance Changes log. After every update, re-check the full table for **Divergence Gaps** (one bank Hawkish while another is Dovish) and **Neutral Holds** (a bank on pause longer than the market expected, or with data pointing to a pending shift), naming the specific currency pairs affected. The note also carries a `## Next Scheduled Updates` table (one row per bank); check it *before* proactively re-fetching a bank's official source page and skip the fetch if today is before that date — central bank decisions are infrequent (every 6–8 weeks), so blind daily re-checks waste tool calls on nothing new. `wiki/notes/economic-calendar.md` (via `pull_economic_calendar.py`) now captures each event's real **Actual** value (from Forex Factory's/TradingView's `actual` field) alongside Forecast/Previous, not just the forecast. `scripts/generate_daily_brief.py` uses that Actual field as the precise trigger: it flags **staleness** (a `## 🏦 Central Bank Tally Reminders` section) only once a bank's Red Folder policy event has an Actual value populated (i.e. genuinely released, not merely dated today) while its tally row wasn't updated since — it only flags, it never writes a stance itself, since that judgment requires interpretation. This Actual-gated reminder, not the scheduled date alone, is the authoritative signal to go re-ingest a bank's full statement.
- **1H Analysis Header Timestamp Rule:** Whenever running a TAT analysis report or intraday iteration, include an explicit SGT timestamp in the main header title (e.g., `# 📈 TAT Alert Report — YYYY-MM-DD [HH:MM SGT]`) and all sub-headers so every scan run is precisely timestamped.
- **Explicit Per-Instrument Direction Rule in TAT Reports:** In all TAT Alert Analysis reports (1H, 4H, Daily, 3TF), narratives, and cluster summary tables, every instrument MUST explicitly specify its individual direction with clear visual indicators: `[[SYMBOL]] (🟢 Bull)` or `[[SYMBOL]] (🔴 Bear)` (or `[[SYMBOL]] (⚪ Neutral)`). In cluster summary tables, group and tag pairs explicitly (e.g., `[[CADCHF]] (🟢 Bull), [[USDCAD]] (🟢 Bull), [[EURCAD]] (🔴 Bear), [[NZDCAD]] (🔴 Bear), [[GBPCAD]] (🔴 Bear)`) so the exact direction of every single pair is immediately unambiguous and obvious to evaluate at a glance.
- **Timestamped Image Naming Standard:** ALL chart screenshots captured across ALL workflows MUST follow the standardized filename format for chronological sorting: `YYMMDD-HHMMSS_<symbol>_<tf>_chart.png` (e.g. `260731-142037_sgdjpy_4h_chart.png`). Reports MUST explicitly list all symbols firing new signals (with signal name, direction, and timestamp) and embed/link to their corresponding timestamped screenshot.
- **Batch TradingView Session Rule:** To prevent repeatedly opening and closing TradingView Desktop for each screenshot, analysis scripts, Daily Briefs, Weekly Reviews, and alert scans MUST launch TradingView ONCE at the start of a screenshot batch using `./scripts/tv_session.sh start`, execute `./scripts/capture_tv_chart.sh <SYMBOL> <TF> <OUTPUT_NAME>` for all required symbols during the open session, and close TradingView ONCE at the end of the batch using `./scripts/tv_session.sh stop` (which saves chart layout `Cmd+S`, requests graceful quit `osascript`, waits 3 seconds, checks active PIDs, and runs fallback `pkill -9`).
  - **Screenshot verification rule (added 2026-08-05, do not skip):** a script reporting "📸 Captured screenshot" is not proof the image is correct. Both `tv_session.sh` and `capture_tv_chart.sh` now self-mitigate two found failure modes — a symbol-search dialog race on cold sessions, and (the dominant cause) TradingView's window being occluded/backgrounded, which makes Chromium silently throttle canvas rendering while symbol labels and CDP `state` checks keep reporting success (`scripts/force_tv_visible.mjs` forces `Page.setWebLifecycleState({state:'active'})` to fix this without needing real OS window focus). These mitigations reduce the failure rate but are not proven bulletproof — **actually open at least one captured image per batch with the Read tool before filing a report that embeds it**, and open all of them if the batch is small enough to be practical. A blank/stale chart with a correctly-labeled symbol is the telltale sign if the mitigations ever fail again.

- **Active Trades Analysis Screenshot Rule:** Whenever running an Active Trades Review or analyzing active positions, the agent MUST run `./scripts/tv_session.sh start` once, `./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME> <OUTPUT_NAME>` for all active symbols, and `./scripts/tv_session.sh stop` once at the end, embedding images in the active trades report (`![<Symbol> 1H Chart Screenshot](../images/<symbol>_1h_chart.png)`).
- **New Alert Screenshot Capture Rule:** Whenever running a TAT Alert Analysis (1H, 4H, Daily, or 3TF) where **NEW alerts** are logged for specific instruments during the scan run, the agent MUST launch `./scripts/tv_session.sh start` once, execute `./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME> <OUTPUT_NAME>` for each new alert symbol, close with `./scripts/tv_session.sh stop`, and embed the captured chart screenshots under a dedicated `## 📸 New Alert Chart Screenshots` section in the report (`![<Symbol> Chart Screenshot](../images/<symbol>_<timeframe>_chart.png)`).
- **Daily Brief Screenshot Storage Rule:** All chart screenshots captured for Daily Brief reports MUST be captured using the batch TV session protocol (`tv_session.sh start`, `capture_tv_chart.sh`, `tv_session.sh stop`), saved directly in `wiki/images/`, and embedded in the Daily Brief report using relative path `../../images/<symbol>_<timeframe>_chart.png`.
- **Markdown Image Embed Syntax & Alt Text Cleanliness Rule:** All chart screenshots embedded in markdown (`![alt text](path)`) across all reports (TAT analysis, Daily Brief, Equity News, etc.) MUST use plain descriptive text in the alt text (e.g. `![<Symbol> <Timeframe> Chart Screenshot](../../images/<filename>.png)`). NEVER include double square brackets `[[...]]`, nested brackets `[...]`, backticks `` `...` ``, or HTML inside the alt text brackets `[...]`. CommonMark and Obsidian parsers treat nested brackets as link/embed boundaries, immediately breaking image rendering into raw text. Run `python3 scripts/lint_images.py --fix` after report generation if verifying embeds.

- **Daily Signals Report Rule (added 2026-09-23 — replaces the v2 Daily Signal Tracker):** The `daily-signal-tracker` skill (retitled **Daily Signals**, v3.0.0) runs **once daily** and is a *snapshot*, not a multi-day tracker. The Orca automation **"Daily Signals"** (`b64e9d36`) fires at **05:45 SGT Mon–Sat** — **05:01 SGT is the data-window reference, not the run time** (the forex Daily bar closes 05:00 and its alerts write at 05:01, defining which signals belong to a given day). The 05:45 slot is deliberately offset to clear the Daily Brief / Morning Pipeline (05:01) and the TAT Combined 1H+4H review (05:31), since all three drive the same TradingView session and this one captures ~45 charts. It reads three Daily-timeframe sources — **Forex** (`gid: 462165474`, tab `Forex D`), **TradingView Stocks** (`gid: 520189562`, tab `bats`), and **Yahoo Stocks** (`gid: 1875176436` `Bull Daily` + `gid: 1088333741` `Bear Daily`, always pulled together as the bull and bear halves of one source) — via `python3 scripts/scan_daily_signals.py`. **Daily timeframe only:** no Weekly state read, no 1H/4H confluence, and none of the retired confluence/pullback/elbow/invalidation classification. **Date window:** for a run on day `D`, Forex, `bats`, and US Yahoo rows are taken dated `D`; **SGX/HKEX rows are taken dated `D−1`**, because those exchanges close at 17:00 SGT — after that day's 05:01 run — so their signals are first visible the following morning. This offset is gap-free (the run on `D−1` was looking at `D−2`). Asian rows must state their `D−1` signal date explicitly in the report so the offset is never mistaken for stale data. `scripts/daily_signal_seen.json` holds the watermark and a 45-day dedupe ledger so weekends and missed runs backfill instead of dropping signals. One batched TradingView session captures **one Daily chart per unique instrument** (~45 per run; an instrument printing on two sources or under two signals shares a single chart), in sequential foreground chunks of ~5. Output goes to `wiki/reports/daily-signals/YYYY-MM-DD_Daily_Signals.md` with three sections (Forex / TradingView Stocks / Yahoo Stocks); same-day reruns **append** a `## 🕒 Intraday Update Run — [HH:MM SGT]` section rather than overwriting, mirroring the Same-Day 1H Analysis Iteration Rule.
- **Multi-Timeframe Context:** When a lower-timeframe entry setup is mentioned (e.g., H1 short), cross-reference and document the nearest higher-timeframe structural boundary (e.g., H4 support) for take-profit and stop-loss levels.



- **Entity Creation:** An instrument automatically earns an entity page in `wiki/entities/` the first time it is tracked, ensuring its key levels and bias are centrally logged.
- **Trading Technique Extraction:** During each ingestion, explicitly identify and document any trading techniques, methodologies, or rules discussed (e.g., "1+1 confirmation", gap-play, range consolidations, scalp triggers, options hedging, or market structure trend sequences). Update corresponding concept pages under `wiki/concepts/` (such as `tat.md` or `wash-and-rinse.md`) to incorporate these newly discussed techniques or adjustments.
- **Post-Ingest Deletion Protocol:** Deletion from Fireflies.ai cloud MUST only take place AFTER the entire ingestion process (source summary creation, entity/concept page updates, log appending, index updating, and hot cache rewriting) is fully completed and verified. Never auto-delete during fetch/ingest; always ask the user for explicit permission after ingestion is complete before executing cloud deletion.


## Tooling

- **Autonomous Access Protocol:** All trade reviews, chart scans, Google Sheet alert data fetching via Service Account credentials (`/Users/chriseah/tradingview-mcp/service_account.json`), TradingView MCP chart resets, quote extractions, Pine label re-reads, screenshot captures, and report generation MUST always be executed 100% autonomously without prompting for user confirmation or requiring approval.
- **Continuous Trade Monitoring & Execution Protocol:** Whenever monitoring active positions or evaluating trade setups, the agent MUST execute the following 3-step sequence on **every check** — TAT levels are dynamic and shift as price moves higher or lower:
  1. **Live Quote & Closed-Bar Precision**: Query exact 5-decimal Eightcap broker quotes (`quote_get` or scanner), aligning 1H, 4H, and Daily scans with 100% completed closed bars.
  2. **TradingView MCP Chart Reset & Scale Alignment**: Call `./scripts/capture_tv_chart.sh` or `chart_set_symbol` / `chart_set_timeframe` for the target symbol and timeframe, executing explicit chart view reset (`Alt+R` / `tv ui keyboard r --alt`) to center candles and price scale before reading indicators or taking screenshots.
  3. **On-Chart TAT Level & Wash Line Re-Read**: Query `data_get_pine_labels`, `data_get_pine_lines`, and `data_get_study_values` via TradingView MCP to read **current** on-chart labels — levels may have moved since the last check:
     - **TAT Levels**: `MajD/MinD <Price> FiRet m15/h1/h4/D/W/M`, `MajD/MinD <Price> Sup/Res m15/h1/h4/D/W`, and `TP : <Price>`.
     - **TAT Alerts**: `OptBull`, `LBull`, `SBull` (Bullish) | `OptBear`, `LBear`, `SBear` (Bearish).
     - **Wash Lines**: `Day Buy` (Daily Buy Wash Line), `Day Sell` (Daily Sell Wash Line), `Wk Buy` (Weekly Buy Wash Line), `Wk Sell` (Weekly Sell Wash Line).
- **Trading Analysis Skills & Automation:**
  - **TAT Alert Analysis Skill**: Use `python3 scripts/binni_alert_analysis.py --timeframe [H1|4H|DAILY|H1_4H|BULL_DAILY|BEAR_DAILY|3tf]` to pull live Google Sheet Telegram alerts across Daily (`gid: 462165474`), 4H (`gid: 1105950672`), H1 (`gid: 0`), **Bull Daily Stock Alerts** (`gid: 1875176436`, [Direct Tab Link](https://docs.google.com/spreadsheets/d/1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE/edit?gid=1875176436#gid=1875176436)), **Bear Daily Stock Alerts** (`gid: 1088333741`, [Direct Tab Link](https://docs.google.com/spreadsheets/d/1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE/edit?gid=1088333741#gid=1088333741)), and **TradingView Stocks** (tab `bats`, `gid: 520189562`, [Direct Tab Link](https://docs.google.com/spreadsheets/d/1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE/edit?gid=520189562#gid=520189562) — used by the `daily-signal-tracker` skill, not by `binni_alert_analysis.py`) tabs, executing Binni's cluster-and-theme analysis and 3-Timeframe synthesis. `H1_4H` runs the 1H analysis to completion, then the 4H analysis, then a 4H+1H confluence/retest review — combined into a single report; used for the 05:31/09:01/13:01/17:01/21:01 SGT runs (see the tat-alert-analysis skill's 5x-Daily Combined Review Rule).
- **Unattended Scheduling via Orca (added 2026-08-28, updated 2026-09-10)**: TAT alert analysis (the 5x-daily 1H+4H combined runs — the standalone hourly-only automation was retired 2026-09-01 at the user's request; TAT alert analysis no longer runs on an hourly baseline, only 5x/day at 05:31/09:01/13:01/17:01/21:01 SGT, each reviewing both 1H and 4H TAT signals together) and the Daily Brief / morning pipeline are driven unattended by Orca automations (`orca automations list` — "TAT Combined 1H+4H Review" for the 09:01/13:01/17:01/21:01 SGT slots, "TAT Combined 1H+4H Review — 05:31 AM Slot" as a separate automation for the 05:31 SGT slot (added 2026-09-10, kept as its own automation rather than folded into the first one because cron can't express a different minute for one hour within a single trigger; deliberately offset 30 minutes past Daily Brief's 05:01 SGT start to avoid the two automations racing on the same TradingView session and wiki bookkeeping files), and "Daily Brief / Morning Pipeline"), not by launchd + `claude -p` directly. Plain `--timeframe H1` (or `4H`) runs remain available but are manual/ad hoc only going forward. Each automation is pinned to the existing wiki-trades worktree (`--workspace-mode existing`, since a fresh Orca worktree would be missing the untracked `wiki/`/`raw/` directories — see the git-scope note below) and set to `--timezone Asia/Singapore`. A small `com.chriseah.wikitrades.orca-runtime` LaunchAgent (`~/Library/LaunchAgents/`, `RunAtLoad: true`, runs `orca open`) keeps Orca's runtime alive after each login, since nothing else relaunches it automatically. The equity-news scans and (until the Orca "Daily Brief" automation is validated on a real unattended morning run) the `com.chriseah.wikitrades.morningpipeline` launchd job remain on the original `claude -p --permission-mode bypassPermissions` path. **Orca's `--precheck` has a hard 600-second timeout** — `generate_daily_brief.py` alone typically takes 10–15 minutes, so that step lives inside the automation's `--prompt` (as an explicit, non-backgrounded Bash call) rather than in `--precheck`. Requires a managed Claude account added via `orca account add` (interactive login) before any of this runs unattended — check with `orca account list`.
  - **Short-Term Trading (D-R-H-R) Skill**: Use `python3 scripts/scan_drhr_setups.py` to cross-reference Daily TradingView brief scans with live H4 and H1 alerts for asymmetric 1:5+ R:R setups.
  - **Currency Strength (ZigZag Structure)**: `python3 scripts/generate_daily_brief.py` runs the full chain itself — a live `tv brief` scan (`~/tradingview-mcp`) → `scripts/build_daily_bias.py` (writes `~/tradingview-mcp/daily_brief/{date}.json` with per-symbol `structure`/`bias` from the Daily-chart ZigZag and TAT trend bar) → `scripts/tat_currency_strength.py` (aggregates per-currency scores from `structure` across the 8 majors, writes `wiki/notes/currency-strength.md`, `wiki/images/currency-strength-graph.svg`, and a deep-dive `wiki/reports/{date}-tat-currency-strength-report.md` with XAU/XAG and full-watchlist change-of-structure detail). Replaces the retired `currency-strength-tracker` skill (marketsmadeclear.com scrape).
  - **Daily Brief Timeframe Scope (added 2026-09-23):** `generate_daily_brief.py` does **not** read the Daily TAT alert sheet (`gid: 462165474`) — that timeframe belongs to the `daily-signal-tracker` (Daily Signals) skill, which runs at 05:45 SGT. The brief's alert synthesis is 4H + 1H only (`binni_alert_analysis.py --timeframe 3tf --no-daily`; the `--no-daily` flag makes `analyze_3tf_multi_timeframe()` emit a `4H + 1H Confluence & Retest Review` and renumber its sections). The brief's live `tv brief` scan is driven by `~/tradingview-mcp/forex_list.json` (not the 88-symbol `rules.json` superset) — forex_list.json is a complete drop-in rules file with the same schema, so the user's own curated list is the single source of truth for what the brief scans. The brief's Daily view comes from `scripts/watchlist_signals.py --capture`, which reuses the `~/tradingview-mcp/daily_brief/{date}.json` already written by `build_daily_bias.py` in the same run for signal state and batch-captures **one Daily chart screenshot per instrument** in `forex_list.json` (single TradingView session per the Batch Session Rule), rendering them as the **Daily Watchlist Charts** gallery — a heading, a signal/structure/bias caption and an embedded chart per instrument. This is the slowest step in the pipeline (~20 min for ~70 charts). Running the script without `--capture` emits a summary table instead, for ad hoc use (columns `# | Instrument | Signal | Direction | Structure | TAT Bias | Price`). TAT chart labels carry only text and price — **no timestamp** — so that table is standing signal state, never "signals that fired today". Plain `--timeframe 3tf` (Daily + 4H + 1H) remains available for ad hoc use. Because the scan and the snapshot now read the same file, adding an instrument to `forex_list.json` is enough for it to appear in the brief. A ticker the scan cannot resolve is called out in a `⚠️ No scan data for N watchlist entries` line rather than being silently dropped — note an unresolvable symbol still returns a record with a null quote, which `build_daily_bias.py` stores as price 0, so a zero price (not just an absent record) is what marks it as no-data. Instruments whose screenshot fails are likewise listed explicitly rather than embedded as a broken image.
- **Watchlist Files** (all in `~/tradingview-mcp/`):
  - `rules.json` — Master combined default watchlist for Daily & Weekly briefs (88 unique instruments across Forex, Commodities, Indices, Crypto, US & SG/HK Equities).
  - `forex_list.json` — Forex pairs, Commodities (Gold, Silver, Oil), Indices (NDQ100, SPX500, DXY, HSI, etc.) — 56 instruments.
  - `crypto_list.json` — Cryptocurrency pairs (BTCUSD, ETHUSD, SOLUSD, NEARUSD) — 8 instruments.
  - `us_stocks.json` — US equities (TSLA, NVDA, MSFT, META, AAPL, AMZN, GOOGL, CLSK, MSTR, RIOT, IBIT) — 13 instruments.
  - `sghk_stocks.json` — Singapore & Hong Kong stocks (SGX:SCY, SGX:D05, SGX:O39, SGX:U11, etc.) & HK/China Indices (HSI:HSI, HK50, HSTECH, CN50) — 15 instruments.
- Scripts in `scripts/` (capture_tv_chart.sh, init_wiki, append_log, update_index, lint_wiki, fetch_google_sheet, binni_alert_analysis, scan_drhr_setups). Always prefer the scripts to hand-editing structural files.
- `scripts/capture_tv_chart_egobrowser.sh` — optional, manual-only ego-browser (real Chromium/CDP) backup for chart screenshots when the TradingView MCP pipeline is slow; not part of any automated batch rule above and must be invoked explicitly.
- The wiki is a git repo; commit after substantive changes so rollback is easy.


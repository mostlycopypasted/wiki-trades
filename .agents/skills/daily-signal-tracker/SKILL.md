---
name: daily-signal-tracker
description: Daily Signals — a once-daily morning snapshot (Orca automation fires 05:45 SGT Mon–Sat; 05:01 SGT is the data-window reference, not the clock time) of every Daily-timeframe TAT signal across three sources (Forex D, TradingView Stocks/bats, and the Yahoo Bull+Bear stock lists), with a chart screenshot per instrument and a single dated report at wiki/reports/daily-signals/YYYY-MM-DD_Daily_Signals.md. Daily timeframe only — no Weekly state read, no 1H/4H confluence, no multi-day watch tracking. Asian (SGX/HKEX) stocks are taken from the previous calendar day because they close at 17:00 SGT, after the run. The Daily-timeframe counterpart to tat-alert-analysis (H1/4H, 5x-daily) and equity-news-finder (equity news).
license: MIT
metadata:
  author: AI Trading Team
  version: "3.0.0"
  tags:
    - google-sheets
    - alerts
    - tat
    - daily-timeframe
    - screenshot-snapshot
    - forex
    - equities
---

# Daily Signals Skill

Runs **once per day**. The Orca automation **"Daily Signals"** fires at **05:45 SGT, Mon–Sat** (`rrule: 45 5 * * 1-6`). **05:01 SGT is the data-window reference, not the run time** — the forex Daily bar closes 05:00 SGT and its alerts write at 05:01, which is what defines *which* signals belong to a given day. The run itself is deliberately offset to 05:45 to clear the Daily Brief / Morning Pipeline (05:01) and the TAT Combined 1H+4H review (05:31): all three drive the same TradingView session, and a ~45-chart batch racing either of them is the failure CLAUDE.md's Batch TradingView Session Rule exists to prevent.

Detects every new Daily-timeframe signal across the three sources below, screenshots each instrument's Daily chart once, and files a single dated report.

> **v3.0.0 (2026-09-23) replaced the v2 "Daily Signal Tracker".** v2 tracked one forex tab through a 14-day watch window driven by a Weekly / 1H / 4H classification engine (confluence → pullback → elbow → invalidation). That engine and the watch window are **gone**. This is a snapshot, not a tracker. The v2 state in `scripts/daily_signal_watches.json` (52 watches) and the per-watch reports in `wiki/reports/tat_analysis/daily-signals/` are **frozen historical artifacts** — read them for history, never write to them.

---

## 📋 1. Data Sources

All three live in the same Google Sheet (`1XQc0TFDvihNN7wSNBBJom5rh5W-D6msm24gaMTQ5DaE`) as `tat-alert-analysis`, registered in `scripts/fetch_google_sheet.py`:

| Source | gid | Real tab title | Fires | Key |
|---|---|---|---|---|
| **Forex** | `462165474` | `Forex D` | 05:00–05:01 SGT | `FOREX_D` |
| **TradingView Stocks** | `520189562` | `bats` | 04:01 SGT | `BATS` |
| **Yahoo Stocks** (bull half) | `1875176436` | `Bull Daily` | no time recorded | `BULL_DAILY` |
| **Yahoo Stocks** (bear half) | `1088333741` | `Bear Daily` | no time recorded | `BEAR_DAILY` |

`Bull Daily` carries only bullish signals and `Bear Daily` only bearish ones — they are two halves of **one** logical "Yahoo Stocks" source and are always pulled together. Pulling only one silently drops half the equity board.

**Explicitly out of scope:** Weekly TAT state, 1H/4H alerts, `wiki/reports/tat_analysis/` reports, and any confluence / pullback / elbow / invalidation classification. Do not read `tv values`, `data_get_pine_labels`, or the H1/4H sheet tabs for this skill.

### The four data traps (all confirmed against live rows, 2026-09-23)

1. **Mixed date formats inside a single column.** `Forex D` holds 63 rows as `23/09/2026` (DMY) and 115 as `2026-07-24` (ISO); `bats` holds 1 DMY and 597 ISO; both Yahoo tabs are 100% DMY. Filtering on the raw string silently under-counts — it read `bats` as 1 row for 2026-09-23 when the true count was 12. Always normalize first (`normalize_date()`).
2. **Two incompatible schemas.** Forex D and bats use `Date` / `Time` / `Symbol` / `Name` / `Direction` / `Signal Type` / `Signal Price` / `Event` / `Subject`. The Yahoo tabs use `Date & Time` (date only, despite the name) / `Yahoo Symbol` / `Stock Name` / `Signal` / `Signal Price` / `Sector` / `Sub-Sector` / `Subject` — **no Direction column and no time at all**. Derive direction from the signal name.
3. **HK tickers arrive as bare integers** (`823`, `2706`, `386`) — the sheet's recurring `.HK`-suffix-drop bug. A bare all-numeric symbol is **HKEX**, never US. Capture with `HKEX:<code>`; the desktop app rejects `HSI:<code>` for individual HK stocks ("This symbol doesn't exist").
4. **The same instrument under several broker prefixes.** `EIGHTCAP:GBPCHF` and `FUSIONMARKETS:GBPCHF` both printed on 2026-09-23. One instrument, one chart — EIGHTCAP is canonical.

### Volume

Roughly **40–55 signals per run**, collapsing to **~45 unique charts** (2026-09-23: 55 rows → 45 charts). Far above v2's 13–15, and in line with `equity-news-finder`'s proven 40-capture runs.

---

## ⚡ 2. Execution Protocol

### 2.1 Scan

```bash
python3 scripts/scan_daily_signals.py --dry-run                    # human summary
python3 scripts/scan_daily_signals.py --json                       # full rows + captures
python3 scripts/scan_daily_signals.py --capture-list               # "TV_SYMBOL SLUG" lines
```

The script pulls all four tabs, normalizes both schemas, applies the date window, dedupes, and filters against the seen-set. It never writes state unless passed `--commit`.

**The date window.** For a run on day `D`:

| Source | Rows taken | Why |
|---|---|---|
| Forex D | dated `D` | daily bar closes 05:00 SGT, alert writes 05:00–05:01 |
| bats | dated `D` | US close, writes 04:01 SGT |
| Yahoo, **US** symbols | dated `D` | same US close |
| Yahoo, **SGX/HKEX** symbols | dated **`D−1`** | SGX/HKEX close 17:00 SGT — *after* that day's 05:01 run |

The Asian offset is gap-free and overlap-free: a `.SI`/`.HK` row dated `D−1` is first visible to the run on `D`, because the run on `D−1` was looking at `D−2`. Verified live: `O39.SI` dated 23/09 (fired ~17:00 SGT that day) correctly belongs to the 24/09 run, not the 23/09 one.

**Two guards, both built into the script:**
- *05:01 race.* Forex rows land at `05:01:02`–`05:01:04`. At the scheduled 05:45 slot this is long settled, but the guard protects ad hoc runs launched at 05:0x: if the Forex window is empty and it is before 05:02 SGT, the script waits 90s and refetches once. `--no-retry` disables it.
- *Weekends and missed runs.* `scripts/daily_signal_seen.json` holds a watermark plus a 45-day seen-set keyed `source|date|instrument|signal`. The sweep runs from the watermark forward, so a skipped run or a long weekend backfills rather than silently dropping signals. Use `--backfill-from YYYY-MM-DD` to force a wider sweep.

> `scripts/daily_signal_seen.json` is a **dedupe ledger, not watch state**. If it is missing, the run will treat every signal in the window as new — that is recoverable, but say so in the log rather than pretending it was a normal run. If it is present but corrupt, the script exits rather than recreating it.

### 2.2 Screenshot batch

One TradingView session for the whole run, per the Batch TradingView Session Rule:

```bash
./scripts/tv_session.sh start
./scripts/capture_tv_chart.sh <TV_SYMBOL> D <YYMMDD-HHMMSS>_<slug>_D_chart
./scripts/tv_session.sh stop
```

Use the deduped `--capture-list`, not the raw row list — an instrument that appears twice (two signals on `GEN`; `SOXS`/`XOP`/`YANG`/`BAI`/`BOTZ`/`QTUM`/`SOXL` on both bats and Yahoo) gets **one** chart shared by both report sections. Always `D` timeframe.

At ~45 captures, run in **sequential foreground chunks of ~5** — never backgrounded — the pattern `equity-news-finder` uses for its 40-capture runs.

**Screenshot verification (do not skip).** A `📸 Captured screenshot` line is not proof. Blank-canvas renders with a correctly-labelled symbol are the known dominant failure mode. Open several captured PNGs with the Read tool and confirm real candles and legible labels before filing the report.

### 2.3 Report

`wiki/reports/daily-signals/YYYY-MM-DD_Daily_Signals.md` — one file per day.

- Header with explicit SGT timestamp: `# 📅 Daily Signals — 2026-09-23 [05:01 SGT]`.
- TOC wrapped in `<!-- TOC:START -->` / `<!-- TOC:END -->` via `report_toc.upsert_toc()`, regenerated on every write.
- Three top-level sections — **Forex**, **TradingView Stocks**, **Yahoo Stocks** — each with a summary table then the chart embeds.
- Every instrument tagged per the Explicit Per-Instrument Direction Rule: `[[GBPUSD]] (🔴 Bear)`, `[[TSM]] (🟢 Bull)`.
- Images live in `wiki/images/`, embedded as `../../images/<file>.png`. Alt text is **plain** — no `[[...]]`, no nested brackets, no backticks.
- Asian rows state their `D−1` signal date explicitly, so the one-day offset is never mistaken for stale data.
- **Same-day rerun appends** `## 🕒 Intraday Update Run — [HH:MM SGT]` rather than overwriting, consistent with every other report type in this wiki.
- If a run finds nothing new, still append a short confirmation note to the report file itself — not only to `wiki/log.md`.

### 2.4 Commit state and bookkeeping

```bash
python3 scripts/scan_daily_signals.py --json --commit
```

Only after the report is written and screenshots verified. Then: one `scripts/append_log.py` entry summarizing counts per source, direction split, unique charts captured, and anything anomalous; a `wiki/index.md` entry for each **new** report file; and rewrite `wiki/hot.md`.

---

## 🧭 3. Notes on Interpretation

- **Cluster forex by currency theme** (the standing convention in `tat-alert-analysis`) — e.g. three GBP shorts on 2026-09-23 is a single Sterling-supply story, not three independent ideas.
- **Cluster stocks by the sheet's own `Sector` / `Sub-Sector` columns**, which the Yahoo tabs already populate. `scripts/scan_stock_alerts.py` does exactly this clustering and is the reference implementation.
- **Leveraged and inverse ETFs are not independent signals.** `SOXL` (3x semis long) and `SOXS` (3x semis short) firing opposite directions on the same day is one semiconductor call expressed twice; say so rather than listing them as two setups.
- **An instrument on two sources is corroboration, not duplication.** Seven names printed on both bats and the Yahoo tabs on 2026-09-23 — worth noting as agreement between two independent feeds.
- **Direction comes from the signal name** on the Yahoo tabs: `SBull`/`LBull`/`OptBull` → 🟢 Bull, `SBear`/`LBear`/`OptBear` → 🔴 Bear. The `Bull Daily` / `Bear Daily` tab split is a redundant cross-check on this, not the primary source.
- The `Subject` column distinguishes `Alert: Stocks D1` from the older `Alert: US Options (Day)` product. Nothing but `Stocks D1` has appeared since 2026-09-15; if `US Options (Day)` rows reappear, tag them in the report rather than silently blending them in.

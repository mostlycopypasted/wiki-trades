---
name: currency-strength-tracker
description: RETIRED (2026-08-02). Formerly pulled weekly currency strength meter readings from marketsmadeclear.com; superseded by scripts/tat_currency_strength.py.
---

# Currency Strength Tracker (Retired)

**Retired 2026-08-02.** This skill scraped a weekly, external Currency Strength Meter
from marketsmadeclear.com — a third-party score with no connection to the wiki's own
TradingView data. It was replaced because the reading was often stale (the site only
refreshes weekly) and opaque (no visibility into their methodology).

**Current replacement**: `scripts/tat_currency_strength.py`, which derives currency
strength from live TradingView Daily-chart **ZigZag market structure** per instrument
(upward structure / downward structure / change of structure), aggregated per currency
across the 8 majors. It reads `~/tradingview-mcp/daily_brief/*.json` (populated by
`scripts/build_daily_bias.py` from a live `tv brief` scan) and writes the same output
files this skill used to (`wiki/notes/currency-strength.md`,
`wiki/images/currency-strength-graph.svg`), so downstream consumers
(`scripts/generate_daily_brief.py`) needed no changes to their read side. It also
writes a deeper per-run report to `wiki/reports/{date}-tat-currency-strength-report.md`.
`scripts/generate_daily_brief.py` now runs this whole pipeline itself as its first step
— no separate skill invocation is needed.

No cron job was ever scheduled for this skill (confirmed via `CronList` at retirement
time), so there was nothing live to disable.

## What's left here (inert reference only)

- `scripts/pull_currency_strength.py` — the old scraper. Left in place, untouched, as a
  historical reference. Do not run it as part of the live daily-brief pipeline.
- `resources/currency_strength_history.csv` — the old weekly scrape history. Not merged
  into the new structure-based history (different methodology and scale — not
  comparable). The new pipeline's history lives entirely in
  `~/tradingview-mcp/daily_brief/*.json`, one file per day.

To manually run the old scraper for reference/comparison only:
```bash
python3 .agents/skills/currency-strength-tracker/scripts/pull_currency_strength.py
```

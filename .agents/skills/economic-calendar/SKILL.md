---
name: economic-calendar
description: Pulls strictly high-impact (Red Folder events only) from Forex Factory calendar and TradingView API for both This Week and Next Week, formatted in SGT.
---

# Economic Calendar Skill

This skill tracks weekly high-impact economic news releases (strictly **Red Folder events only**) from Forex Factory and TradingView, formatted in Singapore Time (SGT), maintaining schedule tables for both **This Week** and **Next Week**.

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

1. **Execution**: The scraper script pulls from the Forex Factory feed (This Week) and TradingView API (Next Week / fallback), applying strict Red Folder filters.
2. **Cron Schedule**: A cron schedule runs the script every Sunday at 5:00 PM (17:00 SGT).
   - Cron Expression: `0 17 * * 0`
3. **Outputs**:
   - Economic Calendar note: `wiki/notes/economic-calendar.md`

## CLI Commands

To manually trigger a calendar update:
```bash
python3 .agents/skills/economic-calendar/scripts/pull_economic_calendar.py
```

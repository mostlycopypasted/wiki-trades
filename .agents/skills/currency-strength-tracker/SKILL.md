---
name: currency-strength-tracker
description: Pulls weekly currency strength meter readings and plots historical trends.
---

# Currency Strength Tracker

This skill tracks weekly currency strength from marketsmadeclear.com, maintains a CSV history, and plots currency trends using dependency-free SVG graphs.

## Setup & Execution

1. **Execution**: The scraper script is designed to run automatically.
2. **Cron Schedule**: A cron schedule runs the script every Sunday at 5:00 PM (17:00).
   - Cron Expression: `0 17 * * 0` (or `0 9 * * 0` in UTC).
   - **Retry Logic**: If the script exits with status code `2` (meaning the web page data has not been updated yet), you MUST schedule a 1-hour one-shot timer (`DurationSeconds=3600`) to retry the pull. Continue doing this until the script succeeds (exits with code 0). 
3. **Outputs**:
   - Historical CSV: `resources/currency_strength_history.csv`
   - Trend Graph (SVG): `resources/currency_strength_graph.svg`

## CLI Commands

To manually trigger a pull:
```bash
python3 .agents/skills/currency-strength-tracker/scripts/pull_currency_strength.py
```

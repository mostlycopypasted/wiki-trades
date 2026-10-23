#!/usr/bin/env bash
# Cron entry point for the daily equity-news-finder run.
#
# Installed via crontab: 30 7 * * 1-5 /Users/chriseah/obsidian/wiki-trades/scripts/run_equity_news_cron.sh
# (07:30 local time, Monday-Friday)
#
# cron's default environment is minimal — no USER/LOGNAME, and a bare PATH
# that doesn't include Homebrew, the Python framework install, or
# ~/.local/bin (where both `claude` and `ego-browser` live). Without
# USER/LOGNAME set explicitly, `claude` reports "Not logged in" even though
# credentials are present, because auth lookup is keyed off them. All of this
# was verified directly (2026-08-18) by invoking claude under a stripped
# `env -i` shell before this script was written — see wiki/log.md.

export HOME="/Users/chriseah"
export USER="chriseah"
export LOGNAME="chriseah"
export PATH="/Users/chriseah/.local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/chriseah/obsidian/wiki-trades

LOG_DIR="/Users/chriseah/Library/Logs/equity-news-cron"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d_%H%M%S).log"

PROMPT="run the equity news. This is a non-interactive, single-turn, unattended run (claude -p via cron) — nobody will see or respond to any notification, and the process exits the moment this turn ends. Do NOT background the TradingView screenshot batch and wait for a task-notification to resume; that pattern silently abandons the batch when the turn ends (this happened for real on 2026-08-18 — see .agents/skills/equity-news-finder/SKILL.md's Non-interactive / unattended runs note in step 7 for the full story and the fix). Instead, run the screenshot batch as sequential synchronous foreground Bash calls in chunks of ~5 symbols each, with an explicit timeout of 500000-550000ms per chunk. Complete the entire run — sector scan, watchlist pull, screenshots, report, entity pages, index/log/hot.md bookkeeping — within this single turn before finishing."

echo "=== equity-news-finder cron run started $(date) ===" >> "$LOG_FILE"
claude -p "$PROMPT" --permission-mode bypassPermissions >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "=== equity-news-finder cron run finished $(date), exit code $EXIT_CODE ===" >> "$LOG_FILE"
exit $EXIT_CODE

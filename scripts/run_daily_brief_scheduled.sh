#!/bin/bash
# NO LONGER AUTO-SCHEDULED as of 2026-08-29. com.chriseah.wikitrades.morningpipeline.plist
# (which called this script at 05:01 SGT Mon-Sat) has been booted out of
# launchd -- no longer loaded/firing. The auto-firing schedule is now owned
# by Orca's "Daily Brief / Morning Pipeline" automation (id
# 03241164-0280-4341-aa03-4d0b170ad195, same 05:01 SGT Mon-Sat rrule
# "1 5 * * 1-6", --provider claude), which was found to be running the
# identical pipeline concurrently with this launchd job -- confirmed root
# cause of a previously-logged bug (duplicate market-sentiment run
# sections). Resolved by making Orca the sole auto-firing path.
#
# RECURRENCE 2026-08-31: found loaded again (cause unknown), alongside the
# equitynews.asian and equitynews.useu plists -- same collision risk,
# though no confirmed collision incident for this specific job this time.
# The plist now lives at
# scripts/launchd-backup/com.chriseah.wikitrades.morningpipeline.plist
# (moved OUT of ~/Library/LaunchAgents/ entirely, not just unloaded) so a
# stray `launchctl load`/`bootstrap` can't silently reload it again.
#
# This script is kept as a MANUAL BACKUP, on purpose -- run it directly
# (`bash scripts/run_daily_brief_scheduled.sh`) any time, or to resume
# auto-firing from launchd again if ever needed, copy the plist back and
# bootstrap it explicitly (and disable the Orca automation first, or this
# collision reproduces immediately):
#   cp scripts/launchd-backup/com.chriseah.wikitrades.morningpipeline.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/502 ~/Library/LaunchAgents/com.chriseah.wikitrades.morningpipeline.plist
# It also supports running
# under a different agent entirely via AGENT_CLI=agy (Antigravity's CLI,
# ~/.local/bin/agy, Gemini-backed) instead of claude -- see the AGENT_CLI
# branch near the bottom of this file -- specifically so this remains usable
# if Claude usage/credits run out and Orca's Claude-pinned automation can't
# run. See wiki/notes/automation-architecture.md for the full picture of
# which automation owns what.
#
# Previously chained behind an equity-news step in
# run_morning_pipeline_scheduled.sh; as of 2026-08-27 that step runs on its
# own independent schedule instead (see that script's now-superseded header
# for the full history), so this script is invoked directly with no
# equity-news step immediately before it. No logic changes needed here: it
# already drives its own TradingView work through tv_session.sh start/stop
# (see generate_daily_brief.py), which already goes through the CDP session
# lock added to tv_session.sh the same day -- that lock's own stale-holder
# detection is sufficient without any additional pre-cleanup step here.
#
# Two failure modes were seen when the whole workflow was handed to a single
# `claude -p` call as a prompt instruction ("run everything synchronously"):
#   1. `claude -p` backgrounded generate_daily_brief.py anyway and exited
#      before the background task notification could ever arrive (single-turn,
#      no resume) -- 2026-08-19.
#   2. Even after being told explicitly not to background it, it backgrounded
#      it again, then backgrounded a *second* poll-loop to wait on the first,
#      and the whole session was killed while parked on that wait -- 2026-08-20.
# Prompt instructions aren't reliable enough to stop an agent from choosing to
# background a slow step. So the mechanical, deterministic part of this
# workflow (the TradingView/data pipeline) is now run directly by this bash
# script -- a real blocking call, no LLM judgment involved, nothing to
# background. `claude -p` is only invoked afterward, for the two steps that
# actually need judgment: the market-sentiment narrative writeup and the wiki
# bookkeeping -- both fast, non-interactive, no reason to background either.

export PATH="/Users/chriseah/.local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"

cd /Users/chriseah/obsidian/wiki-trades || exit 1

TODAY=$(date '+%Y-%m-%d')
BRIEF_FILE="wiki/reports/daily_brief/${TODAY}.md"
SENTIMENT_FILE="wiki/reports/market-sentiment/${TODAY}-market-sentiment.md"

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — starting scheduled daily brief ==="

python3 scripts/generate_daily_brief.py
PIPELINE_EXIT=$?

if [ $PIPELINE_EXIT -ne 0 ] || [ ! -f "$BRIEF_FILE" ]; then
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — generate_daily_brief.py failed (exit $PIPELINE_EXIT) or ${BRIEF_FILE} missing. Aborting before the claude -p step. ==="
	exit 1
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — pipeline complete, handing off to ${AGENT_CLI:-claude} for narrative writeup + bookkeeping ==="

BOOKKEEPING_PROMPT="The daily brief data pipeline has already run and completed for today (${TODAY}) via scripts/generate_daily_brief.py -- do NOT re-run it. ${BRIEF_FILE} and ${SENTIMENT_FILE} already exist. Your job now, all synchronously within this single turn (this is a non-interactive single-turn call -- you cannot background anything and wait for a notification, you get exactly one turn with no resume):
1. Read the screenshot path embedded in ${BRIEF_FILE} and visually verify it with the Read tool (not blank/stale) per the wiki's screenshot verification rule.
2. Read ${SENTIMENT_FILE} and replace every _pending_ cell with a ~200-word prose summary per the Market Sentiment Report Narrative Rule in CLAUDE.md -- do this directly with the Edit tool, do not shell out to a script.
3. Complete the wiki bookkeeping per CLAUDE.md: append_log.py, update_index.py (once for the Daily Brief, once for the Market Sentiment Report), and rewrite wiki/hot.md entirely.
Do not use run_in_background/background on any tool call -- there is nothing in this remaining work that takes long enough to justify it, and backgrounding here means the work silently never completes."

# AGENT_CLI selects which backend runs the prompt above -- defaults to claude
# (matches Orca's own primary automations). Override for a Claude-independent
# fallback, e.g.:  AGENT_CLI=agy bash scripts/run_daily_brief_scheduled.sh
AGENT_CLI="${AGENT_CLI:-claude}"

case "$AGENT_CLI" in
    claude)
        exec claude -p "$BOOKKEEPING_PROMPT" --permission-mode bypassPermissions
        ;;
    agy)
        # agy's -p/--dangerously-skip-permissions mirror claude -p/--permission-mode
        # bypassPermissions; --model picks a Gemini model since the whole point of
        # this path is not depending on Claude.
        exec agy -p "$BOOKKEEPING_PROMPT" --model gemini-3.1-pro-high --dangerously-skip-permissions
        ;;
    *)
        echo "Unknown AGENT_CLI: $AGENT_CLI (expected claude or agy)" >&2
        exit 1
        ;;
esac

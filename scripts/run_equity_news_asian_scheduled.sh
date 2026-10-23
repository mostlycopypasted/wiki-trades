#!/bin/bash
# NO LONGER AUTO-SCHEDULED as of 2026-08-29. Was installed via launchd
# (com.chriseah.wikitrades.equitynews.asian.plist) at 17:30 SGT, Mon-Sat --
# that job has been booted out of launchd in favor of an equivalent Orca
# automation ("Equity News — Asian", same 17:30 SGT Mon-Sat trigger,
# --provider claude), migrated for consistency with this project's other
# TAT/Daily-Brief automations which all live in Orca now. This script
# remains a MANUAL BACKUP: run it directly
# (`bash scripts/run_equity_news_asian_scheduled.sh`), or run it under a
# different agent via AGENT_CLI=agy (Antigravity's CLI, Gemini-backed)
# instead of claude if Claude usage/credits run out -- see the AGENT_CLI
# branch below. See wiki/notes/automation-architecture.md for the full
# picture of which automation owns what.
#
# RECURRENCE 2026-08-31: the plist silently ended up loaded again (cause
# unknown) and collided with Orca a second time (also happened 2026-08-28),
# SIGKILLing this script's claude process both times. Fix: the plist now
# lives at scripts/launchd-backup/com.chriseah.wikitrades.equitynews.asian.plist
# (moved OUT of ~/Library/LaunchAgents/ entirely, not just unloaded) so it
# can't be silently reloaded by a stray `launchctl load`/`bootstrap` again.
# To resume auto-firing from launchd instead of Orca (full rollback), copy
# it back and bootstrap it explicitly:
#   cp scripts/launchd-backup/com.chriseah.wikitrades.equitynews.asian.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/502 ~/Library/LaunchAgents/com.chriseah.wikitrades.equitynews.asian.plist
# Don't do this without also disabling the Orca automation
# (`orca automations edit --id 5e937d9b-d3c4-4fbc-bf28-04eac71e904b --disabled`)
# or this collision reproduces immediately. See
# wiki/notes/automation-architecture.md for the full incident history.
#
# Runs just after SGX/HKEX close. Covers the full watchlist (100% Asian --
# see scripts/equity_watchlist.json: 25 SGX + 1 KRX, zero US/EU) plus
# Asian-market (.SI/.HK) alert-sheet standouts and the SGX-focused
# minichart.com.sg deep-dive. Companion to
# scripts/run_equity_news_useu_scheduled.sh (04:31 SGT, US-focused today --
# see that script's header for why "EU" is aspirational naming).
#
# Both scripts are same-day-iteration-aware per equity-news-finder
# SKILL.md's step 3 (append an Intraday Update section if today's report
# already exists, rather than overwrite) -- no new merge logic needed here,
# it's all in the prompt below plus the skill itself.
#
# Supersedes the equity-news portion of run_morning_pipeline_scheduled.sh --
# see that script's header for the full incident history (2026-08-20 SIGKILL
# incident, why scope was reduced for scheduled runs, etc.) this script
# still inherits. EQUITY_TIMEOUT_SECS here is 4200s (70 min), not the 3600s
# that script used -- this run's scope is LARGER than that reduced-scope
# baseline (adds back minichart.com.sg + SGX/HKEX standout Yahoo pulls,
# both skipped there), so it needs more headroom.
#
# FIX 2026-08-28: the original split (2026-08-27) dropped standout-alert
# screenshot capture entirely from both scheduled scripts -- the pre-split
# unified skill always captured a chart for any standout alert name not
# already on the watchlist (see SKILL.md step 7), but neither new script's
# prompt carried that forward, so standouts from both runs got zero
# screenshots starting with the first split day. Caught when the user
# noticed no screenshots in the 05:30 US/EU run's report. Fixed by having
# THIS run (the only one of the two that touches TradingView at all) also
# capture screenshots for the day's US-market standouts already pulled by
# the earlier 05:30 run, in addition to its own Asian-market standouts --
# see the prompt below.

export HOME="/Users/chriseah"
export USER="chriseah"
export LOGNAME="chriseah"
export PATH="/Users/chriseah/.local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/chriseah/obsidian/wiki-trades || exit 1

EQUITY_TIMEOUT_SECS=4200   # 70 min -- see header note on why this is higher than the 3600s used elsewhere

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — Asian equity-news run starting ==="

EQUITY_PROMPT="run the equity news. This is a non-interactive, single-turn, unattended run (claude -p, scheduled) — nobody will see or respond to any notification, and the process exits the moment this turn ends. Do NOT background the TradingView screenshot batch and wait for a task-notification to resume; that pattern silently abandons the batch when the turn ends. Instead, run the screenshot batch as sequential synchronous foreground Bash calls in chunks of ~5 symbols each, with an explicit timeout of 500000-550000ms per chunk. SCOPE FOR THIS SCHEDULED RUN ONLY (Asian / 17:30 SGT run — do not apply this scoping to any other invocation): check whether wiki/reports/equitynews/YYYY-MM-DD_equity-news-scan.md already exists for today per the skill's same-day-iteration rule — this run is typically SECOND in the SGT day (after the 04:31 SGT US/EU run), so it will usually append a '## 🕒 Intraday Update Run — [HH:MM SGT]' section rather than overwrite; if no report exists yet for today, create it fresh as usual. Read and sector-cluster the day's alert sheet as usual (needs no browser). For the Yahoo Finance pull: pull every symbol on equity_watchlist.json (all 26, no exceptions) AND every alert-sheet standout name whose Yahoo Symbol ends in .SI (SGX) or .HK (HKEX). Skip Yahoo Finance pulls entirely for bare-ticker (US) standout names — those belong to the separate 04:31 SGT US/EU run, not here. For the supplemental deep-dive: INCLUDE the minichart.com.sg deep-dive for SGX standout and watchlist names (this run has no competing US work this time). Skip financialjuice.com entirely this run — do not open ego-browser for it. Keep the full chart-screenshot batch for every symbol on equity_watchlist.json, exactly as normal — that is the core, non-negotiable part of this run. Also capture a Daily chart screenshot for any standout alert name NOT already on the watchlist, per the skill's normal standout-screenshot rule — this includes both (a) today's Asian-market (.SI/.HK) standouts from this run, and (b) any US-market (bare-ticker) standouts already pulled by the earlier 04:31 SGT US/EU run today, which intentionally does zero TradingView work itself and defers all standout screenshots to this run — check today's already-filed report's Yahoo Finance Cross-Reference section for those names before starting the screenshot batch, so nothing gets missed. Run the Stock Correction Discount Rule check for any watchlist symbol flagged for it (e.g. SK Hynix / 000660.KS) — this belongs here, not in the 04:31 SGT run. This whole run has a hard wall-clock budget enforced by the caller; if running low on time, prioritize finishing watchlist Yahoo pulls + screenshots + report + bookkeeping over the minichart deep-dive, and note in the report if anything had to be skipped for time. Complete the entire run within this single turn before finishing."

# AGENT_CLI selects which backend runs the prompt above -- defaults to claude
# (matches Orca's own primary automation for this workflow). Override for a
# Claude-independent fallback, e.g.:
#   AGENT_CLI=agy bash scripts/run_equity_news_asian_scheduled.sh
AGENT_CLI="${AGENT_CLI:-claude}"

case "$AGENT_CLI" in
    claude)
        claude -p "$EQUITY_PROMPT" --permission-mode bypassPermissions &
        ;;
    agy)
        # agy's -p/--dangerously-skip-permissions mirror claude -p/--permission-mode
        # bypassPermissions; --model picks a Gemini model since the whole point of
        # this path is not depending on Claude.
        agy -p "$EQUITY_PROMPT" --model gemini-3.1-pro-high --dangerously-skip-permissions &
        ;;
    *)
        echo "Unknown AGENT_CLI: $AGENT_CLI (expected claude or agy)" >&2
        exit 1
        ;;
esac
EQUITY_PID=$!
ELAPSED=0
EQUITY_TIMED_OUT=0
while kill -0 "$EQUITY_PID" 2>/dev/null; do
	sleep 10
	ELAPSED=$((ELAPSED + 10))
	if [ "$ELAPSED" -ge "$EQUITY_TIMEOUT_SECS" ]; then
		echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — Asian equity-news exceeded ${EQUITY_TIMEOUT_SECS}s hard timeout, killing (PID $EQUITY_PID) ==="
		kill -9 "$EQUITY_PID" 2>/dev/null
		EQUITY_TIMED_OUT=1
		break
	fi
done
wait "$EQUITY_PID" 2>/dev/null
EQUITY_EXIT=$?
if [ "$EQUITY_TIMED_OUT" -eq 1 ]; then
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — Asian equity-news finished: TIMED OUT after ${EQUITY_TIMEOUT_SECS}s ==="
else
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — Asian equity-news finished, exit code $EQUITY_EXIT ==="
fi

# Sanitize/lint markdown image embeds across reports to prevent broken Obsidian tags
python3 scripts/lint_images.py --fix 2>&1 || true

# Forceful, unconditional cleanup regardless of how this run exited -- this
# run does drive TradingView (full watchlist screenshot batch), so the
# cleanup is still justified here, unlike the US/EU sibling script.
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — unconditional TradingView/process cleanup ==="
pkill -9 -f "tv_session.sh" 2>/dev/null || true
pkill -9 -f "cli/index.js" 2>/dev/null || true
pkill -9 -f "capture_tv_chart.sh" 2>/dev/null || true
pkill -9 -f "TradingView" 2>/dev/null || true
rm -rf /tmp/tradingview-desktop-cdp.lock 2>/dev/null || true

exit $EQUITY_EXIT

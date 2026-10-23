#!/bin/bash
# NO LONGER AUTO-SCHEDULED as of 2026-08-29. Was installed via launchd
# (com.chriseah.wikitrades.equitynews.useu.plist) at 04:31 SGT, Mon-Sat --
# that job has been booted out of launchd in favor of an equivalent Orca
# automation ("Equity News — US/EU", same 04:31 SGT Mon-Sat trigger,
# --provider claude), migrated for consistency with this project's other
# TAT/Daily-Brief automations which all live in Orca now. This script
# remains a MANUAL BACKUP: run it directly
# (`bash scripts/run_equity_news_useu_scheduled.sh`), or run it under a
# different agent via AGENT_CLI=agy (Antigravity's CLI, Gemini-backed)
# instead of claude if Claude usage/credits run out -- see the AGENT_CLI
# branch below. See wiki/notes/automation-architecture.md for the full
# picture of which automation owns what.
#
# RECURRENCE 2026-08-31: found loaded again (cause unknown), alongside the
# equitynews.asian and morningpipeline plists (equitynews.asian confirmed
# SIGKILLed from colliding with its Orca counterpart, 2026-08-28 and
# 2026-08-31). The plist now lives at
# scripts/launchd-backup/com.chriseah.wikitrades.equitynews.useu.plist
# (moved OUT of ~/Library/LaunchAgents/ entirely, not just unloaded) so a
# stray `launchctl load`/`bootstrap` can't silently reload it again. To
# resume auto-firing from launchd instead of Orca, copy it back and
# bootstrap it explicitly (and disable the Orca automation first, or this
# collision reproduces immediately):
#   cp scripts/launchd-backup/com.chriseah.wikitrades.equitynews.useu.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/502 ~/Library/LaunchAgents/com.chriseah.wikitrades.equitynews.useu.plist
#
# Captures the prior US overnight session. "US/EU" is forward-looking
# naming: scripts/scan_stock_alerts.py's market_for_symbol() only
# recognizes US (bare ticker), SGX (.SI), and HKEX (.HK) as of 2026-08-27 --
# no EU data source exists yet, so this run is US-only in practice until
# one is added. Companion to scripts/run_equity_news_asian_scheduled.sh
# (17:30 SGT, Asian-focused).
#
# Deliberately does NOT touch TradingView at all (no tv_session.sh, no
# screenshots, no watchlist -- the watchlist is 100% Asian, see the sibling
# script's header) -- so unlike that script, there is no TradingView-process
# cleanup block here. Running one would risk killing a legitimately
# concurrent TradingView batch (the hourly 1H TAT job, or an overrunning
# Asian run if the two ever land close together) rather than cleaning up
# after this script's own work, since this script never starts a
# TradingView session in the first place.
#
# Standout-alert screenshots for the US names pulled here are captured
# LATER, by the 17:30 SGT Asian run (fixed 2026-08-28 -- the initial split
# dropped standout screenshots for both runs entirely; see that script's
# header). This run's own report section for standouts has no chart images
# until the Asian run's Intraday Update appends them same day.
#
# Same-day-iteration-aware per equity-news-finder SKILL.md's step 3 -- see
# the sibling script's header for how the two runs share one report file.

export HOME="/Users/chriseah"
export USER="chriseah"
export LOGNAME="chriseah"
export PATH="/Users/chriseah/.local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/chriseah/obsidian/wiki-trades || exit 1

EQUITY_TIMEOUT_SECS=1800   # 30 min -- no watchlist/screenshot work, much lighter than the Asian run; revisit after a few real runs

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — US/EU equity-news run starting ==="

EQUITY_PROMPT="run the equity news. This is a non-interactive, single-turn, unattended run (claude -p, scheduled) — nobody will see or respond to any notification, and the process exits the moment this turn ends. SCOPE FOR THIS SCHEDULED RUN ONLY (US/EU / 04:31 SGT run — do not apply this scoping to any other invocation): check whether wiki/reports/equitynews/YYYY-MM-DD_equity-news-scan.md already exists for today per the skill's same-day-iteration rule — this run is typically FIRST in the SGT day (SGX/HKEX are still closed at 04:31 SGT), so it will usually create the report fresh; if one already exists for today (e.g. an earlier ad-hoc run), append a '## 🕒 Intraday Update Run — [HH:MM SGT]' section instead of overwriting. Run the sector scan (python3 scripts/scan_stock_alerts.py) normally — it fetches all rows regardless of market, the market breakdown is just for the printed summary. Skip the watchlist entirely: do NOT read equity_watchlist.json, do NOT pull Yahoo Finance for any watchlist symbol, do NOT run tv_session.sh, do NOT open TradingView, do NOT run any chart-screenshot batch. The watchlist is 100% Asian-market (SGX/KRX) and is fully covered by the separate 17:30 SGT Asian run. Also skip the Stock Correction Discount Rule check entirely this run — it is watchlist-based (SK Hynix / 000660.KS) and belongs to the 17:30 run. For the Yahoo Finance pull on alert-sheet standouts: pull ONLY standout names whose Yahoo Symbol is a bare ticker (no .SI or .HK suffix — i.e. US-market names). Explicitly skip Yahoo pulls for any .SI (SGX) or .HK (HKEX) standout names this run — those belong to the 17:30 SGT Asian run. For the supplemental deep-dive: INCLUDE the financialjuice.com deep-dive for the US standout names just pulled. Skip minichart.com.sg entirely this run — do not open ego-browser for it. This run does no watchlist work and no TradingView/screenshot batch, so it should be much lighter than a full run; still complete the entire run — sector scan, standout Yahoo pulls, financialjuice deep-dive, report, entity pages, index/log/hot.md bookkeeping — within this single turn before finishing."

# AGENT_CLI selects which backend runs the prompt above -- defaults to claude
# (matches Orca's own primary automation for this workflow). Override for a
# Claude-independent fallback, e.g.:
#   AGENT_CLI=agy bash scripts/run_equity_news_useu_scheduled.sh
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
		echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — US/EU equity-news exceeded ${EQUITY_TIMEOUT_SECS}s hard timeout, killing (PID $EQUITY_PID) ==="
		kill -9 "$EQUITY_PID" 2>/dev/null
		EQUITY_TIMED_OUT=1
		break
	fi
done
wait "$EQUITY_PID" 2>/dev/null
EQUITY_EXIT=$?
if [ "$EQUITY_TIMED_OUT" -eq 1 ]; then
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — US/EU equity-news finished: TIMED OUT after ${EQUITY_TIMEOUT_SECS}s ==="
else
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — US/EU equity-news finished, exit code $EQUITY_EXIT ==="
fi

# Sanitize/lint markdown image embeds across reports to prevent broken Obsidian tags
python3 scripts/lint_images.py --fix 2>&1 || true

exit $EQUITY_EXIT

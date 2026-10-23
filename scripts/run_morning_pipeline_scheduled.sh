#!/bin/bash
# SUPERSEDED 2026-08-27 — no longer installed as the launchd
# ProgramArguments for com.chriseah.wikitrades.morningpipeline.plist. The
# equity-news step was split into two independently-scheduled runs (the
# watchlist is 100% Asian-market, so a naive single scheduled run couldn't
# be made faster without splitting it); the daily-brief step is now invoked
# directly by that plist instead of being chained through this wrapper.
# Replaced by:
#   - scripts/run_equity_news_asian_scheduled.sh  (17:30 SGT, via
#     com.chriseah.wikitrades.equitynews.asian.plist)
#   - scripts/run_equity_news_useu_scheduled.sh    (05:30 SGT, via
#     com.chriseah.wikitrades.equitynews.useu.plist)
#   - scripts/run_daily_brief_scheduled.sh         (05:01 SGT, now called
#     directly by com.chriseah.wikitrades.morningpipeline.plist)
# Kept in the repo, not deleted, for reference/rollback. Do not re-enable
# without checking whether the TradingView CDP session lock added to
# tv_session.sh the same day has made this script's own manual
# cleanup/serialization logic (below) obsolete too.
#
# --- Original header follows, describes why this existed in the first place ---
#
# Consolidated scheduled entry point: equity-news-finder runs first, and only
# once it has fully finished (or been forcibly stopped) does the daily brief
# start. Both steps drive the same TradingView Desktop CDP session, so they
# must run strictly sequentially, never concurrently -- that's the whole
# reason this exists as one script instead of two independent schedules.
#
# Installed via launchd (com.chriseah.wikitrades.morningpipeline.plist) at
# 05:01 SGT, Mon-Sat. Supersedes:
#   - the standalone equity-news cron entry (previously 07:30 Mon-Fri via
#     `crontab`, scripts/run_equity_news_cron.sh)
#   - the standalone daily-brief-only launchd job (previously 06:30 Mon-Sat,
#     com.chriseah.wikitrades.dailybrief.plist)
#
# --- 2026-08-20 incident and what changed because of it ---
# A live test run showed equity-news-finder legitimately taking 83+ minutes
# and then getting hard SIGKILLed (exit 137) by something outside this
# script's control -- ruled out an OS-level OOM/jetsam kill via `log show`,
# so this is most likely a harness-level wall-clock limit on non-interactive
# `claude -p` sessions. This is NOT a bug in the skill: per its own SKILL.md,
# Yahoo Finance is only reachable via a real browser (`ego-browser` -- plain
# WebFetch returns 503, bot-blocked), and a full run does one browser
# page-load per symbol, sequentially, for every watchlist symbol AND every
# standout name from that day's alert sheet, plus a 15-25min TradingView
# screenshot batch on top. That's genuinely a lot of sequential browser work.
#
# The old version of this script had no timeout and no guaranteed cleanup:
# when the SIGKILL hit mid-`tv_session.sh start`, that shell process was
# orphaned (reparented to PID 1) and kept running, launching TradingView in
# the background *while the daily-brief step below also tried to open its
# own TradingView session* -- three actors racing on one CDP session at once.
# Caught and killed manually that time; not something to rely on a human
# being awake to catch again.
#
# Two changes address this:
#   1. Scope reduction for SCHEDULED runs only (the EQUITY_PROMPT below) --
#      skip the optional minichart.com.sg/financialjuice.com supplemental
#      deep-dive, and skip Yahoo Finance pulls for alert-sheet standout names
#      that aren't already on the watchlist (that sweep's size varies with
#      how many alerts fired that day, uncapped -- the single biggest source
#      of runtime variance). Watchlist Yahoo pulls and watchlist chart
#      screenshots -- the report's actual core value -- are untouched.
#      Manual/interactive "run the equity news" invocations are NOT affected;
#      this reduced scope only applies to this scheduled prompt.
#   2. A hard wrapper-level timeout (EQUITY_TIMEOUT_SECS below) plus a
#      forceful, unconditional process-tree cleanup that runs regardless of
#      how the equity-news step exited -- clean, timed out, or killed.
#
# Known residual risk, not solved here: the hourly 1H TAT analysis job (runs
# independently, mechanism/schedule unknown to this script) also drives
# TradingView. The cleanup below uses broad pkill patterns (any
# tv_session.sh/cli-index.js/TradingView process), which would also kill a
# *legitimately* concurrent TAT run if this pipeline's timeout fires while
# one happens to be active. Reducing this pipeline's own runtime lowers the
# odds of that overlap but doesn't eliminate it -- there's no shared lock
# file convention between the two systems today.
#
# Each `claude -p` step below is also independently vulnerable to
# backgrounding a slow step and dying before it resumes (seen for real on
# 2026-08-19 for the daily brief) -- the equity-news prompt mitigates this by
# instructing explicit synchronous chunking, and the daily-brief step avoids
# it structurally by running its own pipeline as a direct blocking bash call
# before ever invoking claude -p (see run_daily_brief_scheduled.sh).

export HOME="/Users/chriseah"
export USER="chriseah"
export LOGNAME="chriseah"
export PATH="/Users/chriseah/.local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/chriseah/obsidian/wiki-trades || exit 1

SCRIPT_DIR="/Users/chriseah/obsidian/wiki-trades/scripts"
EQUITY_TIMEOUT_SECS=3600   # 60 min hard cap for the (now-reduced-scope) equity-news step

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — morning pipeline starting: equity news first ==="

EQUITY_PROMPT="run the equity news. This is a non-interactive, single-turn, unattended run (claude -p, scheduled) — nobody will see or respond to any notification, and the process exits the moment this turn ends. Do NOT background the TradingView screenshot batch and wait for a task-notification to resume; that pattern silently abandons the batch when the turn ends. Instead, run the screenshot batch as sequential synchronous foreground Bash calls in chunks of ~5 symbols each, with an explicit timeout of 500000-550000ms per chunk. REDUCED SCOPE FOR THIS SCHEDULED RUN ONLY (do not apply this reduction to any other invocation): skip the optional minichart.com.sg and financialjuice.com supplemental deep-dive entirely — do not open ego-browser for those sites this run. Also skip the Yahoo Finance ego-browser pull for standout alert-sheet names that are NOT already on equity_watchlist.json — still read and sector-cluster the alert sheet itself (that needs no browser), just don't do a per-symbol Yahoo pull for names that are only on the alert sheet. Keep the Yahoo Finance pull and the chart screenshot for every symbol on equity_watchlist.json — that is the core, non-negotiable part of this run. This whole run has a hard 60-minute wall-clock budget enforced by the caller; if you are running low on time, prioritize finishing the watchlist Yahoo pulls + screenshots + report + bookkeeping over anything else, and note in the report if any step had to be skipped for time. Complete the entire run within this single turn before finishing."

claude -p "$EQUITY_PROMPT" --permission-mode bypassPermissions &
EQUITY_PID=$!
ELAPSED=0
EQUITY_TIMED_OUT=0
while kill -0 "$EQUITY_PID" 2>/dev/null; do
	sleep 10
	ELAPSED=$((ELAPSED + 10))
	if [ "$ELAPSED" -ge "$EQUITY_TIMEOUT_SECS" ]; then
		echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — equity news exceeded ${EQUITY_TIMEOUT_SECS}s hard timeout, killing (PID $EQUITY_PID) ==="
		kill -9 "$EQUITY_PID" 2>/dev/null
		EQUITY_TIMED_OUT=1
		break
	fi
done
wait "$EQUITY_PID" 2>/dev/null
EQUITY_EXIT=$?
if [ "$EQUITY_TIMED_OUT" -eq 1 ]; then
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — equity news finished: TIMED OUT after ${EQUITY_TIMEOUT_SECS}s ==="
else
	echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — equity news finished, exit code $EQUITY_EXIT ==="
fi

# Forceful, unconditional cleanup regardless of how equity-news exited --
# clean exit, timeout, or an external kill can all leave orphaned tv_session/
# node/TradingView processes behind. See the residual-risk note above re:
# the hourly TAT job sharing TradingView.
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — unconditional TradingView/process cleanup before daily brief ==="
pkill -9 -f "tv_session.sh" 2>/dev/null || true
pkill -9 -f "cli/index.js" 2>/dev/null || true
pkill -9 -f "capture_tv_chart.sh" 2>/dev/null || true
pkill -9 -f "TradingView" 2>/dev/null || true
# A killed tv_session.sh/capture_tv_chart.sh process above may have been
# holding the CDP session lock (added 2026-08-27, see tv_session.sh) --
# tv_session.sh's own stale-PID check would catch this on the next acquire
# attempt anyway, but clear it here too rather than making the daily-brief
# step (which starts right after this) wait out that detection.
rm -rf /tmp/tradingview-desktop-cdp.lock 2>/dev/null || true
sleep 2

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — starting daily brief ==="
bash "$SCRIPT_DIR/run_daily_brief_scheduled.sh"
BRIEF_EXIT=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') — daily brief finished, exit code $BRIEF_EXIT ==="

exit $BRIEF_EXIT

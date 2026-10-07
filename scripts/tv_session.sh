#!/usr/bin/env bash
# Usage: ./scripts/tv_session.sh [start|stop]

set -e

ACTION=${1:-"start"}
MCP_DIR="$HOME/tradingview-mcp"
WIKI_DIR="/Users/chriseah/obsidian/wiki-trades"
cd "$MCP_DIR"

# --- TradingView Desktop CDP session lock -----------------------------------
# Every script that drives TradingView Desktop's CDP session (this script,
# capture_tv_chart.sh, the hourly 1H TAT job, generate_daily_brief.py's top-
# setup capture, etc.) funnels through `tv_session.sh start`/`stop` per the
# Batch TradingView Session Rule in CLAUDE.md — but until now nothing
# serialized access to that ONE shared CDP session across concurrent
# invocations. Confirmed live 2026-08-27: the hourly 1H TAT job collided
# with a concurrent equity-news-finder screenshot batch, silently landing 5
# captures on the wrong symbol (the capture script reported success with no
# warning; only caught by manual visual verification). This mkdir-based
# lock (atomic on POSIX filesystems, no extra dependencies — `flock` isn't
# installed on this Mac) serializes `start` calls so only one
# TradingView-driving batch runs at a time; everyone else waits for the
# holder's `stop` to release it rather than racing the same CDP session.
#
# Ownership is intentionally NOT verified via the calling script's own PID:
# `tv_session.sh start` launches TradingView and then exits within seconds
# (it doesn't stay running for the whole batch — the batch is a series of
# separate `capture_tv_chart.sh` invocations with no persistent parent
# process linking them, especially under the common SKILL.md-driven calling
# pattern where each is its own top-level Bash tool call). A first version
# of this lock recorded $$ as the holder and checked `kill -0` on it — that
# is WRONG and was caught in testing: the recorder process is dead within
# seconds of every single `start` call by design, so that check would
# immediately treat every lock as stale, defeating the whole point.
#
# The actual shared, long-lived resource for the whole batch is the
# TradingView Desktop app process itself (alive from `start` until `stop`
# closes it) — so liveness is checked against THAT instead: the lock is
# stale if TradingView isn't running at all (nothing could be using the CDP
# session) or if it's simply been held too long regardless (age fallback,
# in case TradingView is running but unrelated to any tracked batch — e.g.
# opened manually). `stop` always clears the lock unconditionally on its
# way out. This is a pragmatic serialization fix, not an airtight
# mutual-exclusion guarantee — it eliminates the common accidental-collision
# case without reintroducing an indefinite wait.
LOCK_DIR="/tmp/tradingview-desktop-cdp.lock"
LOCK_STALE_SECS=1800    # 30min — above the documented 15-25min worst-case batch
LOCK_MAX_WAIT_SECS=600  # 10min — wait for a concurrent batch to finish before giving up
LOCK_GRACE_SECS=20      # give a freshly-acquired lock time to actually launch TradingView
                        # before anyone treats "not running yet" as stale — otherwise a second
                        # waiter could steal the lock in the brief launch window and race the
                        # very thing this lock exists to prevent.

acquire_tv_lock() {
    local waited=0
    local announced=false
    while ! mkdir "$LOCK_DIR" 2>/dev/null; do
        local holder_info lock_age
        holder_info=""
        [ -f "$LOCK_DIR/info" ] && holder_info=$(cat "$LOCK_DIR/info" 2>/dev/null)
        lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
        if [ "$lock_age" -ge "$LOCK_GRACE_SECS" ] && [ -z "$(pgrep -f '/Applications/TradingView.app/Contents/MacOS/TradingView' 2>/dev/null)" ]; then
            echo "⚠️ TradingView CDP lock held but TradingView isn't running — clearing stale lock ($holder_info)."
            rm -rf "$LOCK_DIR"
            continue
        fi
        if [ "$lock_age" -ge "$LOCK_STALE_SECS" ]; then
            echo "⚠️ TradingView CDP lock is ${lock_age}s old (>${LOCK_STALE_SECS}s) — treating as stale, clearing."
            rm -rf "$LOCK_DIR"
            continue
        fi
        if [ "$announced" = false ]; then
            echo "⏳ TradingView CDP session is in use by another job ($holder_info) — waiting for it to finish..."
            announced=true
        fi
        if [ "$waited" -ge "$LOCK_MAX_WAIT_SECS" ]; then
            echo "⚠️ Waited ${LOCK_MAX_WAIT_SECS}s for the TradingView CDP lock and it's still held — proceeding anyway (collision risk accepted rather than blocking indefinitely)."
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    echo "pid=$$ script=$(basename "$0") started=$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCK_DIR/info"
}

release_tv_lock() {
    rm -rf "$LOCK_DIR"
}

if [ "$ACTION" = "start" ]; then
    acquire_tv_lock
    echo "🚀 Starting TradingView session with CDP enabled..."
    if node src/cli/index.js launch > /dev/null 2>&1; then
        LAUNCH_EXIT=0
    else
        LAUNCH_EXIT=$?
    fi
    if [ "$LAUNCH_EXIT" -eq 124 ]; then
        # The CLI's own --timeout-ms safety net fired (default 180s) — don't
        # retry launch immediately, since if the underlying cause is a stuck
        # compositor (no active GUI session), an immediate retry would very
        # plausibly just hang again. Fall through to the state poll below,
        # which already independently verifies readiness regardless of what
        # launch reported.
        echo "⏱️ TIMED OUT — launch (proceeding to state poll anyway)"
    fi
    sleep 2.5

    # A fixed sleep isn't enough for a cold launch — the chart widget's JS API
    # (window.TradingViewApi) can take longer to attach than 2.5s, which makes
    # the *first* symbol/timeframe command in a batch race a half-initialized
    # page (seen 2026-08-05: first capture in a batch landed on an unconfirmed
    # symbol-search dropdown instead of the chart). Poll `state` until the CDP
    # bridge actually returns a valid chart state before declaring ready.
    READY=false
    for i in $(seq 1 20); do
        if node src/cli/index.js state 2>/dev/null | grep -q '"success": *true'; then
            READY=true
            break
        fi
        sleep 1
    done
    if [ "$READY" = true ]; then
        echo "✅ TradingView session active (chart API confirmed ready)."
    else
        echo "⚠️ TradingView launched but chart API didn't confirm ready within 20s — proceeding anyway."
    fi

    # Ensure target layout ("0 TAW Layout") is loaded. `layout switch` now
    # verifies the target layout actually finished loading before reporting
    # success (fixed 2026-09-28 — it used to report success the instant the
    # switch was REQUESTED, not once it completed, so every command issued
    # right after could silently land on the previous layout instead; see
    # src/core/ui.js's layoutSwitch()). Trust its exit code, but capture the
    # real error text instead of discarding it, and stop rather than
    # silently batch-capturing on the wrong layout if it never confirms.
    LAYOUT_TARGET=${CHART_LAYOUT:-"0 TAW Layout"}
    echo "📐 Ensuring chart layout \"$LAYOUT_TARGET\" is active..."
    LAYOUT_EXIT=0
    LAYOUT_ERR=$(node src/cli/index.js layout switch "$LAYOUT_TARGET" 2>&1 > /dev/null) || LAYOUT_EXIT=$?
    if [ "$LAYOUT_EXIT" -eq 0 ]; then
        echo "✅ Layout switched to \"$LAYOUT_TARGET\" (confirmed on screen)."
    else
        echo "⚠️ Layout switch to \"$LAYOUT_TARGET\" failed: $LAYOUT_ERR"
        echo "🔁 Retrying with fallback match \"taw\"..."
        FALLBACK_EXIT=0
        LAYOUT_ERR=$(node src/cli/index.js layout switch "taw" 2>&1 > /dev/null) || FALLBACK_EXIT=$?
        if [ "$FALLBACK_EXIT" -eq 0 ]; then
            echo "✅ Layout switched to TAW layout (fallback match, confirmed on screen)."
        else
            echo "❌ Could not confirm the TAW layout loaded: $LAYOUT_ERR"
            echo "❌ Refusing to proceed — captures would silently land on whatever layout was already on screen."
            release_tv_lock
            exit 1
        fi
    fi

    # Force the page out of Chromium's "hidden" page-visibility state — see
    # scripts/force_tv_visible.mjs for why this is necessary (root-caused
    # 2026-08-05: a backgrounded/occluded window silently blanks every chart
    # screenshot while everything else, incl. `state` checks, reports fine).
    node "$WIKI_DIR/scripts/force_tv_visible.mjs" 2>&1 || true

elif [ "$ACTION" = "stop" ]; then
    # Captures render as Line (capture_tv_chart.sh sets it per chart — see the
    # Chart Type Standard in CLAUDE.md), but the user reads the chart as
    # candlesticks when they open TradingView themselves. Restore the resting
    # type BEFORE the Cmd+S below so the saved layout — and therefore the next
    # launch, including after a reboot — comes up as Candles. Override with
    # RESTORE_CHART_TYPE=<type>, or RESTORE_CHART_TYPE= (empty) to skip.
    RESTORE_CHART_TYPE="${RESTORE_CHART_TYPE-Candles}"
    if [ -n "$RESTORE_CHART_TYPE" ] && pgrep -f TradingView > /dev/null 2>&1; then
        echo "🕯️ Restoring chart type to $RESTORE_CHART_TYPE..."
        node src/cli/index.js type "$RESTORE_CHART_TYPE" > /dev/null 2>&1 || true
        RESTORED=$(node src/cli/index.js type 2>/dev/null | grep -o '"chart_type": *"[^"]*"' | head -1 | sed 's/.*"chart_type": *"//;s/"$//')
        if [ "$RESTORED" = "$RESTORE_CHART_TYPE" ]; then
            echo "✅ Chart type restored to $RESTORED."
        else
            echo "⚠️ Could not confirm chart type restore to '$RESTORE_CHART_TYPE' (got '$RESTORED')."
        fi
    fi

    echo "💾 Saving chart layout (Cmd+S)..."
    node src/cli/index.js ui keyboard s --meta > /dev/null 2>&1 || true
    sleep 1.5

    echo "🚪 Requesting graceful quit for TradingView..."
    osascript -e 'tell application "TradingView" to quit' > /dev/null 2>&1 || node src/cli/index.js ui keyboard q --meta > /dev/null 2>&1 || true
    sleep 3

    TV_PIDS=$(pgrep -f TradingView || true)
    if [ -n "$TV_PIDS" ]; then
        echo "⚠️ TradingView process ($TV_PIDS) still active after 3s; executing pkill..."
        pkill -9 -f TradingView || true
    else
        echo "✅ TradingView closed gracefully."
    fi
    release_tv_lock
else
    echo "Unknown action: $ACTION. Use 'start' or 'stop'."
    exit 1
fi

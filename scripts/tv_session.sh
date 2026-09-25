#!/usr/bin/env bash
# Usage: ./scripts/tv_session.sh [start|stop]

set -e

ACTION=${1:-"start"}
MCP_DIR="$HOME/tradingview-mcp"
cd "$MCP_DIR"

if [ "$ACTION" = "start" ]; then
    echo "🚀 Starting TradingView session with CDP enabled..."
    node src/cli/index.js launch > /dev/null 2>&1 || true
    sleep 2.5
    echo "✅ TradingView session active."

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
else
    echo "Unknown action: $ACTION. Use 'start' or 'stop'."
    exit 1
fi

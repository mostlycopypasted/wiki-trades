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

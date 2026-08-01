#!/usr/bin/env bash
# Usage: ./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME> [OUTPUT_NAME] [--standalone]
# Example: ./scripts/capture_tv_chart.sh EIGHTCAP:GBPAUD 60
# Outputs: wiki/images/YYMMDD-HHMMSS_gbpaud_1h_chart.png

set -e

RAW_SYMBOL=${1:-"EIGHTCAP:GBPAUD"}
TF=${2:-"60"}
CUSTOM_NAME=${3:-""}
STANDALONE=false

if [ "$4" = "--standalone" ] || [ "$1" = "--standalone" ] || [ "$3" = "--standalone" ]; then
    STANDALONE=true
fi

# Clean symbol (e.g. EIGHTCAP:AUDCAD -> audcad)
PURE_SYMBOL=$(echo "$RAW_SYMBOL" | sed 's/.*://' | tr '[:upper:]' '[:lower:]')

# Standardize timeframe suffix (60 -> 1h, 240 -> 4h, D/1D -> D)
if [ "$TF" = "60" ] || [ "$TF" = "1h" ]; then
    TF_SUFFIX="1h"
elif [ "$TF" = "240" ] || [ "$TF" = "4h" ]; then
    TF_SUFFIX="4h"
elif [ "$TF" = "D" ] || [ "$TF" = "1D" ] || [ "$TF" = "daily" ]; then
    TF_SUFFIX="D"
else
    TF_SUFFIX="$TF"
fi

TS=$(date +"%y%m%d-%H%M%S")

# Generate filename matching convention: YYMMDD-HHMMSS_symbol_4h/1h/D_chart.png
if [ -n "$CUSTOM_NAME" ] && [ "$CUSTOM_NAME" != "--standalone" ] && [[ "$CUSTOM_NAME" =~ ^[0-9]{6}-[0-9]{6}_ ]]; then
    OUT_NAME="$CUSTOM_NAME"
else
    OUT_NAME="${TS}_${PURE_SYMBOL}_${TF_SUFFIX}_chart"
fi

MCP_DIR="$HOME/tradingview-mcp"
WIKI_DIR="/Users/chriseah/obsidian/wiki-trades"
WIKI_IMG_DIR="$WIKI_DIR/wiki/images"

mkdir -p "$WIKI_IMG_DIR"
cd "$MCP_DIR"

# Check if TradingView process is currently running
TV_PIDS=$(pgrep -f TradingView || true)

# If standalone mode requested or TradingView is not running, start session
if [ "$STANDALONE" = true ] || [ -z "$TV_PIDS" ]; then
    bash "$WIKI_DIR/scripts/tv_session.sh" start
    AUTO_STOP=true
else
    AUTO_STOP=false
fi

# 1. Set symbol and timeframe
node src/cli/index.js symbol "$RAW_SYMBOL" > /dev/null 2>&1
node src/cli/index.js timeframe "$TF" > /dev/null 2>&1
sleep 1.5

# 2. Reset chart scale and view (Alt+R)
node src/cli/index.js ui keyboard r --alt > /dev/null 2>&1
sleep 1

# 3. Take screenshot and move directly to wiki-trades/wiki/images/
CLEAN_NAME=$(echo "$OUT_NAME" | tr -c 'A-Za-z0-9._-' '_')
node src/cli/index.js screenshot -o "$OUT_NAME" > /dev/null 2>&1

if [ -f "$MCP_DIR/screenshots/${CLEAN_NAME}.png" ]; then
    mv -f "$MCP_DIR/screenshots/${CLEAN_NAME}.png" "$WIKI_IMG_DIR/${CLEAN_NAME}.png"
elif [ -f "$MCP_DIR/screenshots/${OUT_NAME}.png" ]; then
    mv -f "$MCP_DIR/screenshots/${OUT_NAME}.png" "$WIKI_IMG_DIR/${OUT_NAME}.png"
fi

if [ -f "$WIKI_IMG_DIR/${CLEAN_NAME}.png" ]; then
    echo "📸 Captured screenshot: $WIKI_IMG_DIR/${CLEAN_NAME}.png"
elif [ -f "$WIKI_IMG_DIR/${OUT_NAME}.png" ]; then
    echo "📸 Captured screenshot: $WIKI_IMG_DIR/${OUT_NAME}.png"
fi

# If standalone mode was auto-started, stop session now
if [ "$AUTO_STOP" = true ] && [ "$STANDALONE" = true ]; then
    bash "$WIKI_DIR/scripts/tv_session.sh" stop
fi

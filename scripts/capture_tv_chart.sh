#!/usr/bin/env bash
# Usage: ./scripts/capture_tv_chart.sh <SYMBOL> <TIMEFRAME> [OUTPUT_NAME] [--standalone]
# Env:   CHART_TYPE=Line|Candles|Bars|Area|HeikinAshi|...  (default: Line)
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

# Strip all trailing .png that TradingView Desktop's API or user input may have
# included (otherwise core/capture.js appends another, giving us foo.png.png).
# The CLI's -o flag is documented as "without .png".
while [[ "$OUT_NAME" == *.png ]]; do
    OUT_NAME="${OUT_NAME%.png}"
done

# Runs a `node src/cli/index.js <args...>` call, capturing stdout in $CLI_OUT
# and setting $CLI_EXIT. The CLI now has its own --timeout-ms safety net
# (default 180s) so a hung CDP call exits 124 instead of blocking forever —
# detect and log that specifically so it's visible in run logs. Callers must
# invoke this as `run_cli ... || true` under this script's `set -e`, since a
# non-zero return here would otherwise abort the whole script.
run_cli() {
    CLI_OUT=$(node src/cli/index.js "$@" 2>/dev/null)
    CLI_EXIT=$?
    if [ "$CLI_EXIT" -eq 124 ]; then
        echo "⏱️ TIMED OUT — node src/cli/index.js $*"
    fi
    return $CLI_EXIT
}

# Check if TradingView process is currently running
TV_PIDS=$(pgrep -f TradingView || true)

# If standalone mode requested or TradingView is not running, start session
if [ "$STANDALONE" = true ] || [ -z "$TV_PIDS" ]; then
    bash "$WIKI_DIR/scripts/tv_session.sh" start
    AUTO_STOP=true
else
    AUTO_STOP=false
fi

# 1. Set symbol, then verify the chart actually landed on it before proceeding.
# The CLI's own setSymbol() already waits internally, but that wait can be
# satisfied by a stale/half-initialized page (seen 2026-08-05: symbol label
# updated but the chart pane stayed blank on the previous symbol's data, and
# on a cold session the symbol-search dropdown was left open, unconfirmed).
# So re-check independently via `state` and retry the whole symbol-set if the
# reported symbol doesn't actually match what we asked for.
PURE_TICKER=$(echo "$RAW_SYMBOL" | sed 's/.*://' | tr '[:upper:]' '[:lower:]')
SYMBOL_CONFIRMED=false
for attempt in 1 2 3; do
    run_cli symbol "$RAW_SYMBOL" || true
    for poll in 1 2 3 4 5; do
        run_cli state || true
        CURRENT=$(echo "$CLI_OUT" | grep -o '"symbol": *"[^"]*"' | head -1 | sed 's/.*"symbol": *"//;s/"$//' | tr '[:upper:]' '[:lower:]')
        if [ -n "$CURRENT" ] && [[ "$CURRENT" == *"$PURE_TICKER"* ]]; then
            SYMBOL_CONFIRMED=true
            break
        fi
        sleep 1
    done
    if [ "$SYMBOL_CONFIRMED" = true ]; then
        break
    fi
    echo "⚠️ Symbol not confirmed on attempt $attempt (wanted '$PURE_TICKER', got '$CURRENT') — retrying..."
done
if [ "$SYMBOL_CONFIRMED" != true ]; then
    echo "⚠️ Could not confirm symbol '$RAW_SYMBOL' after 3 attempts — screenshot may be inaccurate."
fi

# 1b. Set timeframe, then verify it actually landed before proceeding — same
# rationale as the symbol check above. The CLI's setTimeframe() reports
# chart_ready:true purely from a canvas-paint check, not a resolution check,
# so a DOM button-click fallback that silently no-ops (seen when this runs
# right after a heavy multi-symbol scan, e.g. the "tv brief" 84-symbol Daily
# pass, leaving the UI mid-render) goes undetected and the screenshot is
# captured on the previous timeframe (found 2026-08-10: a requested 1H
# screenshot rendered as a fully-painted, correctly-labeled-symbol Daily
# chart). Re-check independently via `state` and retry the whole
# timeframe-set if the reported resolution doesn't match what we asked for.
TF_LOWER=$(echo "$TF" | tr '[:upper:]' '[:lower:]')
EXPECTED_RES="$TF"
case "$TF_LOWER" in
    1h|60|60m) EXPECTED_RES="60" ;;
    4h|240|240m) EXPECTED_RES="240" ;;
    # `timeframe D`/`timeframe 1D` both succeed and echo back "timeframe":
    # "D" in their own response, but `state`'s actual resolution field
    # reports "1D" — confirmed live 2026-08-23. The old `1d) EXPECTED_RES="D"`
    # mapping (and the unhandled bare "d" case, which fell through to
    # EXPECTED_RES="D" via the default above) both expected the wrong
    # string, so every single Daily capture burned all 3 attempts x 5 polls
    # (~15s) before giving up with a warning, even though the timeframe had
    # actually been set correctly on the very first call. Same bug for
    # Weekly ("1w"/"1W" vs. the real "1W" resolution string).
    d|1d|daily) EXPECTED_RES="1D" ;;
    w|1w|weekly) EXPECTED_RES="1W" ;;
esac
RESOLUTION_CONFIRMED=false
for attempt in 1 2 3; do
    run_cli timeframe "$TF" || true
    for poll in 1 2 3 4 5; do
        run_cli state || true
        CURRENT_RES=$(echo "$CLI_OUT" | grep -o '"resolution": *"[^"]*"' | head -1 | sed 's/.*"resolution": *"//;s/"$//')
        if [ "$CURRENT_RES" = "$EXPECTED_RES" ]; then
            RESOLUTION_CONFIRMED=true
            break
        fi
        sleep 1
    done
    if [ "$RESOLUTION_CONFIRMED" = true ]; then
        break
    fi
    echo "⚠️ Timeframe not confirmed on attempt $attempt (wanted '$EXPECTED_RES', got '$CURRENT_RES') — retrying..."
done
if [ "$RESOLUTION_CONFIRMED" != true ]; then
    echo "⚠️ Could not confirm timeframe '$TF' after 3 attempts — screenshot may show the wrong resolution."
fi

# 1c. Set the chart type. Defaults to Line — the wiki's charts are read for
# structure (HH/HL/LH/LL, impulse confirmation, level breaks), and a line chart
# strips intrabar noise that obscures those reads. Override per call with
# CHART_TYPE=Candles (valid: Bars, Candles, Line, Area, HeikinAshi,
# HollowCandles, Renko, Kagi, PointAndFigure, LineBreak).
# Set after the timeframe is confirmed: a resolution change re-renders the pane
# and can revert a type set that ran before it.
CHART_TYPE="${CHART_TYPE:-Line}"
TYPE_CONFIRMED=false
for attempt in 1 2 3; do
    run_cli type "$CHART_TYPE" || true
    run_cli type || true
    CURRENT_TYPE=$(echo "$CLI_OUT" | grep -o '"chart_type": *"[^"]*"' | head -1 | sed 's/.*"chart_type": *"//;s/"$//')
    if [ "$CURRENT_TYPE" = "$CHART_TYPE" ]; then
        TYPE_CONFIRMED=true
        break
    fi
    sleep 1
done
if [ "$TYPE_CONFIRMED" != true ]; then
    echo "⚠️ Could not confirm chart type '$CHART_TYPE' (got '$CURRENT_TYPE') — screenshot may show the wrong style."
fi

# Extra settle time for chart data to actually paint onto the canvas —
# symbol/loading-spinner checks don't guarantee the chart has finished
# rendering, so this is a deliberate safety margin, not just habit.
sleep 2

# The underlying MCP tool's setSymbol() always retries via a UI fallback
# (click legend -> type symbol -> Enter) even after its own JS-API symbol
# switch already succeeded silently. On a freshly-warmed session that
# fallback's Enter can lag behind the dropdown's own async load, leaving an
# open, unconfirmed "Symbol search" dialog on screen even though `state`
# already reports the correct symbol underneath it (root-caused 2026-08-05
# from a batch where the very first capture after session start showed the
# dialog still open in the screenshot). Escape is a no-op when nothing is
# open, so press it unconditionally as cheap insurance before every capture.
run_cli ui keyboard Escape || true
run_cli ui eval 'var b=document.querySelector("[data-name=\"close\"], [aria-label=\"Close\"], button[class*=\"close\"]"); if(b) b.click();' || true
sleep 0.5

# 2. Reset chart scale and view (Alt+R)
run_cli ui keyboard r --alt || true
sleep 1.5

# Force the page out of Chromium's "hidden" page-visibility state right
# before capturing. This is the dominant real-world cause of a blank/stale
# screenshot (root-caused 2026-08-05) — a backgrounded/occluded TradingView
# window makes Chromium throttle canvas rendering entirely, while symbol
# labels and `state` checks keep reporting success because they don't depend
# on the render loop. Idempotent and cheap, so run it unconditionally rather
# than trying to detect visibility loss first.
node "$WIKI_DIR/scripts/force_tv_visible.mjs" 2>&1 || true
sleep 1

# 3. Take screenshot and move directly to wiki-trades/wiki/images/
CLEAN_NAME=$(echo "$OUT_NAME" | tr -c 'A-Za-z0-9._-' '_')
run_cli screenshot -o "$OUT_NAME" || true
if [ "$CLI_EXIT" -eq 124 ]; then
    echo "⏱️ TIMED OUT — screenshot capture failed, no new image will be written for $OUT_NAME"
fi

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

#!/usr/bin/env bash
# Manual/on-demand BACKUP screenshot path via ego-browser (real Chromium,
# CDP-driven, TradingView web chart). NOT wired into tv_session.sh,
# capture_tv_chart.sh, or generate_daily_brief.py automation — invoke
# explicitly only. TradingView MCP remains the sole source of Pine
# labels/lines/quotes/indicator values; this script only produces an image.
#
# Usage: ./scripts/capture_tv_chart_egobrowser.sh <SYMBOL> <TIMEFRAME> [OUTPUT_NAME]
# Example: ./scripts/capture_tv_chart_egobrowser.sh EIGHTCAP:GBPAUD 60
# Outputs: wiki/images/YYMMDD-HHMMSS_gbpaud_1h_chart.png

set -e

RAW_SYMBOL=${1:?symbol required, e.g. EIGHTCAP:GBPAUD}
TF=${2:?timeframe required, e.g. 60}
CUSTOM_NAME=${3:-""}

# Clean symbol (e.g. EIGHTCAP:AUDCAD -> audcad)
PURE_SYMBOL=$(echo "$RAW_SYMBOL" | sed 's/.*://' | tr '[:upper:]' '[:lower:]')

# Standardize timeframe suffix (60 -> 1h, 240 -> 4h, D/1D -> D) — same
# convention as capture_tv_chart.sh so filenames are directly comparable.
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

if [ -n "$CUSTOM_NAME" ] && [[ "$CUSTOM_NAME" =~ ^[0-9]{6}-[0-9]{6}_ ]]; then
    OUT_NAME="$CUSTOM_NAME"
else
    OUT_NAME="${TS}_${PURE_SYMBOL}_${TF_SUFFIX}_chart"
fi
# printf (not echo) avoids feeding tr a trailing newline it would otherwise
# turn into a stray trailing underscore.
CLEAN_NAME=$(printf '%s' "$OUT_NAME" | tr -c 'A-Za-z0-9._-' '_')

WIKI_DIR="/Users/chriseah/obsidian/wiki-trades"
WIKI_IMG_DIR="$WIKI_DIR/wiki/images"
mkdir -p "$WIKI_IMG_DIR"

# ego-browser's `nodejs` runtime does not inherit the calling shell's
# exported env vars (verified empirically — only a fixed system allowlist
# is present in process.env there), so parameters are handed over via a
# JSON file instead. python3 -c with argv avoids any shell-escaping hazard
# from symbols/paths containing special characters.
PARAMS_FILE="/tmp/wiki-trades-ego-tv-capture-params.json"
python3 -c "
import json, sys
json.dump({'symbol': sys.argv[1], 'timeframe': sys.argv[2], 'outputPath': sys.argv[3]}, open(sys.argv[4], 'w'))
" "$RAW_SYMBOL" "$TF" "$WIKI_IMG_DIR/${CLEAN_NAME}.png" "$PARAMS_FILE"

ego-browser nodejs <<'EOF'
const fs = await import('node:fs');
const params = JSON.parse(fs.readFileSync('/tmp/wiki-trades-ego-tv-capture-params.json', 'utf8'));
const symbol = params.symbol;
const timeframe = params.timeframe;
const outputPath = params.outputPath;
const wantTicker = symbol.split(':').pop().toLowerCase();

const task = await useOrCreateTaskSpace('tv-chart-capture-backup');

const url = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(timeframe)}`;

let legendOk = false;
for (let attempt = 1; attempt <= 3; attempt++) {
  await openOrReuseTab(url, { wait: true, timeout: 30 });
  await waitForNetworkIdle({ timeout: 20 });
  await waitForElement('canvas', { timeout: 20 });

  // Same class of bug documented in force_tv_visible.mjs for the TradingView
  // Desktop app: an occluded/backgrounded window silently throttles canvas
  // painting while every other signal keeps reporting fine. Force it active
  // before trusting anything we're about to read or screenshot.
  await cdp('Emulation.setFocusEmulationEnabled', { enabled: true });
  await cdp('Page.setWebLifecycleState', { state: 'active' });

  const info = await pageInfo();
  if (info && info.dialog) {
    await cdp('Page.handleJavaScriptDialog', { accept: true });
  }
  // Escape is a no-op when nothing is open; cheap insurance before every
  // capture, same as the unconditional Escape in capture_tv_chart.sh.
  await pressKey('Escape');

  // Settle time for candle data to actually paint onto the canvas — network
  // idle / DOM load don't guarantee the chart has finished rendering.
  await wait(3);

  const legendText = await js(String.raw`(() => {
    const el = document.querySelector('[data-name="legend-source-item"]')
      || document.querySelector('.pane-legend-title__wrap')
      || document.body;
    return (el && el.innerText || '').toLowerCase();
  })()`);
  legendOk = legendText.includes(wantTicker);
  if (legendOk) break;
  await wait(1);
}
if (!legendOk) {
  cliLog(`WARNING: could not confirm "${wantTicker}" in the chart legend after 3 attempts — screenshot may be inaccurate.`);
}

const shot = await captureScreenshot();

if (typeof shot === 'string' && shot.startsWith('data:')) {
  const base64 = shot.split(',')[1];
  fs.writeFileSync(outputPath, Buffer.from(base64, 'base64'));
} else if (typeof shot === 'string') {
  // captureScreenshot() returns a plain filesystem path to the saved PNG.
  fs.copyFileSync(shot, outputPath);
} else if (shot && typeof shot === 'object' && shot.path) {
  fs.copyFileSync(shot.path, outputPath);
} else if (Buffer.isBuffer(shot)) {
  fs.writeFileSync(outputPath, shot);
} else {
  cliLog('UNRECOGNIZED captureScreenshot() return shape: ' + JSON.stringify(shot).slice(0, 200));
}

cliLog(JSON.stringify({ path: outputPath, legendOk }));

await completeTaskSpace(task.id, { keep: false });
EOF

rm -f "$PARAMS_FILE"

if [ -f "$WIKI_IMG_DIR/${CLEAN_NAME}.png" ]; then
    echo "📸 [ego-browser backup] Captured screenshot: $WIKI_IMG_DIR/${CLEAN_NAME}.png"
else
    echo "⚠️ [ego-browser backup] No file produced — check ego-browser output above."
fi

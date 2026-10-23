#!/usr/bin/env bash
# Batch chart screenshot capture via ego-browser (real Chromium, public
# TradingView web chart), for equity-news-finder's watchlist screenshot step.
#
# Replaces the TradingView-Desktop-CDP path (tv_session.sh + capture_tv_chart.sh)
# for THAT ONE workflow only, per user decision 2026-08-23. This is a
# deliberate tradeoff, not a strict upgrade: the Desktop app's saved chart
# layout applies a suite of custom Pine indicators (TAT levels, wash lines,
# ZigZag structure, etc.) that the public web chart opened here does NOT have
# — these captures are plain price-action charts. In exchange, this path
# avoids TradingView Desktop's CDP session entirely (no hang risk, no
# contention with the hourly TAT job or other CDP-driven work sharing that
# one app instance), and runs the whole batch as ONE ego-browser session —
# one task space, one tab reused sequentially across symbols, closed and
# reopened per symbol — rather than N separate process invocations the way
# capture_tv_chart.sh needs a fresh `node src/cli/index.js` call per symbol.
#
# All other TradingView screenshot workflows in this repo (TAT analysis,
# daily brief, D-R-H-R, active-trades review) are UNCHANGED and still use
# capture_tv_chart.sh / tv_session.sh — this script is scoped to
# equity-news-finder only.
#
# Usage: ./scripts/capture_tv_charts_egobrowser_batch.sh <symbols.json>
#   symbols.json: JSON array of objects, each:
#     {"symbol": "SGX:D05", "timeframe": "D", "outputName": "260823-090000_d05_D_chart"}
#   symbol: TradingView-form symbol (map Yahoo .SI/.HK/.KS suffixes to
#     SGX:/HSI:/KRX: prefixes yourself before calling this script).
#   timeframe: TradingView interval string (e.g. "D", "60", "240").
#   outputName: filename without extension; written to wiki/images/<outputName>.png.
#
# Output: one JSON line per symbol to stdout via cliLog:
#   [{"symbol":"SGX:D05","path":"...","legendOk":true,"captured":true}, ...]

set -e

# Note: the usage message here must avoid literal { } characters — bash's
# ${var:?message} scans for the first unescaped '}' to end the expansion,
# so a message containing its own braces silently truncates and leaks the
# rest as trailing literal text onto the assigned value (hit this for real
# while testing: "path to a JSON array of {symbol...}" broke SYMBOLS_JSON).
SYMBOLS_JSON="${1:?path to a JSON array of symbol/timeframe/outputName objects is required}"
WIKI_DIR="/Users/chriseah/obsidian/wiki-trades"
WIKI_IMG_DIR="$WIKI_DIR/wiki/images"
mkdir -p "$WIKI_IMG_DIR"

# ego-browser's `nodejs` runtime does not inherit the calling shell's
# exported env vars (verified empirically for the single-symbol variant of
# this script — only a fixed system allowlist is present in process.env
# there), so parameters are handed over via a JSON file instead.
PARAMS_FILE="/tmp/wiki-trades-ego-tv-batch-params.json"
python3 -c "
import json, sys
entries = json.load(open(sys.argv[1]))
img_dir = sys.argv[2]
out = []
for e in entries:
    clean_name = ''.join(c if (c.isalnum() or c in '._-') else '_' for c in e['outputName'])
    out.append({
        'symbol': e['symbol'],
        'timeframe': e.get('timeframe', 'D'),
        'outputPath': f'{img_dir}/{clean_name}.png',
    })
json.dump(out, open(sys.argv[3], 'w'))
" "$SYMBOLS_JSON" "$WIKI_IMG_DIR" "$PARAMS_FILE"

ego-browser nodejs <<'EOF'
const fs = await import('node:fs');
const entries = JSON.parse(fs.readFileSync('/tmp/wiki-trades-ego-tv-batch-params.json', 'utf8'));

const task = await useOrCreateTaskSpace('tv-chart-capture-batch');
const results = [];

for (const entry of entries) {
  const { symbol, timeframe, outputPath } = entry;
  const wantTicker = symbol.split(':').pop().toLowerCase();
  const url = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(timeframe)}`;

  let legendOk = false;
  let lastErr = null;
  for (let attempt = 1; attempt <= 3 && !legendOk; attempt++) {
    try {
      await openOrReuseTab(url, { wait: true, timeout: 30 });
      await waitForNetworkIdle({ timeout: 20 });
      await waitForElement('canvas', { timeout: 20 });

      // Same class of bug documented in force_tv_visible.mjs for the
      // TradingView Desktop app: an occluded/backgrounded window silently
      // throttles canvas painting while every other signal keeps reporting
      // fine. Force it active before trusting anything about to be read or
      // screenshotted.
      await cdp('Emulation.setFocusEmulationEnabled', { enabled: true });
      await cdp('Page.setWebLifecycleState', { state: 'active' });

      const info = await pageInfo();
      if (info && info.dialog) {
        await cdp('Page.handleJavaScriptDialog', { accept: true });
      }
      // Escape is a no-op when nothing is open; cheap insurance before
      // every capture.
      await pressKey('Escape');

      // Settle time for candle data to actually paint onto the canvas —
      // network idle / DOM load don't guarantee rendering has finished.
      await wait(3);

      const legendText = await js(String.raw`(() => {
        const el = document.querySelector('[data-name="legend-source-item"]')
          || document.querySelector('.pane-legend-title__wrap')
          || document.body;
        return (el && el.innerText || '').toLowerCase();
      })()`);
      legendOk = legendText.includes(wantTicker);
      if (!legendOk) await wait(1);
    } catch (err) {
      lastErr = err;
      await wait(1);
    }
  }
  if (!legendOk) {
    cliLog(`WARNING: could not confirm "${wantTicker}" in chart legend after 3 attempts${lastErr ? ' (last error: ' + lastErr.message + ')' : ''}`);
  }

  let captured = false;
  try {
    const shot = await captureScreenshot();
    if (typeof shot === 'string' && shot.startsWith('data:')) {
      const base64 = shot.split(',')[1];
      fs.writeFileSync(outputPath, Buffer.from(base64, 'base64'));
      captured = true;
    } else if (typeof shot === 'string') {
      fs.copyFileSync(shot, outputPath);
      captured = true;
    } else if (shot && typeof shot === 'object' && shot.path) {
      fs.copyFileSync(shot.path, outputPath);
      captured = true;
    } else if (Buffer.isBuffer(shot)) {
      fs.writeFileSync(outputPath, shot);
      captured = true;
    } else {
      cliLog(`UNRECOGNIZED captureScreenshot() return shape for ${symbol}: ` + JSON.stringify(shot).slice(0, 200));
    }
  } catch (err) {
    cliLog(`ERROR capturing ${symbol}: ${err.message}`);
  }

  results.push({ symbol, path: outputPath, legendOk, captured });

  // Close the tab before the next symbol rather than letting 26+ live
  // canvas-rendering chart tabs pile up for the whole batch — each tab
  // keeps repainting in the background otherwise, which is exactly the
  // kind of resource pressure that causes silent rendering throttling.
  try { await closeTab(); } catch {}
}

cliLog(JSON.stringify(results));
await completeTaskSpace(task.id, { keep: false });
EOF

rm -f "$PARAMS_FILE"

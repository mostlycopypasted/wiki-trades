#!/usr/bin/env node
// Signal Judge chart pass (docs/design/signal-judge.md §3, Revision 11 item 7).
//
//   node scripts/tv_judge_pass.mjs <request.json> <out.json>
//
// request = {"deadline_ms": <epoch ms>, "items": [{"symbol": "EIGHTCAP:GBPUSD", "timeframes": ["240", "D"]}, ...]}
//
// One process reads, for each symbol x timeframe, the chart state, the last 300 bars, the TAT
// study's labels, the study values and the quote, inside the TradingView session the caller
// (scripts/signal_judge.py) has already started with tv_session.sh. It never starts or stops
// TradingView and takes no screenshots. out.json is rewritten after every item so a kill keeps
// the partial result. Per-read errors are recorded, never thrown; a fatal error before the first
// item (CDP connect, layout switch) is written as {"fatal": ...}. Exit code is always 0.
//
// Staleness is decided in Python: this script only fingerprints each read and, when the
// fingerprint equals the previous symbol's last read (first timeframe) or the first
// timeframe's (second timeframe), waits 1500 ms and re-reads the labels and study values once.

import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const CORE = join(homedir(), 'tradingview-mcp', 'src', 'core');
const HERE = dirname(fileURLToPath(import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const [, , reqPath, outPath] = process.argv;
if (!reqPath || !outPath) {
  console.error('usage: node scripts/tv_judge_pass.mjs <request.json> <out.json>');
  process.exit(2);
}

const out = { items: {}, errors: [], fatal: null, started_at: Date.now(), finished_at: null };
function flush() {
  out.finished_at = Date.now();
  const tmp = outPath + '.tmp';
  writeFileSync(tmp, JSON.stringify(out));
  renameSync(tmp, outPath);
}

function withTimeout(p, ms, what) {
  return Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error(`${what} timed out after ${ms} ms`)), ms))]);
}

function tatStudy(labels) {
  const studies = (labels && labels.studies) || [];
  const s = studies.find((x) => String(x.name || '').startsWith('TATbyBinniOng'));
  return s ? { name: s.name, total_labels: s.total_labels, labels: s.labels || [] } : null;
}

function fingerprint(tat, indicators) {
  const vals = ((indicators && indicators.studies) || []).find((x) => String(x.name || '').startsWith('TATbyBinniOng'));
  return JSON.stringify([
    tat ? tat.total_labels : null,
    tat ? tat.labels.slice(-5).map((l) => l.text) : null,
    vals ? vals.values : null,
  ]);
}

let req;
try {
  req = JSON.parse(readFileSync(reqPath, 'utf8'));
} catch (e) {
  out.fatal = `bad request: ${e.message}`;
  flush();
  process.exit(0);
}

let chart, data, ui, forceVisible;
try {
  chart = await import(pathToFileURL(join(CORE, 'chart.js')).href);
  data = await import(pathToFileURL(join(CORE, 'data.js')).href);
  ui = await import(pathToFileURL(join(CORE, 'ui.js')).href);
  ({ forceVisible } = await import(pathToFileURL(join(HERE, 'force_tv_visible.mjs')).href));
} catch (e) {
  out.fatal = `setup failed: ${e.message}`;
  flush();
  process.exit(0);
}

// tv_session.sh start has already switched to and confirmed the TAW layout; this second switch is
// a belt-and-braces check, so a failure here (e.g. getSavedCharts timing out) is recorded, not fatal.
try {
  await withTimeout(ui.layoutSwitch({ name: '0 TAW Layout' }), 60000, 'layoutSwitch');
  await sleep(2000);
} catch (e) {
  out.errors.push({ symbol: null, tf: null, error: `layoutSwitch (non-fatal): ${e.message}` });
}

async function readLabelsAndValues() {
  const labels = await withTimeout(data.getPineLabels({ study_filter: 'TAT', max_labels: 500 }), 30000, 'getPineLabels');
  const indicators = await withTimeout(data.getStudyValues(), 30000, 'getStudyValues');
  const tat = tatStudy(labels);
  return { tat, indicators, fp: fingerprint(tat, indicators) };
}

let prevFp = null; // last read of the previous symbol
for (const item of req.items || []) {
  if (Date.now() > req.deadline_ms) break;
  const sym = item.symbol;
  out.items[sym] = {};
  try {
    await withTimeout(forceVisible(), 10000, 'forceVisible');
  } catch (e) {
    out.errors.push({ symbol: sym, tf: null, error: `forceVisible: ${e.message}` });
  }
  const ticker = sym.split(':').pop().toUpperCase();
  const onSymbol = async () => String((await withTimeout(chart.getState(), 15000, 'getState')).symbol || '').toUpperCase().endsWith(ticker);
  try {
    await withTimeout(chart.setSymbol({ symbol: sym }), 30000, 'setSymbol');
    if (!(await onSymbol())) {  // setSymbol can return without switching (seen 2026-11-04 right after start)
      await sleep(1500);
      await withTimeout(chart.setSymbol({ symbol: sym }), 30000, 'setSymbol retry');
      await sleep(1000);
    }
  } catch (e) {
    out.errors.push({ symbol: sym, tf: null, error: `setSymbol: ${e.message}` });
    flush();
    continue;
  }
  let firstFp = null;
  let lastFp = null;
  for (const [i, tf] of (item.timeframes || []).entries()) {
    try {
      await withTimeout(chart.setTimeframe({ timeframe: tf }), 30000, 'setTimeframe');
      await sleep(900);
      let state = await withTimeout(chart.getState(), 15000, 'getState');
      let retriedTf = false;
      const okRes = (r) => String(r) === tf || (tf === 'D' && String(r) === '1D');
      if (!okRes(state.resolution)) {
        retriedTf = true;
        await withTimeout(chart.setTimeframe({ timeframe: tf }), 30000, 'setTimeframe retry');
        await sleep(1500);
        state = await withTimeout(chart.getState(), 15000, 'getState');
      }
      const ohlcv = await withTimeout(data.getOhlcv({ count: 300 }), 30000, 'getOhlcv');
      let lv = await readLabelsAndValues();
      // The TAT study may still be calculating after a symbol/timeframe switch: no labels and no
      // trend values yet (seen 2026-11-04 on the first 1H read). Wait and re-read, up to twice.
      const tatReady = (x) => x.tat && ((x.indicators && x.indicators.studies) || []).some((s) => String(s.name || '').startsWith('TATbyBinniOng'));
      let tatRetries = 0;
      while (!tatReady(lv) && tatRetries < 2) {
        tatRetries += 1;
        await sleep(2000);
        lv = await readLabelsAndValues();
      }
      const compareTo = i === 0 ? prevFp : firstFp;
      let relabel = false;
      if (compareTo !== null && lv.fp === compareTo) {
        relabel = true;
        await sleep(1500);
        lv = await readLabelsAndValues();
      }
      const quote = await withTimeout(data.getQuote({}), 15000, 'getQuote');
      out.items[sym][tf] = {
        state: { symbol: state.symbol, resolution: state.resolution },
        bars: (ohlcv && ohlcv.bars) || [],
        tat: lv.tat,
        indicators: lv.indicators,
        quote,
        read_at: Date.now(),
        retried_tf: retriedTf,
        relabel_retry: relabel,
        tat_retries: tatRetries,
        fingerprint: lv.fp,
      };
      if (i === 0) firstFp = lv.fp;
      lastFp = lv.fp;
    } catch (e) {
      out.errors.push({ symbol: sym, tf, error: e.message });
    }
  }
  if (lastFp !== null) prevFp = lastFp;
  flush();
}

flush();
process.exit(0);

/* Trade Terminal — single-page app over /api/*. No build step, no framework. */
'use strict';

// ============================================================ utilities
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
  }
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

const store = {
  get(k, d) { try { const v = localStorage.getItem('desk.' + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('desk.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};

const SGT_FMT = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Singapore', year: 'numeric', month: '2-digit', day: '2-digit' });
const sgtToday = () => SGT_FMT.format(new Date());
function addDays(d, n) {
  const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10);
}
const dow = d => new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' });
const shortDate = d => d ? d.slice(5) : '';
const niceDate = d => d ? `${dow(d)} ${new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}` : '';
const evTime = e => new Date(`${e.date}T${(e.time || '00:00').padStart(5, '0')}:00+08:00`);
function until(ms) {
  if (ms < 0) return 'passed';
  const m = Math.floor(ms / 60000), d = Math.floor(m / 1440), hh = Math.floor((m % 1440) / 60), mm = m % 60;
  return d ? `${d}d ${hh}h` : hh ? `${hh}h ${mm}m` : `${mm}m`;
}
function tokens(q) { return (q || '').toLowerCase().split(/\s+/).filter(Boolean); }
function matches(q, ...fields) {
  const t = tokens(q); if (!t.length) return true;
  const hay = fields.flat().filter(Boolean).join(' ').toLowerCase();
  return t.every(x => hay.includes(x));
}
const DIR_LABEL = { bull: '▲ Bull', bear: '▼ Bear', neutral: '● Neutral' };
const dirBadge = d => h('span', { class: `dir ${d || 'neutral'}` }, DIR_LABEL[d] || DIR_LABEL.neutral);
const symChip = (sym, dir) => h('a', { class: `sym ${dir || ''}`, dataset: { sym }, title: `Open ${sym}` }, sym);
const sigClass = sig => /bull/i.test(sig) ? 'bull' : /bear/i.test(sig) ? 'bear' : '';
const sigSpan = sig => h('span', { class: `sig ${sigClass(sig)}` }, sig || '—');
const impactBadge = lvl => h('span', { class: `impact ${lvl}` }, h('i'), lvl);
const card = (title, right, ...body) => h('div', { class: 'card' }, h('h2', null, title, right ? h('span', { class: 'right' }, right) : null), ...body);
const empty = msg => h('div', { class: 'empty' }, msg);
function seg(options, value, onChange, opts = {}) {
  // options: [{v, label, cls}] ; value: single value or Set when opts.multi
  return h('div', { class: 'seg', role: 'group' }, options.map(o => {
    const on = opts.multi ? value.has(o.v) : value === o.v;
    return h('button', {
      class: `${on ? 'on' : ''} ${o.cls || ''}`, type: 'button', 'aria-pressed': on ? 'true' : 'false',
      onclick: () => {
        if (opts.multi) { const n = new Set(value); n.has(o.v) ? n.delete(o.v) : n.add(o.v); if (n.size || opts.allowEmpty) onChange(n); }
        else onChange(o.v);
      },
    }, o.label);
  }));
}
function toast(msg) {
  const t = h('div', { class: 'toast' }, msg); document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}

// ============================================================ data
const cache = {};
async function api(path, { fresh = false } = {}) {
  if (!fresh && cache[path]) return cache[path];
  const p = fetch(path).then(r => r.ok ? r.json() : null).catch(() => null);
  cache[path] = p;
  const v = await p;
  if (v === null) delete cache[path];
  return v;
}

const S = {
  view: 'desk',
  q: '',
  meta: null,
  sig: null,           // {status, rows}
  f: store.get('filters', {}),
};
const F = (name, defaults) => (S.f[name] = Object.assign({}, defaults, S.f[name] || {}));
function saveFilters() {
  const plain = {};
  for (const [k, v] of Object.entries(S.f)) {
    plain[k] = {};
    for (const [kk, vv] of Object.entries(v)) plain[k][kk] = vv instanceof Set ? [...vv] : vv;
  }
  store.set('filters', plain);
}
const asSet = (v, d) => v instanceof Set ? v : new Set(Array.isArray(v) ? v : d);

async function loadSignals(force = false) {
  const res = await api('/api/signals' + (force ? '?refresh=1' : ''), { fresh: true });
  if (res) S.sig = res;
  updateSheetStatus();
  return S.sig;
}
function updateSheetStatus() {
  const st = S.sig && S.sig.status, dot = $('#sheetDot'), lbl = $('#sheetLbl');
  if (!st) { dot.className = 'dot busy'; lbl.textContent = 'Loading alerts…'; return; }
  if (st.loading && !st.fetchedAt) { dot.className = 'dot busy'; lbl.textContent = 'Loading alerts…'; return; }
  if (st.error && !st.rows) { dot.className = 'dot err'; lbl.textContent = 'Sheet unavailable'; dot.title = st.error; return; }
  dot.className = st.error ? 'dot err' : 'dot ok';
  const t = st.fetchedAt ? new Date(st.fetchedAt * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Singapore' }) : '—';
  lbl.textContent = `${st.rows.toLocaleString()} alerts · ${t} SGT`;
  dot.title = st.error || `Tabs: ${Object.entries(st.tabs || {}).map(([k, v]) => `${k} ${v}`).join(', ')}`;
}
const sigRows = () => (S.sig && S.sig.rows) || [];

// ============================================================ markdown
function renderMd(md, basePath) {
  let src = (md || '')
    .replace(/<!-- TOC:START -->[\s\S]*?<!-- TOC:END -->/g, '')
    .replace(/^---\n[\s\S]*?\n---\n/, '')
    .replace(/\[\[#[^\]]*\]\]/g, '')
    .replace(/`\[\[([^\]|#]+?)\]\]`/g, '[[$1]]')
    .replace(/\[\[([^\]|#]+?)(?:\|([^\]]+))?\]\]/g, (m, s, l) => {
      const sym = s.trim().toUpperCase().replace(/[^A-Z0-9._-]/g, '');
      return `<a class="sym" data-sym="${sym}">${(l || s).replace(/[<>&"]/g, '')}</a>`;
    });
  const box = h('div', { class: 'md' });
  if (window.marked && window.DOMPurify) {
    box.innerHTML = DOMPurify.sanitize(marked.parse(src, { gfm: true }));
  } else {
    box.appendChild(h('pre', null, md));
    return box;
  }
  const baseDir = (basePath || '').split('/').slice(0, -1);
  box.querySelectorAll('img').forEach(img => {
    const raw = img.getAttribute('src') || '';
    if (raw.includes('images/')) img.src = '/images/' + raw.split('/').pop();
    img.loading = 'lazy';
    img.dataset.full = img.src;
    img.dataset.cap = img.alt || '';
  });
  box.querySelectorAll('a[href]').forEach(a => {
    const href = a.getAttribute('href');
    if (/^https?:/.test(href)) { a.target = '_blank'; a.rel = 'noopener'; return; }
    if (/\.md(#.*)?$/.test(href)) {
      const parts = baseDir.slice();
      for (const seg of decodeURIComponent(href.replace(/#.*$/, '')).split('/')) {
        if (seg === '..') parts.pop(); else if (seg && seg !== '.') parts.push(seg);
      }
      a.dataset.doc = parts.join('/');
      a.removeAttribute('href'); a.style.cursor = 'pointer';
    }
  });
  return box;
}

function highlight(root, q) {
  const t = tokens(q).filter(x => x.length >= 2);
  if (!t.length) return 0;
  const re = new RegExp('(' + t.map(x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => n.parentElement.closest('mark,script,style') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
  let n = 0;
  for (const node of nodes) {
    if (!re.test(node.nodeValue)) continue;
    re.lastIndex = 0;
    const frag = document.createDocumentFragment();
    node.nodeValue.split(re).forEach((part, i) => {
      if (i % 2) { frag.appendChild(h('mark', null, part)); n++; } else if (part) frag.appendChild(document.createTextNode(part));
    });
    node.parentNode.replaceChild(frag, node);
  }
  return n;
}

async function openDoc(path, title) {
  const doc = await api('/api/doc?path=' + encodeURIComponent(path));
  if (!doc) { toast('Wiki page not found: ' + path); return; }
  $('#mTitle').textContent = title || path;
  const body = renderMd(doc.md, doc.path);
  $('#mBody').replaceWith(Object.assign(body, { id: 'mBody' }));
  if (S.q) highlight(body, S.q);
  $('#modal').classList.add('show'); $('#scrim').classList.add('show');
  $('#modal .mb').scrollTop = 0;
}

let lbGroup = [], lbIdx = 0, lbAuto = null, lbAutoT = null;
// Lightbox: a horizontal scroll-snap track (one slide per chart) plus a thumbnail strip.
// Scrolling the track (swipe, trackpad, wheel, drag) or tapping a thumbnail moves between charts.
function lightbox(src, cap, group, idx) {
  lbGroup = group || [{ full: src, cap }]; lbIdx = idx || 0;
  const multi = lbGroup.length > 1;
  $('#lightbox').classList.toggle('multi', multi);
  $('#lbTrack').replaceChildren(...lbGroup.map((it, i) => h('div', { class: 'lbslide' },
    h('img', { src: it.full, alt: it.cap || '', loading: Math.abs(i - lbIdx) <= 1 ? 'eager' : 'lazy', draggable: 'false' }))));
  $('#lbStrip').replaceChildren(...(multi ? lbGroup.map((it, i) => h('button', { class: 'lbthumb', type: 'button', title: it.cap || '', dataset: { lbto: i } },
    h('img', { src: it.thumb || it.full, alt: '', loading: 'lazy', draggable: 'false' }),
    h('span', null, (it.cap || '').split(' · ')[0]))) : []));
  $('#lightbox').classList.add('show');
  lbGo(lbIdx, false);
}
function lbGo(i, smooth = true) {
  if (!lbGroup.length) return;
  const to = Math.max(0, Math.min(lbGroup.length - 1, i));
  if (Math.abs(to - lbIdx) > 2) smooth = false;   // long jumps (thumbnail taps) snap; neighbours glide
  lbIdx = to;
  const tr = $('#lbTrack');
  lbAuto = smooth ? lbIdx : null;   // a programmatic smooth scroll is in flight: don't re-sync mid-way
  clearTimeout(lbAutoT); lbAutoT = setTimeout(() => { lbAuto = null; }, 1200);
  tr.scrollTo({ left: lbIdx * tr.clientWidth, behavior: smooth ? 'smooth' : 'instant' });
  lbShow();
}
function lbShow() {
  const it = lbGroup[lbIdx];
  $('#lbCap').textContent = (it.cap || '') + (lbGroup.length > 1 ? `  (${lbIdx + 1}/${lbGroup.length})` : '');
  const strip = $('#lbStrip');
  strip.querySelectorAll('.lbthumb').forEach((b, i) => b.classList.toggle('on', i === lbIdx));
  const on = strip.children[lbIdx];
  if (on) strip.scrollTo({ left: on.offsetLeft - (strip.clientWidth - on.offsetWidth) / 2, behavior: 'smooth' });
}
function lbStep(d) {
  if (lbGroup.length < 2) return;
  lbGo((lbIdx + d + lbGroup.length) % lbGroup.length);
}

// ============================================================ shared computations
const TF_SRC = { '1H': '1H', '4H': '4H', 'D': 'Daily', 'BATS': 'TV Stocks', 'YBULL': 'Yahoo Bull', 'YBEAR': 'Yahoo Bear' };
const SERIES_BULL = { key: 'bull', name: '▲ Bull', color: 'var(--bull)' };
const SERIES_BEAR = { key: 'bear', name: '▼ Bear', color: 'var(--bear)' };
const SERIES_NEU = { key: 'neutral', name: '● Neutral / watch', color: 'var(--neutral)' };
const CCY_ORDER = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF'];
const CCY_COLOR = Object.fromEntries(CCY_ORDER.map((c, i) => [c, `var(--s${i + 1})`]));

function symCurrencies(sym) {
  const s = sym.toUpperCase();
  const cc = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF', 'SGD', 'CNH', 'HKD'];
  if (s.length === 6 && cc.includes(s.slice(0, 3)) && cc.includes(s.slice(3))) return [s.slice(0, 3), s.slice(3)];
  if (/^X(AU|AG|PT|PD|CU)/.test(s)) return [s.slice(3)];
  if (s === 'DXY') return ['USD'];
  return [];
}

function dayBuckets(rows, days) {
  const map = new Map(days.map(d => [d, { bull: 0, bear: 0, neutral: 0 }]));
  for (const r of rows) { const b = map.get(r.date); if (b) b[r.dir] = (b[r.dir] || 0) + 1; }
  return days.map(d => ({ label: shortDate(d), tip: niceDate(d), date: d, values: map.get(d) }));
}
function dateSpan(from, to) { const out = []; for (let d = from; d <= to; d = addDays(d, 1)) out.push(d); return out; }

// Latest signal per (symbol, source) — the "current state" of each timeframe.
function latestBySymbol(rows) {
  const out = {};
  for (const r of rows) { // rows are newest-first
    const o = out[r.sym] || (out[r.sym] = {});
    if (!o[r.src]) o[r.src] = r;
  }
  return out;
}
function alignment(state) {
  const tfs = ['D', '4H', '1H'].map(k => state[k]).filter(Boolean);
  if (!tfs.length) return { dir: 'neutral', n: 0 };
  const newest = tfs.slice().sort((a, b) => (b.date + b.time).localeCompare(a.date + a.time))[0];
  return { dir: newest.dir, n: tfs.filter(r => r.dir === newest.dir).length, total: tfs.length };
}

// ============================================================ views: DESK
async function viewDesk(root) {
  const [brief, hist, cal, cb, tat, ahh, news] = await Promise.all([
    api('/api/brief'), api('/api/strength-history'), api('/api/calendar'), api('/api/cb'), api('/api/tat-latest'), api('/api/ahh'), api('/api/news'),
  ]);
  const q = S.q, rows = sigRows(), today = sgtToday();
  const tfRows = rows.filter(r => ['1H', '4H', 'D'].includes(r.src));
  const lastDay = tfRows.some(r => r.date === today) ? today : (tfRows[0] && tfRows[0].date);
  const dayRows = tfRows.filter(r => r.date === lastDay);
  const cnt = src => dayRows.filter(r => r.src === src).length;
  const nBull = dayRows.filter(r => r.dir === 'bull').length, nBear = dayRows.filter(r => r.dir === 'bear').length;

  const now = Date.now();
  const nextHigh = ((cal && cal.events) || []).filter(e => e.impact === 'High' && evTime(e) > now).sort((a, b) => evTime(a) - evTime(b))[0];
  const scores = (brief && brief.scores) || [];
  const strong = scores[0], weak = scores[scores.length - 1];
  const topSetup = tat && tat.setups && tat.setups.find(s => s.bucket === 'dual');
  const latestNote = (ahh || []).find(n => n.ideas.length);

  const kpi = (lbl, val, foot, onclick, small) => h('div', { class: `kpi ${onclick ? 'click' : ''}`, onclick },
    h('div', { class: 'lbl' }, lbl), h('div', { class: `val ${small ? 'sm' : ''}` }, val), h('div', { class: 'foot' }, foot));

  root.replaceChildren(
    h('div', { class: 'view-head' }, h('h1', null, 'Trade Terminal'), h('span', { class: 'sub' }, `${niceDate(today)} · SGT`)),
    h('div', { class: 'kpis' },
      kpi(`Signals ${lastDay === today ? 'today' : shortDate(lastDay) || ''}`,
        h('span', null, h('span', { style: { color: 'var(--bull-ink)' } }, `▲${nBull}`), ' ', h('span', { style: { color: 'var(--bear-ink)' } }, `▼${nBear}`)),
        rows.length ? `1H ${cnt('1H')} · 4H ${cnt('4H')} · D ${cnt('D')}` : 'Loading alert sheet…', () => go('signals')),
      kpi('Next high-impact', nextHigh ? `${nextHigh.ccy} ${nextHigh.event}` : '—',
        nextHigh ? `in ${until(evTime(nextHigh) - now)} · ${shortDate(nextHigh.date)} ${nextHigh.time}` : 'None scheduled', () => go('calendar'), true),
      kpi('Strongest / weakest', strong ? `${strong.ccy} ${strong.score > 0 ? '+' : ''}${strong.score} / ${weak.ccy} ${weak.score}` : '—',
        brief ? `Currency strength · ${brief.date}` : '', () => go('brief'), true),
      kpi('Top TAT setup', topSetup ? h('span', null, topSetup.syms.join(' & '), ' ', dirBadge(topSetup.dir)) : '—',
        tat ? `${topSetup ? topSetup.title || topSetup.text : ''} · ${tat.date} ${tat.time}` : '', () => go('analysis'), true),
      kpi('Latest session', latestNote ? `${latestNote.session}` : '—',
        latestNote ? `${latestNote.date} · ${latestNote.ideas.length} ideas` : '', () => go('ahh'), true),
    ),
  );

  const dg = h('div', { class: 'desk-grid' }); root.appendChild(dg);
  const put = (el, span) => { el.classList.add(span); dg.appendChild(el); return el; };
  const nCard = put(newsCard(news), 'span-7'); nCard.classList.add('scroll');

  // currency strength + trend
  const csCard = card('Currency strength', brief ? `Daily brief ${brief.date}` : '');
  const trendCard = card('Strength trend', hist ? `${Math.min(hist.length, 25)} briefs` : '');
  const csBox = h('div'); csCard.appendChild(csBox);
  Charts.diverging(csBox, scores.map(s => ({ label: s.ccy, value: s.score, tip: s.bias })), {
    aria: 'Currency strength scores', onClick: d => { setQuery(d.label); go('signals'); },
  });
  csCard.appendChild(h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Click a currency to see its TAT signals.'));
  const H = (hist || []).slice(-25);
  const tBox = h('div'); trendCard.appendChild(tBox);
  Charts.lines(tBox, H.map(x => shortDate(x.date)), CCY_ORDER.map(c => ({ name: c, color: CCY_COLOR[c], values: H.map(x => x.scores[c] ?? null) })),
    { aria: 'Currency strength history', tipLabel: i => niceDate(H[i].date) });

  // signal flow + latest setups
  const fd = F('desk', { flow: '1H' });
  const flowCard = card('Signal flow · 14 days', seg([{ v: '1H', label: '1H' }, { v: '4H', label: '4H' }, { v: 'D', label: 'Daily' }, { v: 'STK', label: 'Stocks' }],
    fd.flow, v => { fd.flow = v; saveFilters(); render(); }));
  const fbox = h('div'); flowCard.appendChild(fbox);
  const srcs = fd.flow === 'STK' ? ['BATS', 'YBULL', 'YBEAR'] : [fd.flow];
  const flowRows = rows.filter(r => srcs.includes(r.src) && matches(q, r.sym, r.name, r.signal, r.event, r.sector));
  Charts.stacked(fbox, dayBuckets(flowRows, dateSpan(addDays(today, -13), today)), [SERIES_BULL, SERIES_BEAR], {
    aria: 'Signals per day', onClick: d => { const f = F('signals', {}); f.range = 'custom'; f.day = d.date; f.srcs = srcs; saveFilters(); go('signals'); },
  });
  if (!rows.length) fbox.prepend(empty('Waiting for the alert sheet…'));

  const setups = ((tat && tat.setups) || []).filter(s => matches(q, s.syms, s.title, s.text, s.detail));
  const setCard = card('Latest TAT setups', tat ? h('a', { onclick: () => go('analysis') , style: { cursor: 'pointer' } }, `${tat.date} · ${tat.time} SGT →`) : '');
  setCard.appendChild(setups.length ? h('div', { class: 'list', style: { maxHeight: '300px', overflowY: 'auto' } }, setups.map(setupLi)) : empty('No setups in latest run'));

  // events, pairs/drhr, ahh
  const upcoming = ((cal && cal.events) || []).filter(e => e.impact !== 'Low' && evTime(e) > now - 3600e3 && evTime(e) < now + 3 * 864e5)
    .filter(e => matches(q, e.ccy, e.event)).sort((a, b) => evTime(a) - evTime(b));
  const evCard = card('Upcoming events · 72h', h('a', { onclick: () => go('calendar'), style: { cursor: 'pointer' } }, 'Calendar →'));
  evCard.appendChild(upcoming.length ? h('div', { class: 'list' }, upcoming.slice(0, 10).map(e => h('div', { class: 'li' },
    h('div', { class: 'body' },
      h('div', { class: 't' }, impactBadge(e.impact), h('span', { class: 'tag' }, e.ccy), e.event),
      h('div', { class: 'm' }, `${niceDate(e.date)} ${e.time} SGT · in ${until(evTime(e) - now)}`, e.forecast ? ` · F ${e.forecast}` : '', e.previous ? ` · P ${e.previous}` : '', e.actual ? ` · A ${e.actual}` : '')))))
    : empty('No medium/high events in the next 72h'));

  const pairs = ((brief && brief.pairs) || []).filter(p => matches(q, p.sym));
  const pCard = card('Suggested pairs', brief ? brief.date : '');
  pCard.appendChild(pairs.length ? h('div', null,
    h('div', { class: 'small muted' }, 'Structure-aligned (score gap ≥4)'),
    h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '8px 0 12px' } },
      pairs.map(p => h('span', { style: { display: 'inline-flex', gap: '4px', alignItems: 'center' } }, symChip(p.sym, p.dir), h('span', { class: `dir ${p.dir}` }, `${p.dir === 'bull' ? '▲ Buy' : '▼ Sell'} ${p.diff}`)))))
    : empty('No suggestions'));
  const drhr = ((brief && brief.drhr) || []).filter(d => matches(q, d.sym, d.label, d.detail));
  if (drhr.length) {
    pCard.appendChild(h('div', { class: 'small muted' }, 'D-R-H-R reversal setups'));
    pCard.appendChild(h('div', { class: 'list' }, drhr.map(d => h('div', { class: 'li' }, h('div', { class: 'body' },
      h('div', { class: 't' }, symChip(d.sym, d.dir), dirBadge(d.dir), h('span', { class: 'small' }, d.label)),
      h('div', { class: 'm' }, d.detail.join(' · ')))))));
  }

  const ideas = latestNote ? latestNote.ideas.filter(i => matches(q, i.title, i.syms, i.direction, i.levels, i.setup)) : [];
  const aCard = card('Latest session ideas', latestNote ? h('a', { onclick: () => go('ahh'), style: { cursor: 'pointer' } }, `${latestNote.session} ${latestNote.date} →`) : '');
  aCard.appendChild(ideas.length ? h('div', { class: 'list' }, ideas.slice(0, 8).map(i => h('div', { class: 'li' }, h('div', { class: 'body' },
    h('div', { class: 't' }, i.syms.slice(0, 3).map(s => symChip(s, i.dir)), dirBadge(i.dir)),
    h('div', { class: 'd' }, i.direction), i.levels ? h('div', { class: 'm' }, 'Levels: ' + i.levels) : null)))) : empty('No ideas match'));

  evCard.classList.add('scroll'); setCard.classList.add('scroll');
  put(evCard, 'span-5');
  put(csCard, 'span-4'); put(trendCard, 'span-4'); put(flowCard, 'span-4');
  put(setCard, 'span-4'); put(pCard, 'span-4'); put(aCard, 'span-4');
  if (cb && cb.stances.length) put(cbCard(cb), 'span-8');
  const fedHolder = put(card('Fed rate odds', 'loading…', empty('Fetching FedWatch…')), 'span-4');
  api('/api/fedwatch').then(fw => {  // slow when OpenD is cold, so don't hold the whole desk for it
    if (!fedHolder.isConnected) return;
    const c = fedCard(fw); c.classList.add('span-4'); fedHolder.replaceWith(c);
  });
}

function newsCard(news) {
  const fd = F('news', { range: 7, all: false, tab: 'watch' });
  const names = (news && news.names) || {};
  const bare = sym => sym.replace(/\.[A-Z]+$/, '');
  const ago = ms => ms < 3600e3 ? `${Math.max(1, Math.round(ms / 60000))}m ago` : ms < 86400e3 ? `${Math.round(ms / 3600e3)}h ago` : `${Math.round(ms / 86400e3)}d ago`;
  const now = Date.now(), mkt = fd.tab === 'market';
  const src = (mkt ? news && news.market : news && news.items) || [];
  const all = src.filter(i => now - i.ts * 1000 < fd.range * 864e5 &&
    (mkt ? matches(S.q, i.title, i.topics) : matches(S.q, i.title, i.syms, i.syms.map(x => names[x]))));
  const shown = fd.all ? all : all.slice(0, 20);
  const right = h('span', { style: { display: 'inline-flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } },
    seg([{ v: 'watch', label: 'Watchlist' }, { v: 'market', label: 'Latest' }], fd.tab, v => { fd.tab = v; fd.all = false; saveFilters(); render(); }),
    seg([{ v: 1, label: '24h' }, { v: 3, label: '3d' }, { v: 7, label: '7d' }, { v: 30, label: '30d' }].filter(o => !mkt || o.v <= 7), Math.min(fd.range, mkt ? 7 : 30), v => { fd.range = v; saveFilters(); render(); }),
    news && news.fetchedAt ? h('span', { class: 'small muted' }, `moomoo · ${news.fetchedAt.slice(5, 16).replace('T', ' ')} SGT`) : null);
  const c = card(mkt ? 'Latest market news' : 'Watchlist news', right);
  c.dataset.news = '1';
  if (!news || !news.items) { c.appendChild(empty('News unavailable — moomoo could not be reached')); return c; }
  if (news.error) c.appendChild(h('div', { class: 'small muted' }, `Showing last good pull — refresh failed: ${news.error}`));
  c.appendChild(shown.length ? h('div', { class: 'list' }, shown.map(i => h('div', { class: 'li' }, h('div', { class: 'body' },
    mkt ? h('div', { class: 't' }, (i.topics || []).slice(0, 3).map(x => h('span', { class: 'tag' }, x)))
        : h('div', { class: 't' }, i.syms.slice(0, 3).map(x => symChip(bare(x))), h('span', { class: 'tag' }, i.syms.map(x => names[x] || x).slice(0, 2).join(' · '))),
    h('div', { class: 'd' }, h('a', { href: i.url, target: '_blank', rel: 'noopener noreferrer' }, i.title)),
    h('div', { class: 'm' }, `${ago(now - i.ts * 1000)} · ${i.time} SGT · ${i.source}`)))))
    : empty(`No headlines in the last ${fd.range === 1 ? '24h' : fd.range + 'd'}`));
  if (all.length > 20) c.appendChild(h('a', { class: 'small', style: { cursor: 'pointer', display: 'inline-block', marginTop: '8px' },
    onclick: () => { fd.all = !fd.all; saveFilters(); render(); } }, fd.all ? 'Show fewer' : `Show all ${all.length}`));
  c.appendChild(h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Compiled from public information; not investment advice.'));
  return c;
}

function setupLi(s) {
  const detail = h('div', { class: 'd clamp' }, s.text || '', s.detail.length ? h('ul', { style: { margin: '4px 0 0', paddingLeft: '18px' } }, s.detail.map(d => h('li', null, d))) : null);
  return h('div', { class: 'li' }, h('div', { class: 'body' },
    h('div', { class: 't' }, s.syms.map(x => symChip(x, s.dir)), dirBadge(s.dir),
      h('span', { class: 'tag' }, s.bucket === 'dual' ? '⭐⭐⭐ 4H+1H' : '🔄 Retest')),
    s.title ? h('div', { class: 'd' }, s.title) : null,
    (s.text || s.detail.length) ? detail : null,
    (s.text || s.detail.length) ? h('a', { class: 'small', style: { cursor: 'pointer' }, onclick: e => { detail.classList.toggle('open'); e.target.textContent = detail.classList.contains('open') ? 'Less' : 'More'; } }, 'More') : null));
}

function fedCard(fw) {
  const c = card('Fed rate odds', fw && fw.fetchedAt ? `moomoo FedWatch · ${fw.fetchedAt.slice(5, 16).replace('T', ' ')} SGT` : '');
  if (!fw || !fw.meetings || !fw.meetings.length) {
    c.appendChild(empty(fw && fw.error ? `FedWatch unavailable — ${fw.error}` : 'FedWatch unavailable — is moomoo OpenD running?'));
    return c;
  }
  if (fw.error) c.appendChild(h('div', { class: 'small muted' }, `Showing last good pull — refresh failed: ${fw.error}`));
  const next = fw.meetings[0];
  c.appendChild(h('div', { style: { margin: '2px 10px 8px' } },
    h('span', { class: 'small muted' }, `Next FOMC ${next.date} · vs current ${fw.base}${fw.baseInferred ? ' (inferred)' : ''}`), h('br'),
    h('span', { style: { fontSize: '20px', fontWeight: 700, color: next.hike >= 50 ? 'var(--hawk)' : 'var(--text)' } }, `${next.hike.toFixed(1)}%`),
    h('span', { class: 'small muted' }, ' hike · '), h('b', null, `${next.hold.toFixed(1)}%`), h('span', { class: 'small muted' }, ' hold'),
    next.cut ? h('span', { class: 'small muted' }, ` · ${next.cut.toFixed(1)}% cut`) : null));
  const bar = pct => ({ width: `${pct}%` });
  c.appendChild(h('div', null, fw.meetings.slice(0, 8).map(m => h('div', { class: 'hbar', style: { gridTemplateColumns: '64px 1fr 122px' },
    title: m.ranges.map(r => `${r.range}: ${r.p}%`).join('\n') },
    h('span', { class: 'small' }, m.date.slice(2)),
    h('div', { class: 'bars', style: { background: 'var(--surface-3)' } },
      m.cut ? h('i', { style: { ...bar(m.cut), background: 'var(--dove)' } }) : null,
      m.hold ? h('i', { style: { ...bar(m.hold), background: 'var(--neutral)' } }) : null,
      m.hike ? h('i', { style: { ...bar(m.hike), background: 'var(--hawk)' } }) : null),
    h('span', { class: 'num small', style: { whiteSpace: 'nowrap' } }, `${m.hike.toFixed(0)}% hike · ${m.move_bp >= 0 ? '+' : ''}${m.move_bp}bp`)))));
  c.appendChild(h('div', { class: 'legend' },
    h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--neutral)' } }), 'Hold'),
    h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--hawk)' } }), 'Hike'),
    h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--dove)' } }), 'Cut')));
  c.appendChild(h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Market-implied probability of any hike by that meeting, and expected cumulative move vs the current range. Hover a row for the range split.'));
  return c;
}

function cbCard(cb) {
  return card('Central bank tally', `updated ${cb.updated || '—'}`, h('div', { class: 'cbgrid' }, cb.stances.map(s =>
    h('div', { class: `cb ${s.lean}`, title: s.trigger },
      h('div', { class: 'bk' }, s.bank, ' ', h('span', { class: 'small muted' }, s.lean === 'hawk' ? '▲ hawk' : s.lean === 'dove' ? '▼ dove' : '● hold')),
      h('div', { class: 'st' }, s.stance),
      h('div', { class: 'nx' }, s.next && s.next.when ? `Next: ${s.next.when}` : `Changed ${s.changed}`)))));
}

// ============================================================ views: SIGNALS
async function viewSignals(root) {
  const f = F('signals', { range: '7d', srcs: ['1H', '4H', 'D'], dir: 'all', kinds: ['Opt', 'L', 'S'], cls: 'all', ccy: 'all', shown: 200 });
  f.srcs = asSet(f.srcs); f.kinds = asSet(f.kinds);
  const today = sgtToday(), q = S.q, rows = sigRows();
  const start = { today: today, '3d': addDays(today, -2), '7d': addDays(today, -6), '30d': addDays(today, -29), all: '0000' }[f.range];
  const inRange = r => f.range === 'custom' ? r.date === f.day : r.date >= start;
  const kind = sig => /^opt/i.test(sig) ? 'Opt' : /^l/i.test(sig) ? 'L' : /^s/i.test(sig) ? 'S' : 'Opt';
  const filtered = rows.filter(r => f.srcs.has(r.src) && inRange(r) && (f.dir === 'all' || r.dir === f.dir) && f.kinds.has(kind(r.signal))
    && (f.cls === 'all' || r.cls === f.cls) && (f.ccy === 'all' || symCurrencies(r.sym).includes(f.ccy))
    && matches(q, r.sym, r.name, r.signal, r.event, r.sector, r.srcLabel));

  const upd = fn => () => { fn(); f.shown = 200; saveFilters(); render(); };
  const classes = ['all', ...new Set(rows.map(r => r.cls))].sort();
  root.replaceChildren(
    h('div', { class: 'view-head' }, h('h1', null, 'TAT Signals'), h('span', { class: 'sub' }, 'Live from the TAT alert Google Sheet')),
    h('div', { class: 'filters' },
      h('span', { class: 'flabel' }, 'Range'),
      seg([{ v: 'today', label: 'Today' }, { v: '3d', label: '3D' }, { v: '7d', label: '7D' }, { v: '30d', label: '30D' }, { v: 'all', label: 'All' }]
        .concat(f.range === 'custom' ? [{ v: 'custom', label: niceDate(f.day) }] : []), f.range, v => upd(() => { f.range = v; })()),
      h('span', { class: 'flabel' }, 'Source'),
      seg(Object.entries(TF_SRC).map(([v, label]) => ({ v, label })), f.srcs, v => upd(() => { f.srcs = v; })(), { multi: true }),
      h('span', { class: 'flabel' }, 'Dir'),
      seg([{ v: 'all', label: 'All' }, { v: 'bull', label: '▲ Bull', cls: 'bull' }, { v: 'bear', label: '▼ Bear', cls: 'bear' }], f.dir, v => upd(() => { f.dir = v; })()),
      h('span', { class: 'flabel' }, 'Signal'),
      seg([{ v: 'Opt', label: 'Opt' }, { v: 'L', label: 'Large' }, { v: 'S', label: 'Small' }], f.kinds, v => upd(() => { f.kinds = v; })(), { multi: true }),
      h('select', { onchange: e => upd(() => { f.cls = e.target.value; })(), 'aria-label': 'Asset class' },
        classes.map(c => h('option', { value: c, selected: c === f.cls ? true : null }, c === 'all' ? 'All classes' : c))),
      h('select', { onchange: e => upd(() => { f.ccy = e.target.value; })(), 'aria-label': 'Currency' },
        ['all', ...CCY_ORDER, 'SGD', 'CNH'].map(c => h('option', { value: c, selected: c === f.ccy ? true : null }, c === 'all' ? 'All currencies' : c))),
    ),
  );
  if (!rows.length) { root.appendChild(card('Signals', null, empty(S.sig && S.sig.status && S.sig.status.error ? 'Alert sheet unavailable: ' + S.sig.status.error : 'Loading alert sheet…'))); return; }

  const nb = filtered.filter(r => r.dir === 'bull').length, ns = filtered.filter(r => r.dir === 'bear').length;
  const uniq = new Set(filtered.map(r => r.sym)).size;
  root.appendChild(h('div', { class: 'kpis' }, [
    ['Signals', filtered.length.toLocaleString(), `${uniq} instruments`],
    ['Bullish', h('span', { style: { color: 'var(--bull-ink)' } }, `▲ ${nb}`), filtered.length ? `${Math.round(100 * nb / filtered.length)}%` : ''],
    ['Bearish', h('span', { style: { color: 'var(--bear-ink)' } }, `▼ ${ns}`), filtered.length ? `${Math.round(100 * ns / filtered.length)}%` : ''],
    ['Tone', filtered.length ? (nb > ns * 1.5 ? 'Risk-on / bid' : ns > nb * 1.5 ? 'Heavy selling' : 'Mixed') : '—', 'bull vs bear breadth'],
    ['Latest', filtered[0] ? h('span', null, filtered[0].sym, ' ', sigSpan(filtered[0].signal)) : '—', filtered[0] ? `${filtered[0].date} ${filtered[0].time} · ${TF_SRC[filtered[0].src]}` : ''],
  ].map(([l, v, ft]) => h('div', { class: 'kpi' }, h('div', { class: 'lbl' }, l), h('div', { class: 'val sm' }, v), h('div', { class: 'foot' }, ft)))));

  // chart + most active
  const days = f.range === 'custom' ? [f.day] : dateSpan(f.range === 'all' ? addDays(today, -59) : start, today);
  const chartCard = card('Signals per day', f.range === 'all' ? 'last 60 days' : '');
  const cbox = h('div'); chartCard.appendChild(cbox);
  Charts.stacked(cbox, dayBuckets(filtered, days), [SERIES_BULL, SERIES_BEAR], { aria: 'Filtered signals per day',
    onClick: d => { f.range = 'custom'; f.day = d.date; saveFilters(); render(); } });
  chartCard.appendChild(h('div', { class: 'small muted', style: { marginTop: '4px' } }, 'Click a day to drill in.'));
  const bySym = {};
  for (const r of filtered) { const o = bySym[r.sym] || (bySym[r.sym] = { bull: 0, bear: 0 }); o[r.dir] = (o[r.dir] || 0) + 1; }
  const top = Object.entries(bySym).map(([s, o]) => ({ s, ...o, n: (o.bull || 0) + (o.bear || 0) })).sort((a, b) => b.n - a.n).slice(0, 14);
  const maxN = Math.max(1, ...top.map(t => t.n));
  const actCard = card('Most active', `${Object.keys(bySym).length} instruments`,
    top.length ? top.map(t => h('div', { class: 'hbar', title: `${t.s}: ▲${t.bull || 0} ▼${t.bear || 0}` },
      symChip(t.s, (t.bull || 0) >= (t.bear || 0) ? 'bull' : 'bear'),
      h('div', { class: 'bars' },
        t.bull ? h('i', { style: { width: `${100 * t.bull / maxN}%`, background: 'var(--bull)' } }) : null,
        t.bear ? h('i', { style: { width: `${100 * t.bear / maxN}%`, background: 'var(--bear)' } }) : null),
      h('span', { class: 'num small' }, `${t.n}`))) : empty('Nothing matches'),
    h('div', { class: 'legend' }, h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--bull)' } }), '▲ Bull'), h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--bear)' } }), '▼ Bear')));
  root.appendChild(h('div', { class: 'grid g-wide' }, chartCard, actCard));

  // multi-timeframe alignment matrix (current state from the whole sheet, scoped to the filtered symbols)
  const fxSyms = new Set(filtered.filter(r => ['1H', '4H', 'D'].includes(r.src)).map(r => r.sym));
  if (fxSyms.size) {
    const latest = latestBySymbol(rows.filter(r => ['1H', '4H', 'D'].includes(r.src)));
    const mrows = [...fxSyms].map(sym => ({ sym, st: latest[sym] || {}, al: alignment(latest[sym] || {}) }))
      .sort((a, b) => (b.al.n - a.al.n) || ((b.st['1H'] || b.st['4H'] || {}).date || '').localeCompare((a.st['1H'] || a.st['4H'] || {}).date || ''));
    const stale = addDays(today, -10);
    const cell = r => r ? h('span', { class: 'cell', style: r.date < stale ? { opacity: 0.45 } : null, title: `${r.signal} @ ${r.price} · ${r.event}${r.date < stale ? ' · older than 10 days' : ''}` }, h('span', { class: `dir ${r.dir}` }, r.dir === 'bull' ? '▲' : '▼', ' ', r.signal), h('span', { class: 's' }, `${shortDate(r.date)} ${r.time.slice(0, 5)}`)) : h('span', { class: 'muted' }, '—');
    const mx = card('Multi-timeframe alignment', 'latest signal per timeframe · ★ = timeframes agreeing with the newest · faded = older than 10 days',
      h('div', { class: 'tbl-wrap', style: { maxHeight: '420px', overflowY: 'auto' } }, h('table', { class: 'tbl mx' },
        h('thead', null, h('tr', null, ['Instrument', 'Class', 'Daily', '4H', '1H', 'Alignment'].map(c => h('th', { class: ['Daily', '4H', '1H'].includes(c) ? 'c tf' : null }, c)))),
        h('tbody', null, mrows.slice(0, 60).map(m => h('tr', null,
          h('td', null, symChip(m.sym, m.al.dir)), h('td', null, h('span', { class: 'tag' }, (m.st['1H'] || m.st['4H'] || m.st['D']).cls)),
          h('td', { class: 'c' }, cell(m.st['D'])), h('td', { class: 'c' }, cell(m.st['4H'])), h('td', { class: 'c' }, cell(m.st['1H'])),
          h('td', { class: 'nowrap' }, h('span', { class: 'stars' }, '★'.repeat(m.al.n)), ' ', dirBadge(m.al.dir))))))));
    root.appendChild(h('div', { class: 'mt' }, mx));
  }

  // table
  const sort = f.sort || { k: 'date', d: -1 };
  const keyf = { date: r => r.date + ' ' + r.time, sym: r => r.sym, src: r => r.src, signal: r => r.signal, dir: r => r.dir, price: r => +r.price || 0 };
  const sorted = filtered.slice().sort((a, b) => { const x = keyf[sort.k](a), y = keyf[sort.k](b); return (x < y ? -1 : x > y ? 1 : 0) * sort.d; });
  const th = (label, k) => h('th', { class: k ? 'sortable' : '', onclick: k ? () => { f.sort = { k, d: sort.k === k ? -sort.d : -1 }; saveFilters(); render(); } : null },
    label, sort.k === k ? (sort.d > 0 ? ' ↑' : ' ↓') : '');
  const tbl = card('All signals', `${filtered.length.toLocaleString()} rows`, h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, th('Date / time (SGT)', 'date'), th('Instrument', 'sym'), th('Source', 'src'), th('Signal', 'signal'), th('Dir', 'dir'), th('Price', 'price'), th('Event / sector'))),
    h('tbody', null, sorted.slice(0, f.shown).map(r => h('tr', null,
      h('td', { class: 'nowrap num' }, `${r.date} ${r.time.slice(0, 5)}`),
      h('td', { class: 'nowrap' }, symChip(r.sym, r.dir), r.exch && !['EIGHTCAP', 'BATS'].includes(r.exch) ? h('span', { class: 'small muted' }, ' ' + r.exch) : null,
        r.name ? h('div', { class: 'small muted' }, r.name) : null),
      h('td', null, h('span', { class: 'tag src' }, TF_SRC[r.src])),
      h('td', null, sigSpan(r.signal)), h('td', null, dirBadge(r.dir)),
      h('td', { class: 'num' }, r.price), h('td', { class: 'wrap small' }, r.event || r.sector)))))),
    sorted.length > f.shown ? h('div', { class: 'more' }, h('button', { class: 'btn', onclick: () => { f.shown += 400; render(); } }, `Show more (${(sorted.length - f.shown).toLocaleString()} left)`)) : null);
  root.appendChild(h('div', { class: 'mt' }, tbl));
}

// ============================================================ views: ANALYSIS
async function viewAnalysis(root) {
  const meta = S.meta || {};
  const dates = [...new Set([...(meta.tat || []), ...(meta.dsig || [])])].sort().reverse();
  const f = F('analysis', { date: null, run: null, dir: 'all', showNarr: true });
  if (!f.date || !dates.includes(f.date)) f.date = dates[0];
  const [rep, ds] = await Promise.all([
    (meta.tat || []).includes(f.date) ? api('/api/tat?date=' + f.date) : null,
    (meta.dsig || []).includes(f.date) ? api('/api/dsig?date=' + f.date) : null,
  ]);
  const runs = (rep && rep.runs) || [];
  let run = runs.find(r => r.time === f.run) || runs[runs.length - 1];
  const idx = dates.indexOf(f.date);
  const setDate = d => { f.date = d; f.run = null; saveFilters(); render(); };

  root.replaceChildren(
    h('div', { class: 'view-head' }, h('h1', null, 'TAT Analysis'), h('span', { class: 'sub' }, '1H + 4H combined reviews and Daily Signals write-ups')),
    h('div', { class: 'filters' },
      h('div', { class: 'datebar' },
        h('button', { class: 'iconbtn', disabled: idx >= dates.length - 1 ? true : null, onclick: () => setDate(dates[idx + 1]), title: 'Older' }, '‹'),
        h('select', { onchange: e => setDate(e.target.value), 'aria-label': 'Report date' }, dates.map(d => h('option', { value: d, selected: d === f.date ? true : null }, niceDate(d) + ' ' + d.slice(0, 4)))),
        h('button', { class: 'iconbtn', disabled: idx <= 0 ? true : null, onclick: () => setDate(dates[idx - 1]), title: 'Newer' }, '›')),
      runs.length ? h('span', { class: 'flabel' }, 'Run') : null,
      runs.length ? seg(runs.map(r => ({ v: r.time, label: r.time })), run && run.time, v => { f.run = v; saveFilters(); render(); }) : null,
      h('span', { class: 'flabel' }, 'Dir'),
      seg([{ v: 'all', label: 'All' }, { v: 'bull', label: '▲ Bull', cls: 'bull' }, { v: 'bear', label: '▼ Bear', cls: 'bear' }], f.dir, v => { f.dir = v; saveFilters(); render(); }),
      rep ? h('button', { class: 'btn', onclick: () => openDoc(rep.path, rep.title) }, 'Full report ↗') : null,
    ),
  );
  if (!rep && !ds) { root.appendChild(card('Analysis', null, empty('No TAT report or Daily Signals write-up for this date.'))); return; }

  if (run) {
    const setups = run.setups.filter(s => (f.dir === 'all' || s.dir === f.dir) && matches(S.q, s.syms, s.title, s.text, s.detail));
    const group = b => setups.filter(s => s.bucket === b);
    const ideaCard = s => h('div', { class: `icard ${s.dir}` },
      h('div', { class: 'hd' }, s.syms.map(x => symChip(x, s.dir)), dirBadge(s.dir)),
      s.title ? h('div', { class: 'title' }, s.title) : null,
      s.text ? h('div', { class: 'kv' }, s.text) : null,
      s.detail.length ? h('ul', null, s.detail.map(d => h('li', null, d))) : null);
    const secs = [['dual', '⭐⭐⭐ 4H + 1H dual alignment'], ['retest', '🔄 Retest pullback candidates']];
    const setCard = card(`Setups · ${run.time} SGT run`, `${setups.length} of ${run.setups.length}`);
    for (const [b, title] of secs) {
      const g = group(b);
      if (!g.length) continue;
      setCard.appendChild(h('h3', null, title, ' ', h('span', { class: 'muted small' }, `(${g.length})`)));
      setCard.appendChild(h('div', { class: 'cards' }, g.map(ideaCard)));
    }
    if (!setups.length) setCard.appendChild(empty(run.setups.length ? 'No setups match the filters' : 'No structured setups were extracted from this run — see the narrative below.'));
    root.appendChild(setCard);

    if (run.diff && run.diff.length) {
      const cols = Object.keys(run.diff[0]);
      root.appendChild(h('div', { class: 'mt' }, card('What changed vs the previous run', null, h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
        h('thead', null, h('tr', null, cols.map(c => h('th', null, c)))),
        h('tbody', null, run.diff.filter(r => matches(S.q, Object.values(r))).map(r => h('tr', null, cols.map((c, i) => {
          const td = h('td', { class: i ? 'wrap small' : 'nowrap' }); td.appendChild(renderInline(r[c])); return td;
        })))))))));
    }

    const narr = h('details', { open: f.showNarr ? true : null, ontoggle: e => { f.showNarr = e.target.open; saveFilters(); } },
      h('summary', { style: { cursor: 'pointer', fontWeight: 600, color: 'var(--text-2)' } }, `Full ${run.time} SGT narrative (clusters, watchlists, screenshots)`));
    const md = renderMd(run.md, rep.path);
    narr.appendChild(md);
    const hits = S.q ? highlight(md, S.q) : 0;
    root.appendChild(h('div', { class: 'mt' }, card('Run narrative', S.q ? `${hits} match${hits === 1 ? '' : 'es'} for “${S.q}”` : '', narr)));
  }
  if (ds && ds.summary) {
    const md = renderMd(ds.summary, ds.path);
    if (S.q) highlight(md, S.q);
    root.appendChild(h('div', { class: 'mt' }, card('Daily Signals · executive summary', h('a', { style: { cursor: 'pointer' }, onclick: () => openDoc(ds.path, 'Daily Signals ' + ds.date) }, 'Full Daily Signals report ↗'), md)));
  }
}

function renderInline(str) {
  const wrap = renderMd(str || '');
  const p = wrap.querySelector('p');
  return p ? Object.assign(document.createElement('span'), { innerHTML: p.innerHTML }) : wrap;
}

// ============================================================ views: CALENDAR
// Actuals the wiki snapshot didn't have yet are backfilled server-side from TradingView after release.
const actualCell = (val, src) => h('b', { title: src ? `Filled from ${src} after release` : null }, val,
  src ? h('sup', { class: 'muted', style: { fontWeight: 400, marginLeft: '3px' } }, 'TV') : null);
let cdTimer = null;
async function viewCalendar(root) {
  const [cal, cb, fw] = await Promise.all([api('/api/calendar'), api('/api/cb'), api('/api/fedwatch')]);
  const f = F('calendar', { range: 'week', impacts: ['High', 'Medium'], ccy: 'all', hidePast: false });
  f.impacts = asSet(f.impacts);
  const today = sgtToday(), now = Date.now();
  const evs = ((cal && cal.events) || []);
  const rangeOk = e => ({ last: e.week === 'last', today: e.date === today, tomorrow: e.date === addDays(today, 1), week: e.week === 'this', next: e.week === 'next', all: true })[f.range];
  const list = evs.filter(e => rangeOk(e) && f.impacts.has(e.impact) && (f.ccy === 'all' || e.ccy === f.ccy) && (!f.hidePast || evTime(e) > now)
    && matches(S.q, e.ccy, e.event)).sort((a, b) => evTime(a) - evTime(b));
  const nextHigh = evs.filter(e => e.impact === 'High' && evTime(e) > now).sort((a, b) => evTime(a) - evTime(b))[0];
  const ccys = ['all', ...[...new Set(evs.map(e => e.ccy))].sort()];
  const upd = fn => () => { fn(); saveFilters(); render(); };

  const cd = h('span', { class: 'cd' });
  const tick = () => { if (nextHigh) cd.textContent = until(evTime(nextHigh) - Date.now()); };
  tick(); clearInterval(cdTimer); cdTimer = setInterval(tick, 15000);

  const top = [
    h('div', { class: 'view-head' }, h('h1', null, 'Economic Calendar'), h('span', { class: 'sub' }, `Forex Factory · SGT · updated ${cal ? cal.updated : '—'}`)),
    nextHigh ? h('div', { class: 'banner' }, h('span', { class: 'flabel', style: { margin: 0 } }, 'Next high-impact'), cd,
      h('span', null, h('span', { class: 'tag' }, nextHigh.ccy), ' ', h('b', null, nextHigh.event)),
      h('span', { class: 'muted' }, `${niceDate(nextHigh.date)} ${nextHigh.time} SGT`, nextHigh.forecast ? ` · Forecast ${nextHigh.forecast}` : '', nextHigh.previous ? ` · Previous ${nextHigh.previous}` : '')) : null,
    h('div', { class: 'filters' },
      h('span', { class: 'flabel' }, 'When'),
      seg([{ v: 'last', label: 'Last week' }, { v: 'today', label: 'Today' }, { v: 'tomorrow', label: 'Tomorrow' }, { v: 'week', label: 'This week' }, { v: 'next', label: 'Next week' }, { v: 'all', label: 'All' }], f.range, v => upd(() => { f.range = v; })()),
      h('span', { class: 'flabel' }, 'Impact'),
      seg([{ v: 'High', label: '🟥 High' }, { v: 'Medium', label: '🟧 Medium' }, { v: 'Low', label: '🟨 Low' }], f.impacts, v => upd(() => { f.impacts = v; })(), { multi: true }),
      h('select', { onchange: e => upd(() => { f.ccy = e.target.value; })(), 'aria-label': 'Currency' }, ccys.map(c => h('option', { value: c, selected: c === f.ccy ? true : null }, c === 'all' ? 'All currencies' : c))),
      h('label', { class: 'toggle' }, h('input', { type: 'checkbox', checked: f.hidePast ? true : null, onchange: e => upd(() => { f.hidePast = e.target.checked; })() }), 'Hide past'),
    ),
  ].filter(Boolean);
  root.replaceChildren(...top);

  const body = [];
  let lastDate = null;
  for (const e of list) {
    if (e.date !== lastDate) { body.push(h('tr', { class: 'dayrow' }, h('td', { colspan: 8 }, `${niceDate(e.date)}${e.date === today ? ' · Today' : ''}`))); lastDate = e.date; }
    const t = evTime(e) - now;
    body.push(h('tr', { class: t < 0 ? 'past' : t < 2 * 3600e3 ? 'soon' : '' },
      h('td', { class: 'nowrap num' }, e.time), h('td', null, impactBadge(e.impact)), h('td', null, h('span', { class: 'tag' }, e.ccy)),
      h('td', { class: 'wrap' }, e.url ? h('a', { href: e.url, target: '_blank', rel: 'noopener' }, e.event) : e.event),
      h('td', { class: 'num nowrap' }, e.actual ? actualCell(e.actual, e.actualSrc) : h('span', { class: 'muted' }, '—')),
      h('td', { class: 'num' }, e.forecast), h('td', { class: 'num' }, e.previous),
      h('td', { class: 'nowrap small muted' }, t > 0 && t < 3 * 864e5 ? 'in ' + until(t) : '')));
  }
  const tableCard = card('Events', `${list.length} events`, list.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, ['Time', 'Impact', 'Ccy', 'Event', 'Actual', 'Forecast', 'Previous', ''].map(c => h('th', null, c)))), h('tbody', null, body))) : empty('No events match these filters'));

  // side: central banks + per-currency density
  const side = h('div', { class: 'grid' });
  if (cb) {
    side.appendChild(cbCard(cb));
    side.appendChild(fedCard(fw));
    const ahead = cb.stances.filter(s => s.next && s.next.when).map(s => ({ ...s, d: (s.next.when.match(/\d{4}-\d{2}-\d{2}/) || [''])[0] }))
      .filter(s => s.d && s.d >= today).sort((a, b) => a.d.localeCompare(b.d));
    side.appendChild(card('Rate decisions ahead', null, ahead.length ? h('div', { class: 'list' }, ahead.map(s => h('div', { class: 'li' }, h('div', { class: 'body' },
      h('div', { class: 't' }, s.bank, h('span', { class: 'tag' }, s.stance)), h('div', { class: 'm' }, `${s.next.when} · ${s.next.type}`))))) : empty('None scheduled')));
  }
  const byCcy = {};
  for (const e of evs.filter(e => rangeOk(e) && e.impact !== 'Low')) { const o = byCcy[e.ccy] || (byCcy[e.ccy] = { High: 0, Medium: 0 }); o[e.impact]++; }
  const ccyRows = Object.entries(byCcy).sort((a, b) => (b[1].High * 3 + b[1].Medium) - (a[1].High * 3 + a[1].Medium));
  const maxC = Math.max(1, ...ccyRows.map(([, o]) => o.High + o.Medium));
  side.appendChild(card('Event load by currency', 'high + medium',
    ccyRows.length ? ccyRows.map(([c, o]) => h('div', { class: 'hbar', title: `${c}: ${o.High} high, ${o.Medium} medium`, style: { cursor: 'pointer' }, onclick: () => upd(() => { f.ccy = c; })() },
      h('span', { class: 'tag' }, c), h('div', { class: 'bars' },
        o.High ? h('i', { style: { width: `${100 * o.High / maxC}%`, background: 'var(--high)' } }) : null,
        o.Medium ? h('i', { style: { width: `${100 * o.Medium / maxC}%`, background: 'var(--medium)' } }) : null),
      h('span', { class: 'num small' }, o.High + o.Medium))) : empty('—'),
    h('div', { class: 'legend' }, h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--high)' } }), 'High'), h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: 'var(--medium)' } }), 'Medium'))));
  root.appendChild(h('div', { class: 'grid g-side' }, tableCard, side));
}

// ============================================================ views: AHH
async function viewAhh(root) {
  const notes = (await api('/api/ahh')) || [];
  // `hidden` (not an allow-list) so a session type added later shows up without resetting saved filters
  const f = F('ahh', { range: '30d', hidden: [], dir: 'all', mode: 'ideas', sym: null });
  delete f.sessions;
  const TYPES = ['Weekly Review', 'TAR Session', 'AHH Access Time', 'AHH Session', 'TAW Pro', '3TT'].filter(t => notes.some(n => n.session === t));
  const hidden = asSet(f.hidden, []);
  const shownTypes = new Set(TYPES.filter(t => !hidden.has(t)));
  const today = sgtToday();
  const start = { last: (notes[0] || {}).date, '7d': addDays(today, -6), '30d': addDays(today, -29), all: '0000' }[f.range];
  const upd = fn => () => { fn(); saveFilters(); render(); };
  const inScope = n => n.date >= start && !hidden.has(n.session);
  const ideaOk = i => (f.dir === 'all' || i.dir === f.dir) && (!f.sym || i.syms.includes(f.sym)) && matches(S.q, i.title, i.syms, i.direction, i.levels, i.setup, i.session);
  const scoped = notes.filter(inScope);
  const allIdeas = scoped.flatMap(n => n.ideas);
  const ideas = allIdeas.filter(ideaOk);

  root.replaceChildren(
    h('div', { class: 'view-head' }, h('h1', null, 'Session Ideas'), h('span', { class: 'sub' }, 'Suggested trades from Weekly Review, TAR Session, AHH Access Time, AHH Session, TAW Pro and 3TT notes')),
    h('div', { class: 'filters' },
      seg([{ v: 'ideas', label: 'Trade ideas' }, { v: 'rules', label: 'Trading rules' }], f.mode, v => upd(() => { f.mode = v; })()),
      h('span', { class: 'flabel' }, 'Range'),
      seg([{ v: 'last', label: 'Last session' }, { v: '7d', label: '7D' }, { v: '30d', label: '30D' }, { v: 'all', label: 'All' }], f.range, v => upd(() => { f.range = v; })()),
      h('span', { class: 'flabel' }, 'Session'),
      seg(TYPES.map(v => ({ v, label: v })), shownTypes, v => upd(() => { f.hidden = TYPES.filter(t => !v.has(t)); })(), { multi: true }),
      f.mode === 'ideas' ? h('span', { class: 'flabel' }, 'Dir') : null,
      f.mode === 'ideas' ? seg([{ v: 'all', label: 'All' }, { v: 'bull', label: '▲ Long', cls: 'bull' }, { v: 'bear', label: '▼ Short', cls: 'bear' }, { v: 'neutral', label: '● Watch' }], f.dir, v => upd(() => { f.dir = v; })()) : null,
      f.sym ? h('button', { class: 'btn', onclick: upd(() => { f.sym = null; }) }, `✕ ${f.sym}`) : null,
    ),
  );

  if (f.mode === 'rules') {
    const rules = scoped.flatMap(n => n.rules).filter(r => matches(S.q, r.name, r.text));
    root.appendChild(card('Technical trading rules emphasized', `${rules.length} rules`, rules.length ? h('div', { class: 'list' }, rules.map(r => h('div', { class: 'li' }, h('div', { class: 'body' },
      h('div', { class: 't' }, r.name || 'Rule', h('span', { class: 'tag' }, `${r.session} · ${r.date}`)), h('div', { class: 'd' }, r.text))))) : empty('No rules match')));
    return;
  }

  // top instruments + direction mix per session
  const counts = {};
  for (const i of allIdeas.filter(i => (f.dir === 'all' || i.dir === f.dir) && matches(S.q, i.title, i.syms, i.direction, i.levels, i.setup))) {
    for (const s of i.syms) { const o = counts[s] || (counts[s] = { bull: 0, bear: 0, neutral: 0 }); o[i.dir]++; }
  }
  const topI = Object.entries(counts).map(([s, o]) => ({ s, ...o, n: o.bull + o.bear + o.neutral })).sort((a, b) => b.n - a.n).slice(0, 14);
  const maxN = Math.max(1, ...topI.map(t => t.n));
  const topCard = card('Most-discussed instruments', 'click to filter', topI.length ? topI.map(t => h('div', { class: 'hbar', style: { cursor: 'pointer' }, title: `${t.s}: ▲${t.bull} ▼${t.bear} ●${t.neutral}`, onclick: upd(() => { f.sym = f.sym === t.s ? null : t.s; }) },
    h('span', { class: `sym ${t.bull > t.bear ? 'bull' : t.bear > t.bull ? 'bear' : ''}` }, t.s),
    h('div', { class: 'bars' }, [['bull', 'var(--bull)'], ['neutral', 'var(--neutral)'], ['bear', 'var(--bear)']].map(([k, c]) => t[k] ? h('i', { style: { width: `${100 * t[k] / maxN}%`, background: c } }) : null)),
    h('span', { class: 'num small' }, t.n))) : empty('No ideas'),
    h('div', { class: 'legend' }, [['▲ Long', 'var(--bull)'], ['● Watch', 'var(--neutral)'], ['▼ Short', 'var(--bear)']].map(([l, c]) => h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: c } }), l))));
  const mixCard = card('Direction mix per session', null);
  const mbox = h('div'); mixCard.appendChild(mbox);
  const sess = scoped.slice(0, 16).reverse();
  Charts.stacked(mbox, sess.map(n => {
    const v = { bull: 0, bear: 0, neutral: 0 }; n.ideas.filter(ideaOk).forEach(i => v[i.dir]++);
    return { label: shortDate(n.date), tip: `${n.session} · ${niceDate(n.date)}`, values: v };
  }), [SERIES_BULL, SERIES_NEU, SERIES_BEAR], { aria: 'Ideas per session by direction', height: 200 });
  root.appendChild(h('div', { class: 'grid g2' }, topCard, mixCard));

  // grouped cards
  let shown = 0;
  for (const n of scoped) {
    const list = n.ideas.filter(ideaOk);
    if (!list.length && (S.q || f.sym || f.dir !== 'all')) continue;
    shown += list.length;
    const sum = h('div', { class: 'session-sum clamp' }, renderInline(n.summary));
    root.appendChild(h('div', { class: 'session-hd' },
      h('h3', null, `${n.session}`), h('span', { class: 'muted' }, niceDate(n.date) + ' ' + n.date.slice(0, 4)),
      h('span', { class: 'tag' }, `${list.length} idea${list.length === 1 ? '' : 's'}`),
      h('a', { style: { cursor: 'pointer' }, onclick: () => openDoc(n.path, `${n.session} — ${n.date}`) }, 'Open note ↗')));
    if (n.summary) { sum.addEventListener('click', () => sum.classList.toggle('open')); sum.style.cursor = 'pointer'; sum.title = 'Click to expand'; root.appendChild(sum); }
    if (list.length) root.appendChild(h('div', { class: 'cards' }, list.map(i => {
      const setup = h('div', { class: 'kv clamp' }, h('b', null, 'Setup'), i.setup);
      return h('div', { class: `icard ${i.dir}` },
        h('div', { class: 'hd' }, i.syms.slice(0, 4).map(s => symChip(s, i.dir)), dirBadge(i.dir)),
        h('div', { class: 'title' }, i.title),
        i.direction ? h('div', { class: 'kv' }, h('b', null, 'Direction'), i.direction) : null,
        i.levels ? h('div', { class: 'kv' }, h('b', null, 'Levels'), i.levels) : null,
        i.setup ? setup : null,
        i.setup && i.setup.length > 220 ? h('a', { class: 'small', style: { cursor: 'pointer' }, onclick: e => { setup.classList.toggle('open'); e.target.textContent = setup.classList.contains('open') ? 'Less' : 'More'; } }, 'More') : null);
    })));
  }
  if (!shown && !scoped.length) root.appendChild(empty('No sessions in this range'));
  else if (!shown) root.appendChild(empty('No ideas match these filters'));
}

// ============================================================ views: BRIEF
async function viewBrief(root) {
  const dates = (S.meta && S.meta.briefs) || [];
  const f = F('brief', { date: null, wdir: 'all', wcls: 'all', wsig: false });
  // Default to the newest brief (today's) on each page load; a date picked later in the session sticks until reload.
  if (!viewBrief.started) { viewBrief.started = true; f.date = dates[0]; }
  if (!f.date || !dates.includes(f.date)) f.date = dates[0];
  const [b, sent] = await Promise.all([api('/api/brief?date=' + f.date), api('/api/sentiment?date=' + f.date)]);
  const idx = dates.indexOf(f.date);
  const setDate = d => { f.date = d; saveFilters(); render(); };
  root.replaceChildren(
    h('div', { class: 'view-head' }, h('h1', null, 'Daily Brief'), h('span', { class: 'sub' }, b ? b.title.replace(/^📅\s*/, '') : '')),
    h('div', { class: 'filters' },
      h('div', { class: 'datebar' },
        h('button', { class: 'iconbtn', disabled: idx >= dates.length - 1 ? true : null, onclick: () => setDate(dates[idx + 1]) }, '‹'),
        h('select', { onchange: e => setDate(e.target.value), 'aria-label': 'Brief date' }, dates.map(d => h('option', { value: d, selected: d === f.date ? true : null }, niceDate(d) + ' ' + d.slice(0, 4)))),
        h('button', { class: 'iconbtn', disabled: idx <= 0 ? true : null, onclick: () => setDate(dates[idx - 1]) }, '›')),
      b ? h('button', { class: 'btn', onclick: () => openDoc(b.path, b.title) }, 'Full brief ↗') : null),
  );
  if (!b) { root.appendChild(empty('No brief for this date')); return; }
  const q = S.q;

  if (b.overview.length) root.appendChild(h('div', { class: 'card' }, b.overview.map(o => h('div', { style: { padding: '3px 0' } }, h('b', null, o.k + ': '), renderInline(o.v)))));

  const evCard = card("Today's high-impact events", null, b.events.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, ['Time', 'Ccy', 'Event', 'Actual', 'Forecast', 'Previous'].map(c => h('th', null, c)))),
    h('tbody', null, b.events.filter(e => matches(q, Object.values(e))).map(e => h('tr', null,
      h('td', { class: 'num' }, e['Time (SGT)']), h('td', null, h('span', { class: 'tag' }, e.Currency)), h('td', { class: 'wrap' }, e.Event),
      h('td', { class: 'num nowrap' }, e.Actual && e.Actual !== '—' ? actualCell(e.Actual, e.actualSrc) : h('span', { class: 'muted' }, '—')), h('td', { class: 'num' }, e.Forecast), h('td', { class: 'num' }, e.Previous)))))) : empty('No red-folder events'));
  const csCard = card('Currency strength', null);
  const csBox = h('div'); csCard.appendChild(csBox);
  Charts.diverging(csBox, b.scores.map(s => ({ label: s.ccy, value: s.score, tip: s.bias })), { aria: 'Currency strength', onClick: d => { setQuery(d.label); go('signals'); } });
  if (b.pairs.length) csCard.appendChild(h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' } },
    b.pairs.map(p => h('span', { style: { display: 'inline-flex', gap: '4px', alignItems: 'center' } }, symChip(p.sym, p.dir), h('span', { class: `dir ${p.dir}` }, `${p.dir === 'bull' ? '▲ Buy' : '▼ Sell'} ${p.diff}`)))));
  if (b.cos.length) csCard.appendChild(h('div', { class: 'small', style: { marginTop: '10px' } }, h('b', null, 'Change of structure: '),
    b.cos.map(c => h('span', null, symChip(c.sym), ` ${c.prev} → ${c.cur}  `))));
  root.appendChild(h('div', { class: 'grid g2' }, evCard, csCard));

  // sentiment
  const srows = (sent && sent.rows && sent.rows.length ? sent.rows : b.sentiment).filter(r => matches(q, r.name, r.sym, r.summary));
  if (srows.length) {
    const sc = card('News sentiment', sent && sent.date ? h('a', { style: { cursor: 'pointer' }, onclick: () => openDoc(sent.path, 'Market sentiment ' + sent.date) }, `${sent.date} · headlines ↗`) : '');
    for (const r of srows) {
      const sum = r.summary ? h('div', { class: 'sentsum hidden' }, r.summary) : null;
      sc.appendChild(h('div', { class: 'sentrow', title: `▲ ${r.pos}% positive · ● ${r.neu}% neutral · ▼ ${r.neg}% negative`, onclick: () => sum && sum.classList.toggle('hidden') },
        h('span', { class: 'nm' }, r.sym ? symChip(r.sym) : null, ' ', r.name.replace(/\s*\(.*\)$/, '')),
        h('div', { class: 'sentbar' },
          h('i', { style: { width: r.pos + '%', background: 'var(--bull)' } }), h('i', { style: { width: r.neu + '%', background: 'var(--neutral)' } }), h('i', { style: { width: r.neg + '%', background: 'var(--bear)' } })),
        h('span', { class: 'num small muted' }, r.n)));
      if (sum) sc.appendChild(sum);
    }
    sc.appendChild(h('div', { class: 'legend' }, [['▲ Positive', 'var(--bull)'], ['● Neutral', 'var(--neutral)'], ['▼ Negative', 'var(--bear)']].map(([l, c]) => h('span', { class: 'k' }, h('i', { class: 'sw', style: { background: c } }), l)),
      h('span', { class: 'muted' }, '· number = articles · click a row for the summary')));
    root.appendChild(h('div', { class: 'mt' }, sc));
  }

  const syn = b.synthesis.filter(s => matches(q, s.syms, s.text));
  const drhr = b.drhr.filter(d => matches(q, d.sym, d.label, d.detail));
  root.appendChild(h('div', { class: 'grid g2 mt' },
    card('4H + 1H synthesis', null, syn.length ? h('div', { class: 'list' }, syn.map(setupLi)) : empty('None')),
    card('D-R-H-R reversal setups', null, drhr.length ? h('div', { class: 'list' }, drhr.map(d => h('div', { class: 'li' }, h('div', { class: 'body' },
      h('div', { class: 't' }, symChip(d.sym, d.dir), dirBadge(d.dir), h('span', { class: 'small' }, d.label)), h('div', { class: 'm' }, d.detail.join(' · ')))))) : empty('None'))));

  // watchlist gallery
  if (b.watchlist.length) {
    const upd = fn => () => { fn(); saveFilters(); render(); };
    const classes = ['all', ...new Set(b.watchlist.map(w => w.cls))];
    const wl = b.watchlist.filter(w => (f.wdir === 'all' || w.dir === f.wdir) && (f.wcls === 'all' || w.cls === f.wcls) && (!f.wsig || w.signal) && matches(q, w.sym, w.signal, w.structure, w.bias));
    const nb = b.watchlist.filter(w => w.dir === 'bull').length, ns = b.watchlist.filter(w => w.dir === 'bear').length;
    root.appendChild(h('div', { class: 'mt' }, card('Daily watchlist charts', `${wl.length} of ${b.watchlist.length} · ▲${nb} ▼${ns}`,
      h('div', { class: 'filters' },
        seg([{ v: 'all', label: 'All' }, { v: 'bull', label: '▲ Bull', cls: 'bull' }, { v: 'bear', label: '▼ Bear', cls: 'bear' }, { v: 'neutral', label: '● Neutral' }], f.wdir, v => upd(() => { f.wdir = v; })()),
        h('select', { onchange: e => upd(() => { f.wcls = e.target.value; })(), 'aria-label': 'Class' }, classes.map(c => h('option', { value: c, selected: c === f.wcls ? true : null }, c === 'all' ? 'All classes' : c))),
        h('label', { class: 'toggle' }, h('input', { type: 'checkbox', checked: f.wsig ? true : null, onchange: e => upd(() => { f.wsig = e.target.checked; })() }), 'With signal only')),
      wl.length ? h('div', { class: 'wgrid' }, wl.map(w => h('div', { class: 'wcard' },
        w.img ? h('img', { src: '/images/' + w.img, loading: 'lazy', alt: `${w.sym} daily chart`, dataset: { full: '/images/' + w.img, cap: `${w.sym} · Daily · ${b.date}` } }) : h('div', { class: 'empty' }, 'No chart'),
        h('div', { class: 'wb' }, symChip(w.sym, w.dir), dirBadge(w.dir), w.signal ? sigSpan(w.signal) : null,
          h('span', { class: 'tag' }, 'Struct ' + w.structure), h('span', { class: 'tag' }, 'Bias ' + w.bias), h('span', { class: 'num muted', style: { marginLeft: 'auto' } }, w.price))))) : empty('Nothing matches'))));
  }
}

// ============================================================ views: MY WATCHLIST
async function viewMyWatchlist(root) {
  const g = await api('/api/my-watchlist');
  root.replaceChildren(h('div', { class: 'view-head' }, h('h1', null, 'My Watchlist'),
    h('span', { class: 'sub' }, g && g.date ? `4H screenshot sweep · ${g.date}${g.time ? ' · ' + g.time + ' SGT run' : ''}` : '')));
  if (!g || !g.entries.length) {
    root.appendChild(empty('No my-watchlist screenshots captured yet — this populates after the next scheduled 4H run (06:15/09:01/13:01/17:01/21:01 SGT).'));
    return;
  }
  const q = S.q;
  const entries = g.entries.filter(e => matches(q, e.sym));
  root.appendChild(card('4H chart screenshots', `${entries.length} of ${g.entries.length}`,
    entries.length ? h('div', { class: 'wgrid' }, entries.map(e => h('div', { class: 'wcard' },
      e.img ? h('img', { src: '/images/' + e.img, loading: 'lazy', alt: `${e.sym} 4H chart`, dataset: { full: '/images/' + e.img, cap: `${e.sym} · 4H · ${g.date}` } }) : h('div', { class: 'empty' }, 'No chart'),
      h('div', { class: 'wb' }, symChip(e.sym))))) : empty('Nothing matches')));
}

// ============================================================ instrument drawer
const TV_LAYOUT = 'https://www.tradingview.com/chart/3Jax65FF/';

// Open the saved TradingView layout on this instrument, with the same exchange prefix the alerts use.
function tradingViewUrl(sym, row, interval = 'D') {
  let exch = row ? row.exch : '';
  if (exch === 'US') exch = '';                           // Yahoo US tickers: let TradingView resolve the listing
  else if (!exch && (!row || row.cls !== 'Stock')) exch = 'EIGHTCAP';
  const symParam = encodeURIComponent(exch ? `${exch}:${sym}` : sym);
  const intParam = interval ? `&interval=${encodeURIComponent(interval)}` : '';
  return `${TV_LAYOUT}?symbol=${symParam}${intParam}`;
}
async function openSymbol(sym) {
  sym = (sym || '').toUpperCase().trim();
  if (!sym) return;
  $('#dSym').textContent = sym;
  $('#dTags').replaceChildren();
  const body = $('#dBody');
  body.replaceChildren(empty('Loading…'));
  $('#drawer').classList.add('show'); $('#scrim').classList.add('show');
  if (location.hash.startsWith('#sym=')) history.replaceState(null, '', `#${S.view}`);

  const [imgs, ahh, brief, cal, sent, entity, journal] = await Promise.all([
    api('/api/images?sym=' + encodeURIComponent(sym)), api('/api/ahh'), api('/api/brief'), api('/api/calendar'), api('/api/sentiment'),
    api('/api/doc?path=' + encodeURIComponent(`entities/${sym.toLowerCase()}.md`)), api('/api/journal'),
  ]);
  const tatDates = ((S.meta && S.meta.tat) || []).slice(0, 2);
  const reps = await Promise.all(tatDates.map(d => api('/api/tat?date=' + d)));
  if ($('#dSym').textContent !== sym) return; // user moved on

  const rows = sigRows().filter(r => r.sym === sym);
  const cls = rows[0] ? rows[0].cls : '';
  const tagKids = [
    ...[cls, ...symCurrencies(sym)].filter(Boolean).map(t => h('span', { class: 'tag' }, t)),
    entity ? h('a', { class: 'small', style: { cursor: 'pointer', marginLeft: '6px' }, onclick: () => openDoc(entity.path, sym) }, 'Wiki page ↗') : null,
    h('a', { class: 'small', href: tradingViewUrl(sym, rows[0], 'D'), target: '_blank', rel: 'noopener', style: { marginLeft: '6px' } }, 'TradingView ↗'),
  ].filter(Boolean);
  $('#dTags').replaceChildren(...tagKids);
  const out = [];

  // current state per timeframe
  const st = latestBySymbol(rows)[sym] || {};
  const tfs = (cls === 'Stock' ? ['BATS', 'YBULL', 'YBEAR'] : ['D', '4H', '1H'])
    .sort((x, y) => {  // newest signal on the left; timeframes with no signal last
      const kx = st[x] ? `${st[x].date} ${st[x].time}` : '', ky = st[y] ? `${st[y].date} ${st[y].time}` : '';
      return ky.localeCompare(kx);
    });
  const tfMap = { 'D': 'D', '4H': '240', '1H': '60' };
  out.push(h('div', { class: 'statebox' }, tfs.map(k => {
    const r = st[k];
    const iv = tfMap[k] || 'D';
    return h('div', { class: `sb ${r ? r.dir : ''}` },
      h('div', { class: 'tf', style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
        h('span', null, TF_SRC[k]),
        h('a', {
          href: tradingViewUrl(sym, rows[0], iv),
          target: '_blank',
          rel: 'noopener',
          class: 'small muted',
          style: { textDecoration: 'none', marginLeft: '4px' },
          title: `Open ${sym} (${k}) in TradingView`
        }, '↗')
      ),
      r ? h('div', { class: 'v' }, dirBadge(r.dir), ' ', sigSpan(r.signal)) : h('div', { class: 'v muted' }, 'No signal'),
      r ? h('div', { class: 's' }, `${r.date} ${r.time.slice(0, 5)} · @ ${r.price}`) : null,
      r && r.event ? h('div', { class: 's' }, r.event) : null);
  })));
  const al = alignment(st);
  if (al.n >= 2) out.push(h('div', { class: 'small' }, h('span', { class: 'stars' }, '★'.repeat(al.n)), ` ${al.n} of ${al.total} timeframes agree `, dirBadge(al.dir)));

  // my journal entries for this instrument
  const mine = (journal || []).filter(t => t.symbol === sym).sort((a, b) => (b.opened || '').localeCompare(a.opened || ''));
  if (mine.length) {
    const ms = rStats(mine.filter(hasR));
    out.push(card('My trades', ms.n ? `${mine.length} logged · ${fmtR(ms.tot)} · win ${ms.win}%` : `${mine.length} logged`, h('div', { class: 'list' }, mine.slice(0, 8).map(t => h('div', { class: 'li', style: { cursor: 'pointer' }, onclick: () => openDoc(t.path, `${t.symbol} ${t.direction} · ${t.opened}`) }, h('div', { class: 'body' },
      h('div', { class: 't' }, dirBadge(tradeDir(t)), h('span', { class: 'small muted' }, t.opened), t.status === 'closed' ? rSpan(t.result_r) : h('span', { class: 'tag' }, t.status),
        t.fomo !== null && t.fomo !== undefined ? h('span', { class: 'tag' }, `FOMO ${t.fomo}`) : null),
      t.why ? h('div', { class: 'd clamp' }, t.why) : null,
      t.flags.length ? h('div', null, t.flags.map(x => h('span', { class: `tag flag ${x}` }, x))) : null))))));
  }

  const w = brief && brief.watchlist.find(x => x.sym === sym);
  if (w) out.push(card('Daily brief state', brief.date, h('div', { class: 'wb', style: { display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' } },
    dirBadge(w.dir), w.signal ? sigSpan(w.signal) : null, h('span', { class: 'tag' }, 'Structure ' + w.structure), h('span', { class: 'tag' }, 'TAT bias ' + w.bias), h('span', { class: 'num' }, 'Price ' + w.price))));
  const pair = brief && brief.pairs.find(p => p.sym === sym);
  if (pair) out.push(h('div', null, h('span', { class: `dir ${pair.dir}` }, `${pair.dir === 'bull' ? '▲ Structure-aligned buy' : '▼ Structure-aligned sell'} · score gap ${pair.diff}`)));

  // charts
  if (imgs && imgs.length) {
    const pick = [], seen = new Set();
    for (const i of imgs) { if (!seen.has(i.tf)) { seen.add(i.tf); pick.push(i); } }
    for (const i of imgs) { if (pick.length >= 6) break; if (!pick.includes(i)) pick.push(i); }
    out.push(card('Charts', `${imgs.length} captures`, h('div', { class: 'thumbs' }, pick.map(i => h('figure', null,
      h('img', { src: '/images/' + i.file, loading: 'lazy', alt: `${sym} ${i.tf}`, dataset: { full: '/images/' + i.file, cap: `${sym} · ${i.tf} · ${i.at}` } }),
      h('figcaption', null, `${i.tf} · ${i.at}`))))));
  }

  // TAT setups mentioning the symbol
  const tatHits = [];
  reps.forEach(rep => rep && rep.runs.slice().reverse().forEach(run => run.setups.filter(s => s.syms.includes(sym)).forEach(s => tatHits.push({ ...s, when: `${rep.date} ${run.time}` }))));
  if (tatHits.length) out.push(card('TAT analysis setups', `${tatHits.length} mentions`, h('div', { class: 'list' }, tatHits.slice(0, 6).map(s => {
    const li = setupLi(s); li.querySelector('.t').appendChild(h('span', { class: 'small muted' }, s.when)); return li;
  }))));

  // AHH ideas
  const ideas = (ahh || []).flatMap(n => n.ideas).filter(i => i.syms.includes(sym));
  if (ideas.length) out.push(card('Session ideas', `${ideas.length} mentions`, h('div', { class: 'list' }, ideas.slice(0, 8).map(i => h('div', { class: 'li' }, h('div', { class: 'body' },
    h('div', { class: 't' }, dirBadge(i.dir), h('span', { class: 'tag' }, `${i.session} · ${i.date}`)),
    h('div', { class: 'd' }, i.direction), i.levels ? h('div', { class: 'm' }, 'Levels: ' + i.levels) : null,
    i.setup ? h('div', { class: 'm clamp' }, i.setup) : null))))));

  // sentiment
  const sr = sent && sent.rows.find(r => r.sym === sym);
  if (sr) out.push(card('News sentiment', sent.date, h('div', { class: 'sentbar', style: { margin: '4px 0 8px' } },
    h('i', { style: { width: sr.pos + '%', background: 'var(--bull)' } }), h('i', { style: { width: sr.neu + '%', background: 'var(--neutral)' } }), h('i', { style: { width: sr.neg + '%', background: 'var(--bear)' } })),
    h('div', { class: 'small muted' }, `▲ ${sr.pos}% · ● ${sr.neu}% · ▼ ${sr.neg}% of ${sr.n} articles`), sr.summary ? h('div', { class: 'd', style: { marginTop: '6px' } }, sr.summary) : null));

  // events for its currencies
  const ccys = symCurrencies(sym), now = Date.now();
  const evs = ((cal && cal.events) || []).filter(e => ccys.includes(e.ccy) && e.impact !== 'Low' && evTime(e) > now && evTime(e) < now + 7 * 864e5).sort((a, b) => evTime(a) - evTime(b));
  if (evs.length) out.push(card(`Upcoming ${ccys.join(' / ')} events`, '7 days', h('div', { class: 'list' }, evs.slice(0, 8).map(e => h('div', { class: 'li' }, h('div', { class: 'body' },
    h('div', { class: 't' }, impactBadge(e.impact), h('span', { class: 'tag' }, e.ccy), e.event), h('div', { class: 'm' }, `${niceDate(e.date)} ${e.time} · in ${until(evTime(e) - now)}`)))))));

  // signal history
  out.push(card('Signal history', `${rows.length} signals`, rows.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, ['Date / time', 'Source', 'Signal', 'Price', 'Event'].map(c => h('th', null, c)))),
    h('tbody', null, rows.slice(0, 40).map(r => h('tr', null, h('td', { class: 'nowrap num' }, `${r.date} ${r.time.slice(0, 5)}`),
      h('td', null, h('span', { class: 'tag src' }, TF_SRC[r.src])), h('td', null, sigSpan(r.signal)), h('td', { class: 'num' }, r.price), h('td', { class: 'small wrap' }, r.event || r.sector)))))) : empty(S.sig ? 'No TAT signals on record' : 'Alert sheet still loading')));

  body.replaceChildren(...out);
  body.scrollTop = 0;
}
function closeOverlays() {
  if ($('#lightbox').classList.contains('show')) { $('#lightbox').classList.remove('show'); return; }
  if ($('#modal').classList.contains('show')) { $('#modal').classList.remove('show'); if (!$('#drawer').classList.contains('show')) $('#scrim').classList.remove('show'); return; }
  $('#drawer').classList.remove('show'); $('#scrim').classList.remove('show'); $('#dSym').textContent = '';
}

// ============================================================ views: JOURNAL
const FLAG_LABEL = {
  'high-fomo': 'FOMO ≥ 3', unplanned: 'Unplanned (self-rated)', 'no-wiki-plan': 'Not in wiki plan',
  revenge: 'Revenge (< 1h after a loss)', overtrading: 'Overtrading (4th+ trade of day)', 'no-stop': 'No stop', 'rules-broken': 'Rules broken',
};
const fmtR = r => r === null || r === undefined ? '—' : (r > 0 ? '+' : '') + Number(r).toFixed(2) + 'R';
const rSpan = r => h('span', { class: `num ${r > 0 ? 'up' : r < 0 ? 'down' : ''}` }, fmtR(r));
const tradeDir = t => t.direction === 'short' ? 'bear' : 'bull';
const hasR = t => t.status === 'closed' && t.result_r !== null && t.result_r !== undefined;
function rStats(list) {
  const rs = list.map(t => t.result_r), n = rs.length, tot = rs.reduce((a, b) => a + b, 0);
  return { n, tot: +tot.toFixed(2), avg: n ? +(tot / n).toFixed(2) : 0, win: n ? Math.round(100 * rs.filter(r => r > 0).length / n) : 0 };
}
function groupR(list, keyf) {
  const g = {};
  list.forEach(t => keyf(t).forEach(k => (g[k] = g[k] || []).push(t)));
  return Object.entries(g).map(([k, v]) => ({ k, ...rStats(v) })).sort((a, b) => a.tot - b.tot);
}
function rBreakdown(title, groups, note) {
  const c = card(title, note || '');
  if (!groups.length) { c.appendChild(empty('No closed trades yet')); return c; }
  const box = h('div'); c.appendChild(box);
  Charts.diverging(box, groups.map(g => ({ label: `${g.k} (${g.n})`, value: g.tot, tip: `avg ${fmtR(g.avg)} · win ${g.win}%` })), { aria: title, labelW: 130 });
  return c;
}
const fomoBucket = t => t.fomo === null || t.fomo === undefined ? 'unrated' : t.fomo <= 1 ? '0–1 low' : t.fomo < 3 ? '2 some' : '3+ high';

// ---------- journal form: writes go through POST /api/journal/* → scripts/journal.py (the journal's only writer)
const sgtNow = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Singapore', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date());
const TIME_RE = '\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}';
const fld = (label, input, opts = {}) => h('label', { class: `fld ${opts.wide ? 'wide' : ''}` }, h('span', { class: 'fl' }, label, opts.req ? h('b', { class: 'req' }, ' *') : null), input, opts.hint ? h('small', { class: 'muted' }, opts.hint) : null);
const inp = (name, attrs = {}) => h('input', { name, class: 'txt', autocomplete: 'off', ...attrs });
const num = (name, attrs = {}) => inp(name, { type: 'text', inputmode: 'decimal', pattern: '-?[0-9]*\\.?[0-9]*', ...attrs });
const sel = (name, opts, attrs = {}) => h('select', { name, ...attrs }, h('option', { value: '' }, '—'), opts.map(o => Array.isArray(o) ? h('option', { value: o[0] }, o[1]) : h('option', { value: o }, o)));
const area = (name, ph, attrs = {}) => h('textarea', { name, class: 'txt', rows: 3, placeholder: ph, ...attrs });
const pills = (name, opts, type = 'checkbox') => h('div', { class: 'pills' }, opts.map(o => h('label', { class: 'pill' }, h('input', { type, name, value: Array.isArray(o) ? o[0] : o }), h('span', null, Array.isArray(o) ? o[1] : o))));

function formData(form) {
  const fd = new FormData(form), out = {};
  for (const k of new Set(fd.keys())) {
    const v = fd.getAll(k).map(x => String(x).trim()).filter(Boolean);
    if (v.length) out[k] = form.querySelector(`[name="${k}"]`).type === 'checkbox' ? v : v[0];
  }
  return out;
}

function openJournalForm(title, fields, cmd, extra = {}) {
  const err = h('div', { class: 'ferr', role: 'alert' });
  const save = h('button', { class: 'btn primary', type: 'submit' }, 'Save to journal');
  const form = h('form', { class: 'jform', novalidate: false }, fields, err,
    h('div', { class: 'factions' }, h('button', { class: 'btn', type: 'button', onclick: closeOverlays }, 'Cancel'), save));
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const data = { ...extra, ...formData(form) };
    save.disabled = true; save.textContent = 'Saving…'; err.textContent = '';
    const res = await fetch('/api/journal/' + cmd, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Desk': '1' }, body: JSON.stringify(data) })
      .then(r => r.json()).catch(() => ({ ok: false, error: 'Server unreachable' }));
    save.disabled = false; save.textContent = 'Save to journal';
    if (!res.ok) { err.textContent = res.error || 'Save failed'; return; }
    closeOverlays(); delete cache['/api/journal']; toast(res.message || 'Saved'); render();
  });
  $('#mTitle').textContent = title;
  $('#mBody').replaceWith(h('div', { id: 'mBody', class: 'md' }, form));
  $('#modal').classList.add('show'); $('#scrim').classList.add('show');
  $('#modal .mb').scrollTop = 0;
}

async function newTradeForm() {
  const m = await api('/api/journal-meta');
  if (!m) { toast('Journal options unavailable'); return; }
  openJournalForm('Log a trade', [
    h('div', { class: 'fgrid' },
      fld('Symbol', inp('symbol', { required: true, list: 'symlist', placeholder: 'GBPAUD', autocapitalize: 'characters' }), { req: true }),
      fld('Direction', pills('direction', [['long', '▲ Long'], ['short', '▼ Short']], 'radio'), { req: true }),
      fld('Entry', num('entry')), fld('Stop', num('stop')), fld('Target', num('target')),
      fld('Size (lots/units)', num('size')), fld('Risk % of account', num('risk')),
      fld('Timeframe', sel('tf', ['15m', '1H', '4H', 'D', 'W'])),
      fld('Setup (signal / level)', inp('setup', { placeholder: 'TAT OptBull retest of MajD 1.9070' }), { wide: true }),
      fld('Idea came from', sel('source', m.sources)),
      fld('In your plan before the session?', sel('planned', ['yes', 'no'], { required: true }), { req: true }),
      fld('FOMO', sel('fomo', [0, 1, 2, 3, 4, 5].map(n => [n, n === 0 ? '0 — none' : n === 5 ? '5 — had to get in' : String(n)]), { required: true }), { req: true }),
      fld('Confidence', sel('confidence', [1, 2, 3, 4, 5].map(n => [n, String(n)]))),
      fld('Feeling right now', pills('emotion', m.emotions), { wide: true }),
      fld('Why are you taking this trade?', area('why', 'In your own words'), { wide: true }),
      fld('How do you feel?', area('feel', 'In your own words'), { wide: true }),
      fld('FOMO check (tick what is true)', h('div', { class: 'checks' }, m.checklist.map((c, i) => h('label', null, h('input', { type: 'checkbox', name: 'checks', value: i }), ' ', c))), { wide: true }),
      fld('Opened (SGT)', inp('opened', { value: sgtNow(), pattern: TIME_RE, placeholder: 'YYYY-MM-DD HH:MM' }), { hint: 'Change it to backfill an earlier trade' }),
    ),
  ], 'new');
  const dirs = $('#mBody').querySelectorAll('input[name=direction]'); dirs[0].required = true;
}

function commentForm(t) {
  openJournalForm(`Comment · ${t.symbol} ${t.direction} · ${t.opened}`, [
    h('div', { class: 'fgrid' },
      fld('Comment', area('text', 'Moved stop to BE, felt relieved…', { required: true, rows: 4 }), { req: true, wide: true }),
      fld('At (SGT)', inp('at', { value: sgtNow(), pattern: TIME_RE }))),
  ], 'comment', { ref: t.id });
}

async function closeTradeForm(t) {
  const m = await api('/api/journal-meta');
  if (!m) { toast('Journal options unavailable'); return; }
  openJournalForm(`Close · ${t.symbol} ${t.direction} · ${t.opened}`, [
    h('div', { class: 'fgrid' },
      fld('Exit price', num('exit'), { hint: t.entry != null ? `entry ${t.entry} · stop ${t.stop ?? '—'}` : null }),
      fld('Result in R', num('r'), { hint: 'Leave blank to compute from entry/stop/exit' }),
      fld('P&L (SGD)', num('pnl')),
      fld('Rules followed?', sel('rules', ['yes', 'partial', 'no'])),
      fld('Mistakes', pills('mistakes', m.mistakes), { wide: true }),
      fld('Exit & outcome notes', area('note', 'What happened, in your own words'), { wide: true }),
      fld('Closed (SGT)', inp('closed', { value: sgtNow(), pattern: TIME_RE })),
      fld('Never taken', h('label', { class: 'pill' }, h('input', { type: 'checkbox', name: 'cancel', value: '1' }), h('span', null, 'Cancel this trade')))),
  ], 'close', { ref: t.id });
}

async function viewJournal(root) {
  const all = (await api('/api/journal', { fresh: true })) || [];
  const f = F('journal', { range: 'all', status: 'all', flagged: false });
  const q = S.q;
  const cutoff = f.range === 'all' ? '' : addDays(sgtToday(), -Number(f.range));
  const inRange = all.filter(t => (t.opened || '') >= cutoff &&
    matches(q, t.symbol, t.direction, t.setup, t.idea_source, t.emotion_before, t.mistakes, t.flags, t.why, t.feel, t.comments.map(c => c.text)));
  const done = inRange.filter(hasR).sort((a, b) => (a.closed || a.opened || '').localeCompare(b.closed || b.opened || ''));
  const st = rStats(done);

  root.replaceChildren(h('div', { class: 'view-head' }, h('h1', null, 'Trade Journal'),
    h('span', { class: 'sub' }, 'Why you took each trade, how you felt, and what it cost · wiki/notes/journal/'),
    h('span', { style: { marginLeft: 'auto' } }, seg([{ v: '7', label: '7d' }, { v: '30', label: '30d' }, { v: '90', label: '90d' }, { v: 'all', label: 'All' }],
      f.range, v => { f.range = v; saveFilters(); render(); })),
    h('button', { class: 'btn primary', type: 'button', onclick: newTradeForm }, '＋ Log trade')));

  if (!all.length) {
    root.appendChild(card('No journal entries yet', null, h('div', { class: 'md' },
      h('p', null, h('button', { class: 'btn primary', type: 'button', onclick: newTradeForm }, '＋ Log your first trade')),
      h('p', null, 'Or from the terminal (it prompts for why, how you feel and the FOMO checklist):'),
      h('pre', null, 'python3 scripts/journal.py new GBPAUD long\npython3 scripts/journal.py comment GBPAUD "moved stop to BE"\npython3 scripts/journal.py close GBPAUD --exit 1.9150'),
      h('p', null, 'Or copy wiki/notes/journal/_template.md in Obsidian, or tell Claude about the trade.'))));
    return;
  }

  // streak = run of same-sign results ending at the latest closed trade
  let streak = 0;
  for (let i = done.length - 1; i >= 0; i--) {
    const s = Math.sign(done[i].result_r);
    if (!streak || Math.sign(streak) === s) streak += s || 0; else break;
    if (!s) break;
  }
  const fomoCost = rStats(done.filter(t => t.flags.includes('high-fomo')));
  const kpi = (lbl, val, foot) => h('div', { class: 'kpi' }, h('div', { class: 'lbl' }, lbl), h('div', { class: 'val' }, val), h('div', { class: 'foot' }, foot));
  root.appendChild(h('div', { class: 'kpis' },
    kpi('Trades', String(inRange.length), `${done.length} closed · ${inRange.filter(t => t.status === 'open').length} open`),
    kpi('Win rate', done.length ? `${st.win}%` : '—', `${done.filter(t => t.result_r > 0).length}W / ${done.filter(t => t.result_r <= 0).length}L`),
    kpi('Total R', rSpan(st.tot), `expectancy ${fmtR(st.avg)} / trade`),
    kpi('Streak', streak ? h('span', { class: streak > 0 ? 'up' : 'down' }, `${Math.abs(streak)} ${streak > 0 ? 'wins' : 'losses'}`) : '—', 'latest closed trades'),
    kpi('FOMO trades', fomoCost.n ? rSpan(fomoCost.tot) : '—', fomoCost.n ? `${fomoCost.n} trades · win ${fomoCost.win}%` : 'none with FOMO ≥ 3'),
  ));

  // equity curve + behaviour flags
  let cum = 0;
  const eqCard = card('Equity curve', `cumulative R · ${done.length} closed trades`);
  const eqBox = h('div'); eqCard.appendChild(eqBox);
  if (done.length) {
    Charts.lines(eqBox, done.map(t => shortDate((t.closed || t.opened).slice(0, 10))),
      [{ name: 'Cumulative R', color: 'var(--accent)', values: done.map(t => +(cum += t.result_r).toFixed(2)) }],
      { aria: 'Cumulative R', tipLabel: i => `${done[i].symbol} ${done[i].direction} · ${fmtR(done[i].result_r)}` });
  } else eqBox.appendChild(empty('No closed trades in range'));
  const flags = groupR(done, t => t.flags.length ? t.flags : ['clean']);
  const flagCard = card('Behaviour flags', 'what each pattern cost you', flags.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, ['Pattern', 'Trades', 'Total', 'Avg', 'Win'].map(c => h('th', null, c)))),
    h('tbody', null, flags.map(g => h('tr', null, h('td', null, g.k === 'clean' ? 'No flags ✓' : FLAG_LABEL[g.k] || g.k), h('td', { class: 'num' }, g.n),
      h('td', null, rSpan(g.tot)), h('td', null, rSpan(g.avg)), h('td', { class: 'num' }, `${g.win}%`)))))) : empty('No closed trades yet'),
    h('div', { class: 'small muted', style: { marginTop: '6px' } }, '"Not in wiki plan" means the symbol wasn\'t in that day\'s TAT report (runs before entry), Daily Signals or Daily Brief.'));
  root.appendChild(h('div', { class: 'grid g-wide' }, eqCard, flagCard));

  // psychology breakdowns
  root.appendChild(h('div', { class: 'grid g3 mt' },
    rBreakdown('By FOMO score', groupR(done, t => [fomoBucket(t)]), 'total R (trades)'),
    rBreakdown('By emotion before entry', groupR(done, t => t.emotion_before.length ? t.emotion_before : ['unrated'])),
    rBreakdown('Planned vs not', groupR(done, t => [`self: ${t.planned || 'unrated'}`, t.plan_evidence.length ? 'wiki: in plan' : 'wiki: not in plan'])),
  ));
  root.appendChild(h('div', { class: 'grid g3 mt' },
    rBreakdown('By idea source', groupR(done, t => [t.idea_source || 'unrated'])),
    rBreakdown('Mistakes', groupR(done.filter(t => t.mistakes.length), t => t.mistakes)),
    rBreakdown('By hour of entry (SGT)', groupR(done, t => [(t.opened || '').slice(11, 13) + ':00'])),
  ));

  // trade table
  const rows = inRange.filter(t => (f.status === 'all' || t.status === f.status) && (!f.flagged || t.flags.some(x => x !== 'no-wiki-plan')))
    .sort((a, b) => (b.opened || '').localeCompare(a.opened || ''));
  const tbl = card('Trades', h('span', { style: { display: 'inline-flex', gap: '8px' } },
    seg([{ v: 'all', label: 'All' }, { v: 'open', label: 'Open' }, { v: 'closed', label: 'Closed' }, { v: 'cancelled', label: 'Cancelled' }], f.status, v => { f.status = v; saveFilters(); render(); }),
    seg([{ v: true, label: '⚑ Flagged only' }], f.flagged ? true : null, () => { f.flagged = !f.flagged; saveFilters(); render(); })),
    rows.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ['Opened (SGT)', 'Instrument', 'Setup / why', 'Feeling', 'FOMO', 'Result', 'Flags', 'Notes', ''].map(c => h('th', null, c)))),
      h('tbody', null, rows.map(t => h('tr', { style: { cursor: 'pointer' }, title: 'Open journal entry', onclick: e => { if (!e.target.closest('[data-sym]')) openDoc(t.path, `${t.symbol} ${t.direction} · ${t.opened}`); } },
        h('td', { class: 'nowrap num' }, t.opened || '—'),
        h('td', { class: 'nowrap' }, symChip(t.symbol, tradeDir(t)), ' ', dirBadge(tradeDir(t))),
        h('td', { class: 'wrap' }, t.setup ? h('div', null, t.setup) : null, t.why ? h('div', { class: 'small muted clamp' }, t.why) : null),
        h('td', null, t.emotion_before.map(e => h('span', { class: 'tag' }, e))),
        h('td', { class: 'num' }, t.fomo ?? '—'),
        h('td', { class: 'nowrap' }, t.status === 'closed' ? rSpan(t.result_r) : h('span', { class: 'tag' }, t.status)),
        h('td', null, t.flags.map(x => h('span', { class: `tag flag ${x}`, title: FLAG_LABEL[x] || x }, x)),
          t.mistakes.map(x => h('span', { class: 'tag mistake' }, x))),
        h('td', { class: 'small nowrap' }, t.comments.length ? `💬 ${t.comments.length}` : '', t.checklist.done ? ` ✓ ${t.checklist.done}/${t.checklist.total}` : ''),
        h('td', { class: 'nowrap', onclick: e => e.stopPropagation() },
          h('button', { class: 'btn sm', type: 'button', title: 'Add a comment', onclick: () => commentForm(t) }, '💬'),
          t.status === 'open' ? h('button', { class: 'btn sm', type: 'button', onclick: () => closeTradeForm(t) }, 'Close') : null)))))) : empty('No trades match'));
  root.appendChild(h('div', { class: 'mt' }, tbl));

  // recent comments across all trades
  const comments = inRange.flatMap(t => t.comments.map(c => ({ ...c, t }))).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 12);
  if (comments.length) root.appendChild(h('div', { class: 'mt' }, card('Recent thoughts', `${comments.length} latest comments`, h('div', { class: 'list' }, comments.map(c => h('div', { class: 'li' }, h('div', { class: 'body' },
    h('div', { class: 't' }, symChip(c.t.symbol, tradeDir(c.t)), h('span', { class: 'small muted' }, c.at)),
    h('div', { class: 'd' }, c.text))))))));
}

// ============================================================ performance (broker statement logs)
const money = (v, d = 2) => v === null || v === undefined ? '—' : (v < 0 ? '−' : '') + 'S$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const moneySpan = (v, d) => h('span', { class: `num ${v > 0 ? 'up' : v < 0 ? 'down' : ''}` }, money(v, d));
const pct = (v, d = 1) => v === null || v === undefined ? '—' : (100 * v).toFixed(d) + '%';
const hrs = v => { if (!v) return '—'; const m = Math.round(v * 60); return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`; };
const sinceOf = r => r === 'all' ? '' : r === 'ytd' ? sgtToday().slice(0, 4) + '-01-01' : addDays(sgtToday(), -Number(r));

async function viewPerformance(root) {
  const f = F('performance', { account: 'all', range: 'all', sort: 'deals', sym: '' });
  const since = sinceOf(f.range);
  const qs = `/api/performance?account=${f.account}${since ? '&since=' + since : ''}`;
  const d = await api(qs, { fresh: !!S.perfRefresh });
  S.perfRefresh = false;
  const head = h('div', { class: 'view-head' }, h('h1', null, 'Performance'),
    h('span', { class: 'sub' }, 'Realised P&L from the AXI and Fusion statement logs · SGD · times in SGT'),
    h('span', { style: { marginLeft: 'auto', display: 'inline-flex', gap: '8px', flexWrap: 'wrap' } },
      seg([{ v: 'all', label: 'All' }, { v: 'axi', label: 'AXI' }, { v: 'fusion', label: 'Fusion' }], f.account, v => { f.account = v; f.sym = ''; saveFilters(); render(); }),
      seg([{ v: '30', label: '30d' }, { v: '90', label: '90d' }, { v: 'ytd', label: 'YTD' }, { v: '365', label: '1y' }, { v: 'all', label: 'All' }], f.range, v => { f.range = v; saveFilters(); render(); }),
      h('button', { class: 'btn', type: 'button', title: 'Re-read both sheets now', onclick: async () => { toast('Refreshing statements…'); await api(qs + '&refresh=1', { fresh: true }); S.perfRefresh = true; render(); } }, '↻')));
  if (!d) { root.replaceChildren(head, card('Statements unavailable', null, empty('The server could not load the statement logs.'))); return; }
  const st = d.stats, acc = d.accounts;
  const age = d.status.fetchedAt ? Math.round((Date.now() / 1000 - d.status.fetchedAt) / 60) : null;
  const status = h('div', { class: 'small muted', style: { margin: '-6px 0 12px' } },
    Object.values(acc).map(a => `${a.label}: ${a.trades} trades (${(a.first || '').slice(0, 10)} → ${(a.last || '').slice(0, 10)})`).join(' · '),
    age !== null ? ` · ${d.status.source === 'snapshot' ? 'saved copy' : 'fetched'} ${age < 1 ? 'just now' : age + ' min ago'}` : '',
    d.status.error ? h('span', { class: 'down' }, ` · sheet error: ${d.status.error}`) : null);
  root.replaceChildren(head, status);
  if (!st.trades) { root.appendChild(card('No closed trades in range', null, empty('Try a longer range or another account.'))); return; }

  const kpi = (lbl, val, foot) => h('div', { class: 'kpi' }, h('div', { class: 'lbl' }, lbl), h('div', { class: 'val' }, val), h('div', { class: 'foot' }, foot));
  root.appendChild(h('div', { class: 'kpis' },
    kpi('Net realised P&L', moneySpan(st.net), `gross ${money(st.gross)} · swap ${money(st.swap)}`),
    kpi('Win rate', pct(st.winRate, 2), `${st.wins} W · ${st.losses} L · ${st.be} BE`),
    kpi('Trades closed', String(st.trades), `${st.long.deals} long (${pct(st.long.deals / st.trades, 0)}) · ${st.short.deals} short`),
    kpi('Commissions', moneySpan(st.commission), `avg ${money(st.avgCommission)} / deal`),
    kpi('Streak', st.streak ? h('span', { class: st.streak > 0 ? 'up' : 'down' }, `${Math.abs(st.streak)} ${st.streak > 0 ? 'wins' : 'losses'}`) : '—', 'latest closed trades'),
  ));
  root.appendChild(h('div', { class: 'kpis' },
    kpi('Average win', moneySpan(st.avgWin), `total gains ${money(st.totalGains)}`),
    kpi('Average loss', moneySpan(st.avgLoss), `total losses ${money(st.totalLosses)}`),
    kpi('Profit factor', st.profitFactor === null ? '—' : st.profitFactor.toFixed(2), `win/loss ratio ${st.wlRatio === null ? '—' : st.wlRatio.toFixed(2)}`),
    kpi('Largest gain / loss', h('span', { style: { display: 'flex', flexWrap: 'wrap', columnGap: '8px' } }, moneySpan(st.largestGain), moneySpan(st.largestLoss)), `best ${st.bestSymbol || '—'} · worst ${st.worstSymbol || '—'}`),
    kpi('Expectancy', moneySpan(st.expectancy), 'average net per trade'),
  ));

  // equity curve (trading P&L only) + drawdown
  const eq = st.equity;
  let peak = -Infinity;
  const dd = eq.map(p => { peak = Math.max(peak, p.cum); return +(p.cum - peak).toFixed(2); });
  const eqBox = h('div');
  const eqCard = card('Equity curve', `cumulative net P&L and drawdown (DD) · ${eq.length} trades`, eqBox,
    h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Trading P&L only: deposits, withdrawals and transfers are left out so they don\'t show up as gains or drawdowns.'));
  Charts.lines(eqBox, eq.map(p => p.t.slice(2, 10)), [
    { name: 'P&L', color: 'var(--accent)', values: eq.map(p => p.cum) },
    { name: 'DD', color: 'var(--bear)', values: dd }],
    { aria: 'Cumulative net P&L and drawdown', height: 240, tipLabel: i => `${eq[i].t.slice(0, 16)}` });
  const monBox = h('div');
  const monCard = card('Monthly P&L', `${st.monthly.length} months`, monBox);
  Charts.diverging(monBox, st.monthly.slice(-18).reverse().map(m => ({ label: m.month, value: Math.round(m.net), tip: `${m.deals} trades · win ${pct(m.winRate, 0)}` })), { aria: 'Monthly net P&L', labelW: 70 });
  root.appendChild(h('div', { class: 'grid g-wide' }, eqCard, monCard));

  // capital + hold time
  const kv = rows => h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' }, h('tbody', null, rows.map(([k, v]) => h('tr', null, h('td', null, k), h('td', { class: 'num', style: { textAlign: 'right' } }, v))))));
  const b = st.balance, e = st.equityDD;
  const notes = Object.values(acc).filter(a => f.account === 'all' || a.label.toLowerCase() === f.account).flatMap(a => a.notes.map(n => `${a.label}: ${n}`));
  root.appendChild(h('div', { class: 'grid g3 mt' },
    card('Drawdown & account capital', 'balance includes cash movements', kv([
      ['Peak account balance', money(b.peak)], ['Lowest balance (trough)', money(b.trough)], ['Latest balance', money(b.last)],
      ['Max peak-to-trough drawdown (balance)', h('span', null, money(b.dd), ' · ', pct(b.ddPct, 2))],
      ['Max drawdown (trading P&L only)', h('span', null, money(e.dd), ' · ', pct(e.ddPct, 2))],
      ['Balance at start of range', money(e.start)]]),
      notes.length ? h('ul', { class: 'small muted', style: { margin: '8px 0 0', paddingLeft: '18px' } }, notes.map(n => h('li', null, n))) : null),
    card('Holding duration', null, kv([
      ['Average hold (all trades)', hrs(st.hold.all)], ['Average hold (winners)', hrs(st.hold.win)],
      ['Average hold (losers)', hrs(st.hold.loss)], ['Longest position held', hrs(st.hold.max)]]),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, st.hold.win > st.hold.loss * 1.2 ? 'Winners are held longer than losers.' : st.hold.loss > st.hold.win * 1.2 ? 'Losers are held longer than winners. Check whether stops are being moved.' : '')),
    card('Long vs short', null, kv([
      ['Long', h('span', null, `${st.long.deals} · win ${pct(st.long.winRate, 0)} · `, moneySpan(st.long.net))],
      ['Short', h('span', null, `${st.short.deals} · win ${pct(st.short.winRate, 0)} · `, moneySpan(st.short.net))],
      ...st.classes.map(c => [c.cls, h('span', null, `${c.deals} · win ${pct(c.winRate, 0)} · `, moneySpan(c.net))])]))));

  // day of week + hour of day
  const bucketRow = (label, r) => h('tr', null, h('td', null, label), h('td', { class: 'num' }, r.deals), h('td', { class: 'num' }, r.wins), h('td', { class: 'num' }, r.losses),
    h('td', { class: 'num' }, pct(r.winRate, 1)), h('td', null, moneySpan(r.avg)), h('td', null, moneySpan(r.net)));
  const bucketHead = first => h('thead', null, h('tr', null, [first, 'Deals', 'Wins', 'Losses', 'Win rate', 'Avg P&L', 'Net P&L'].map(c => h('th', null, c))));
  const days = st.dow.filter(r => r.deals);
  const tot = { deals: st.trades, wins: st.wins, losses: st.losses, winRate: st.winRate, avg: st.expectancy, net: st.net };
  const hourBox = h('div');
  Charts.diverging(hourBox, st.hours.filter(r => r.deals).map(r => ({ label: `${String(r.hour).padStart(2, '0')}:00 (${r.deals})`, value: Math.round(r.net), tip: `win ${pct(r.winRate, 0)} · avg ${money(r.avg)}` })), { aria: 'Net P&L by hour closed', labelW: 84 });
  root.appendChild(h('div', { class: 'grid g2 mt' },
    card('Day-of-week performance', 'by close day (SGT)', h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' }, bucketHead('Day'),
      h('tbody', null, days.map(r => bucketRow(r.day, r)), h('tr', { style: { fontWeight: 600 } }, bucketRow('Total', tot).childNodes))))),
    card('By hour closed (SGT)', 'net P&L (deals)', hourBox)));

  // symbol table
  const sorters = { deals: (a, b) => b.deals - a.deals, net: (a, b) => b.net - a.net, worst: (a, b) => a.net - b.net, win: (a, b) => b.winRate - a.winRate };
  const syms = st.symbols.filter(r => matches(S.q, r.symbol, r.cls)).sort(sorters[f.sort] || sorters.deals);
  root.appendChild(h('div', { class: 'mt' }, card('Symbol performance', seg([{ v: 'deals', label: 'Most traded' }, { v: 'net', label: 'Best' }, { v: 'worst', label: 'Worst' }, { v: 'win', label: 'Win rate' }], f.sort, v => { f.sort = v; saveFilters(); render(); }),
    h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ['Symbol', 'Class', 'Deals', 'Wins', 'Losses', 'Win rate', 'Avg P&L', 'Net P&L'].map(c => h('th', null, c)))),
      h('tbody', null, syms.map(r => h('tr', { style: { cursor: 'pointer' }, class: f.sym === r.symbol ? 'sel' : '', title: 'Show this symbol\'s trades',
        onclick: e => { if (e.target.closest('[data-sym]')) return; f.sym = f.sym === r.symbol ? '' : r.symbol; saveFilters(); render(); } },
        h('td', { class: 'nowrap' }, symChip(r.symbol)), h('td', null, h('span', { class: 'tag' }, r.cls)), h('td', { class: 'num' }, r.deals), h('td', { class: 'num' }, r.wins), h('td', { class: 'num' }, r.losses),
        h('td', { class: 'num' }, pct(r.winRate, 1)), h('td', null, moneySpan(r.avg)), h('td', null, moneySpan(r.net)))),
        h('tr', { style: { fontWeight: 600 } }, h('td', null, 'Total'), h('td'), h('td', { class: 'num' }, st.trades), h('td', { class: 'num' }, st.wins), h('td', { class: 'num' }, st.losses),
          h('td', { class: 'num' }, pct(st.winRate, 1)), h('td', null, moneySpan(st.expectancy)), h('td', null, moneySpan(st.net)))))))));

  // trades list
  const list = d.list.filter(t => (!f.sym || t.symbol === f.sym) && matches(S.q, t.symbol, t.account, t.side));
  root.appendChild(h('div', { class: 'mt' }, card(f.sym ? `Trades · ${f.sym}` : 'Trades', h('span', null, `${list.length} shown${d.list.length >= 500 ? ' (latest 500)' : ''}`,
    f.sym ? h('button', { class: 'btn sm', type: 'button', style: { marginLeft: '8px' }, onclick: () => { f.sym = ''; saveFilters(); render(); } }, 'Clear') : null),
    list.length ? h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
      h('thead', null, h('tr', null, ['Closed (SGT)', 'Account', 'Instrument', 'Size', 'Entry → exit', 'Held', 'Comm + swap', 'Net'].map(c => h('th', null, c)))),
      h('tbody', null, list.slice(0, 300).map(t => h('tr', null,
        h('td', { class: 'nowrap num' }, (t.close || '').slice(0, 16)), h('td', null, h('span', { class: 'tag' }, acc[t.account].label)),
        h('td', { class: 'nowrap' }, symChip(t.symbol, t.side === 'long' ? 'bull' : 'bear'), ' ', dirBadge(t.side === 'long' ? 'bull' : 'bear')),
        h('td', { class: 'num' }, t.size), h('td', { class: 'num nowrap' }, `${t.entry} → ${t.exit}`), h('td', { class: 'num nowrap' }, hrs(t.hold)),
        h('td', null, moneySpan(+(t.commission + t.swap).toFixed(2))), h('td', null, moneySpan(t.net)))))))
      : empty('No trades match'))));
}

// ============================================================ routing & rendering
const VIEWS = { desk: viewDesk, signals: viewSignals, analysis: viewAnalysis, calendar: viewCalendar, ahh: viewAhh, brief: viewBrief, 'my-watchlist': viewMyWatchlist, journal: viewJournal, performance: viewPerformance };
let renderSeq = 0;
async function render() {
  const seq = ++renderSeq, view = S.view, root = $('#view-' + view);
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + view));
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.view === view));
  if (view !== 'calendar') clearInterval(cdTimer);
  root.classList.add('loading');
  const tmp = document.createElement('section');
  try {
    await VIEWS[view](tmp);
  } catch (e) {
    console.error(e);
    tmp.replaceChildren(card('Something went wrong', null, h('pre', { class: 'small' }, String(e && e.stack || e))));
  }
  if (seq !== renderSeq) return;
  const y = window.scrollY;
  root.replaceChildren(...tmp.childNodes);
  root.classList.remove('loading');
  // charts measured 0-width while detached: re-trigger their mount now that they are in the DOM
  root.querySelectorAll('.chart').forEach(c => { c._w = null; });
  window.dispatchEvent(new Event('resize'));
  window.scrollTo(0, y);
}
function go(view) { if (location.hash !== '#' + view) location.hash = view; else { S.view = view; render(); } }
function route() {
  const hash = location.hash.slice(1);
  if (hash.startsWith('sym=')) { openSymbol(decodeURIComponent(hash.slice(4))); return; }
  const v = VIEWS[hash] ? hash : 'desk';
  if (v !== S.view || !$('#view-' + v).childNodes.length) { S.view = v; store.set('view', v); window.scrollTo(0, 0); render(); }
}
function setQuery(q) { $('#q').value = q; S.q = q; }

// ============================================================ terminal chrome: clock, sessions, tape
const SESSION_DEFS = [['TKY', 'Asia/Tokyo', 9, 18], ['LDN', 'Europe/London', 8, 17], ['NYC', 'America/New_York', 8, 17]];
function setSidebar(collapsed) {
  document.documentElement.classList.toggle('side-collapsed', collapsed);
  const b = $('#sideToggle');
  b.textContent = collapsed ? '»' : '«';
  b.title = collapsed ? 'Expand sidebar ([)' : 'Collapse sidebar ([)';
  b.setAttribute('aria-label', b.title); b.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  store.set('sideCollapsed', collapsed);
  tickClock();
  setTimeout(() => { document.querySelectorAll('.chart').forEach(c => { c._w = null; }); window.dispatchEvent(new Event('resize')); }, 180);
}
function tickClock() {
  const now = new Date();
  const clk = $('#clock'), t = now.toLocaleTimeString('en-GB', { hour12: false, timeZone: 'Asia/Singapore' });
  clk.replaceChildren(document.createTextNode(document.documentElement.classList.contains('side-collapsed') ? t.slice(0, 5) : t), h('span', { class: 'tz' }, ' SGT'));
  $('#sessions').replaceChildren(...SESSION_DEFS.map(([n, tz, o, c]) => {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: 'numeric', hour12: false, weekday: 'short' })
      .formatToParts(now).map(x => [x.type, x.value]));
    const hr = +p.hour % 24, open = !['Sat', 'Sun'].includes(p.weekday) && hr >= o && hr < c;
    return h('span', { class: open ? 'on' : '', title: `${n} ${open ? 'open' : 'closed'}` }, n);
  }));
}
const TAPE_PX_PER_SEC = 50;
async function renderTape() {
  const rows = sigRows().filter(r => r.dir === 'bull' || r.dir === 'bear').slice(0, 40);
  const news = await api('/api/news');
  const items = [];
  const heads = ((news && news.market) || []).slice(0, 14);
  const headline = n => h('a', { class: 'it news', href: n.url, target: '_blank', rel: 'noopener noreferrer', title: n.title },
    h('b', null, 'NEWS'), h('span', { class: 'hd' }, n.title.length > 95 ? n.title.slice(0, 94) + '…' : n.title),
    h('span', { class: 'tm' }, n.time.slice(5)));
  rows.forEach((r, i) => {
    items.push(h('span', { class: `it ${r.dir}`, dataset: { sym: r.sym } },
      h('b', null, r.sym), h('span', { class: 'ar' }, r.dir === 'bull' ? '▲' : '▼'), h('span', { class: 'sg' }, r.signal || ''),
      h('span', { class: 'tm' }, `${r.src} ${shortDate(r.date)}${r.time ? ' ' + r.time : ''}`)));
    if (i % 3 === 2 && heads.length) items.push(headline(heads.shift()));  // one headline per three signals
  });
  heads.forEach(n => items.push(headline(n)));
  const tape = $('#tape');
  if (!items.length) { tape.replaceChildren(h('span', { class: 'it' }, h('span', { class: 'tm' }, 'Waiting for signals…'))); return; }
  // two copies so the -50% keyframe loops seamlessly
  const clone = () => items.map(n => n.cloneNode(true));
  const trk = h('div', { class: 'trk' }, ...items, ...clone());
  tape.replaceChildren(trk);
  // constant scroll speed whatever the item count: one loop = half the track width
  requestAnimationFrame(() => { trk.style.animationDuration = Math.max(20, trk.scrollWidth / 2 / TAPE_PX_PER_SEC) + 's'; });
}
// An open tab re-reads the server's cached news every 5 min (a local read, never a moomoo call) and swaps in
// only the news card + tape when the server's pull time has changed, so scroll position elsewhere is kept.
const NEWS_POLL_MS = 5 * 60 * 1000;
let newsPolledAt = Date.now();
async function pollNews() {
  newsPolledAt = Date.now();
  const prev = await api('/api/news');
  const next = await api('/api/news', { fresh: true });
  if (!next || !next.fetchedAt || (prev && prev.fetchedAt === next.fetchedAt)) return;
  renderTape();
  const old = $('[data-news]');
  if (S.view === 'desk' && old && old.isConnected) {
    const list = old.querySelector('.list'), top = list ? list.scrollTop : 0;
    const fresh = newsCard(next);
    fresh.className = old.className;
    old.replaceWith(fresh);
    const nl = fresh.querySelector('.list'); if (nl) nl.scrollTop = top;
  }
}
const COMMANDS = {
  desk: 'desk', home: 'desk', signals: 'signals', sig: 'signals', tat: 'signals', analysis: 'analysis', an: 'analysis',
  calendar: 'calendar', cal: 'calendar', econ: 'calendar', news: 'desk', ahh: 'ahh', sessions: 'ahh', ideas: 'ahh',
  brief: 'brief', daily: 'brief', watchlist: 'my-watchlist', wl: 'my-watchlist', journal: 'journal', jnl: 'journal',
  performance: 'performance', perf: 'performance', pnl: 'performance',
};

// ============================================================ boot
function wire() {
  let t = null;
  $('#q').addEventListener('input', e => {
    clearTimeout(t);
    t = setTimeout(() => { S.q = e.target.value.trim(); render(); }, 160);
  });
  $('#q').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const cmd = COMMANDS[e.target.value.trim().replace(/^[:>]/, '').toLowerCase()];
      if (cmd) { e.target.value = ''; S.q = ''; e.target.blur(); go(cmd); return; }
      const v = e.target.value.trim().toUpperCase();
      const known = (S.meta && S.meta.symbols) || [];
      if (known.includes(v) || sigRows().some(r => r.sym === v)) openSymbol(v);
    } else if (e.key === 'Escape') { e.target.value = ''; S.q = ''; render(); e.target.blur(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) { e.preventDefault(); $('#q').focus(); $('#q').select(); }
    if (e.key === 'Escape' && document.activeElement !== $('#q')) closeOverlays();
    if (e.key === '[' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) $('#sideToggle').click();
    if (/^[1-9]$/.test(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      const a = document.querySelectorAll('#nav a')[+e.key - 1]; if (a) go(a.dataset.view);
    }
  });
  document.addEventListener('click', e => {
    const s = e.target.closest('[data-sym]');
    if (s) { e.preventDefault(); openSymbol(s.dataset.sym); return; }
    const d = e.target.closest('[data-doc]');
    if (d) { e.preventDefault(); openDoc(d.dataset.doc, d.textContent); return; }
    const img = e.target.closest('img[data-full]');
    if (img) {
      const scope = img.closest('.wgrid') || img.parentElement;
      const imgs = [...scope.querySelectorAll('img[data-full]')];
      lightbox(img.dataset.full, img.dataset.cap, imgs.map(i => ({ full: i.dataset.full, cap: i.dataset.cap, thumb: i.getAttribute('src') })), imgs.indexOf(img));
    }
  });
  // lightbox: the track scrolls natively (swipe / trackpad); sync the index when a scroll settles
  const lbTrack = $('#lbTrack'), lbStrip = $('#lbStrip');
  let lbScrollT = null, lbDrag = null, lbMoved = false, lbWheelAt = 0;
  lbTrack.addEventListener('scroll', () => {
    clearTimeout(lbScrollT);
    lbScrollT = setTimeout(() => {
      const i = Math.round(lbTrack.scrollLeft / Math.max(1, lbTrack.clientWidth));
      if (lbAuto !== null) { if (i === lbAuto) lbAuto = null; return; }
      if (i !== lbIdx && i >= 0 && i < lbGroup.length) { lbIdx = i; lbShow(); }
    }, 90);
  }, { passive: true });
  // mouse: a vertical wheel flips one chart (horizontal trackpad scrolling is left to the browser)
  lbTrack.addEventListener('wheel', e => {
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY) || lbGroup.length < 2) return;
    e.preventDefault();
    const now = Date.now();
    if (now - lbWheelAt > 350 && Math.abs(e.deltaY) > 4) { lbWheelAt = now; lbStep(e.deltaY > 0 ? 1 : -1); }
  }, { passive: false });
  // mouse: click-and-drag pans the track, then snaps to the nearest chart
  lbTrack.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse' || lbGroup.length < 2) return;
    lbDrag = { x: e.clientX, left: lbTrack.scrollLeft }; lbMoved = false;
    lbTrack.classList.add('dragging');
  });
  window.addEventListener('pointermove', e => {
    if (!lbDrag) return;
    const dx = e.clientX - lbDrag.x;
    if (Math.abs(dx) > 5) lbMoved = true;
    lbTrack.scrollLeft = lbDrag.left - dx;
  });
  window.addEventListener('pointerup', e => {
    if (!lbDrag) return;
    const dx = e.clientX - lbDrag.x, w = lbTrack.clientWidth;
    lbDrag = null; lbTrack.classList.remove('dragging');
    if (lbMoved) lbGo(Math.abs(dx) > w * 0.15 ? lbIdx + (dx < 0 ? 1 : -1) : lbIdx);
  });
  // the thumbnail strip scrolls sideways with a plain mouse wheel too
  lbStrip.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); lbStrip.scrollLeft += e.deltaY; }
  }, { passive: false });
  $('#lightbox').addEventListener('click', e => {
    if (lbMoved) { lbMoved = false; return; }   // end of a drag, not a click
    const to = e.target.closest('[data-lbto]');
    if (to) { lbGo(+to.dataset.lbto); return; }
    const nav = e.target.closest('[data-lb]');
    if (nav) { lbStep(+nav.dataset.lb); return; }
    if (e.target.closest('#lbStrip')) return;
    $('#lightbox').classList.remove('show');
  });
  window.addEventListener('resize', () => { if ($('#lightbox').classList.contains('show')) lbGo(lbIdx, false); });
  document.addEventListener('keydown', e => {
    if (!$('#lightbox').classList.contains('show')) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); lbStep(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); lbStep(1); }
  });
  $('#scrim').addEventListener('click', closeOverlays);
  $('#dClose').addEventListener('click', () => { $('#drawer').classList.remove('show'); if (!$('#modal').classList.contains('show')) $('#scrim').classList.remove('show'); $('#dSym').textContent = ''; });
  $('#mClose').addEventListener('click', () => { $('#modal').classList.remove('show'); if (!$('#drawer').classList.contains('show')) $('#scrim').classList.remove('show'); });
  $('#refreshBtn').addEventListener('click', async () => {
    $('#sheetDot').className = 'dot busy'; $('#sheetLbl').textContent = 'Refreshing…';
    for (const k of Object.keys(cache)) delete cache[k];
    S.meta = await api('/api/meta');
    cache['/api/news'] = Promise.resolve(await api('/api/news?refresh=1', { fresh: true }));
    await loadSignals(true);
    fillSymbols(); renderTape(); render(); toast('Wiki + alert sheet reloaded');
  });
  $('#themeBtn').addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next; store.set('theme', next);
  });
  window.addEventListener('hashchange', route);
}
function fillSymbols() {
  const set = new Set([...((S.meta && S.meta.symbols) || []), ...sigRows().map(r => r.sym)]);
  $('#symlist').replaceChildren(...[...set].sort().map(s => h('option', { value: s })));
}

(async function boot() {
  const theme = store.get('theme', null);
  if (theme) document.documentElement.dataset.theme = theme;
  wire();
  $('#sideToggle').addEventListener('click', () => setSidebar(!document.documentElement.classList.contains('side-collapsed')));
  setSidebar(store.get('sideCollapsed', false));
  setInterval(tickClock, 1000);
  S.view = VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : store.get('view', 'desk');
  S.meta = await api('/api/meta');
  updateSheetStatus();
  const hash = location.hash.slice(1);
  if (!VIEWS[hash] && !hash.startsWith('sym=')) history.replaceState(null, '', '#' + S.view);
  render();
  if (hash.startsWith('sym=')) openSymbol(decodeURIComponent(hash.slice(4)));
  // the alert sheet takes a few seconds on first load; render again once it lands
  await loadSignals();
  fillSymbols(); renderTape();
  if (['desk', 'signals'].includes(S.view)) render();
  setInterval(pollNews, NEWS_POLL_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - newsPolledAt > NEWS_POLL_MS) pollNews(); });
  let lastFetch = S.sig && S.sig.status && S.sig.status.fetchedAt;
  setInterval(async () => {
    await loadSignals();
    const f = S.sig && S.sig.status && S.sig.status.fetchedAt;
    if (f && f !== lastFetch) {
      lastFetch = f; fillSymbols(); renderTape();
      if (['desk', 'signals'].includes(S.view) && !$('#drawer').classList.contains('show')) render();
    }
  }, 60000);
})();

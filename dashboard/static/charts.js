/* Minimal SVG chart primitives for the Trading Desk.
 * Colors come from CSS custom properties so light/dark themes swap in one place.
 * Every chart is interactive: per-mark tooltips on bars, crosshair + all-series
 * readout on lines. Labels go in via textContent (data is treated as untrusted). */
const Charts = (() => {
  const NS = 'http://www.w3.org/2000/svg';

  function s(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs || {}) if (attrs[k] !== undefined && attrs[k] !== null) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  }
  function text(parent, x, y, str, attrs) {
    const t = s('text', Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }

  // ---------- tooltip ----------
  const tipEl = () => document.getElementById('tooltip');
  function showTip(evt, header, rows) {
    const el = tipEl();
    el.replaceChildren();
    if (header) {
      const h = document.createElement('div'); h.className = 'tt-h'; h.textContent = header; el.appendChild(h);
    }
    for (const r of rows) {
      const row = document.createElement('div'); row.className = 'tt-r';
      if (r.color) { const k = document.createElement('span'); k.className = 'ln'; k.style.background = r.color; row.appendChild(k); }
      const b = document.createElement('b'); b.textContent = r.value; row.appendChild(b);
      const n = document.createElement('span'); n.className = 'n'; n.textContent = r.label; row.appendChild(n);
      el.appendChild(row);
    }
    el.classList.add('show');
    moveTip(evt);
  }
  function moveTip(evt) {
    const el = tipEl();
    const pad = 14, w = el.offsetWidth, h = el.offsetHeight;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
    el.style.left = x + 'px'; el.style.top = y + 'px';
  }
  function hideTip() { tipEl().classList.remove('show'); }

  // ---------- mounting: re-render on resize ----------
  const observers = new WeakMap();
  function mount(container, render) {
    const draw = () => {
      const w = Math.max(240, Math.floor(container.clientWidth));
      if (container._w === w) return;
      container._w = w;
      container.replaceChildren();
      render(w);
    };
    if (observers.has(container)) observers.get(container).disconnect();
    const ro = new ResizeObserver(draw);
    ro.observe(container);
    observers.set(container, ro);
    container._w = null;
    draw();
  }

  function niceMax(v) {
    if (v <= 4) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  // Path for a bar whose data-end (top) is rounded and whose baseline end is square.
  function barPath(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    if (h <= 0) return '';
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function hbarPath(x0, y, len, h, r, dir) {
    // horizontal bar from x0, extending len in dir (+1 right / -1 left), rounded at the far end
    r = Math.min(r, h / 2, Math.abs(len));
    if (len <= 0) return '';
    if (dir > 0) {
      const x1 = x0 + len;
      return `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - r},${y + h}H${x0}Z`;
    }
    const x1 = x0 - len;
    return `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 + r},${y + h}H${x0}Z`;
  }

  // ---------- stacked vertical bars ----------
  // data: [{label, tip, values:{key:n}}], series: [{key, name, color}] bottom→top
  function stacked(container, data, series, opts = {}) {
    const H = opts.height || 190;
    const legend = document.createElement('div'); legend.className = 'legend';
    for (const sr of series) {
      const k = document.createElement('span'); k.className = 'k';
      const sw = document.createElement('i'); sw.className = 'sw'; sw.style.background = sr.color;
      k.append(sw, document.createTextNode(sr.name)); legend.appendChild(k);
    }
    const holder = document.createElement('div'); holder.className = 'chart';
    container.replaceChildren(holder, legend);
    if (!data.length) { holder.innerHTML = '<div class="empty">No data in range</div>'; return; }
    mount(holder, (W) => {
      const m = { l: 30, r: 6, t: 8, b: 22 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const tot = data.map(d => series.reduce((a, sr) => a + (d.values[sr.key] || 0), 0));
      const ymax = niceMax(Math.max(1, ...tot));
      const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || 'stacked bar chart' }, holder);
      const g = s('g', { class: 'grid' }, svg);
      for (let i = 0; i <= 4; i++) {
        const v = ymax * i / 4, y = m.t + ih - ih * v / ymax;
        if (i > 0) s('line', { x1: m.l, x2: W - m.r, y1: y, y2: y }, g);
        text(svg, m.l - 6, y + 3.5, String(Math.round(v)), { 'text-anchor': 'end', class: 'tabular' });
      }
      s('line', { x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih, class: 'axis' }, svg);
      const step = iw / data.length, bw = Math.max(3, Math.min(34, step * 0.7));
      const labelEvery = Math.ceil(46 / step);
      data.forEach((d, i) => {
        const x = m.l + step * i + (step - bw) / 2;
        let base = m.t + ih, first = true;
        const segs = series.filter(sr => d.values[sr.key] > 0);
        segs.forEach((sr, j) => {
          const hgt = ih * d.values[sr.key] / ymax;
          const gap = first ? 0 : 2;
          const top = j === segs.length - 1;
          const y = base - hgt;
          const hh = Math.max(0, hgt - gap);
          if (top) s('path', { d: barPath(x, y, bw, hh, 4), fill: sr.color, class: 'mark' }, svg);
          else s('rect', { x, y, width: bw, height: hh, fill: sr.color, class: 'mark' }, svg);
          base = y; first = false;
        });
        if (i % labelEvery === 0 || i === data.length - 1) {
          text(svg, m.l + step * i + step / 2, H - 6, d.label, { 'text-anchor': 'middle' });
        }
        const hit = s('rect', { x: m.l + step * i, y: m.t, width: step, height: ih, class: 'hit', tabindex: 0 }, svg);
        const rows = series.slice().reverse().map(sr => ({ color: sr.color, value: String(d.values[sr.key] || 0), label: sr.name }));
        rows.push({ value: String(tot[i]), label: 'Total' });
        const on = (e) => showTip(e, d.tip || d.label, rows);
        hit.addEventListener('pointerenter', on);
        hit.addEventListener('pointermove', moveTip);
        hit.addEventListener('pointerleave', hideTip);
        hit.addEventListener('focus', () => { const r = hit.getBoundingClientRect(); on({ clientX: r.right, clientY: r.top }); });
        hit.addEventListener('blur', hideTip);
        if (opts.onClick) hit.addEventListener('click', () => opts.onClick(d));
      });
    });
  }

  // ---------- diverging horizontal bars (e.g. currency strength) ----------
  // items: [{label, value, tip}]
  function diverging(container, items, opts = {}) {
    const holder = document.createElement('div'); holder.className = 'chart';
    container.replaceChildren(holder);
    if (!items.length) { holder.innerHTML = '<div class="empty">No data</div>'; return; }
    mount(holder, (W) => {
      const rowH = 24, m = { l: opts.labelW || 44, r: 34, t: 4, b: 4 };
      const H = m.t + m.b + rowH * items.length;
      const iw = W - m.l - m.r - (opts.labelW ? 30 : 0); // wide labels: leave room for a value left of a full-length bar
      const vmax = Math.max(1, ...items.map(d => Math.abs(d.value)));
      const x0 = m.l + (opts.labelW ? 30 : 0) + iw / 2, scale = (iw / 2) / vmax;
      const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || 'diverging bar chart' }, holder);
      s('line', { x1: x0, x2: x0, y1: m.t, y2: H - m.b, class: 'axis' }, svg);
      items.forEach((d, i) => {
        const y = m.t + i * rowH, bh = 12, by = y + (rowH - bh) / 2;
        const pos = d.value >= 0, len = Math.abs(d.value) * scale;
        const color = d.value === 0 ? 'var(--neutral)' : pos ? 'var(--bull)' : 'var(--bear)';
        text(svg, m.l - 8, y + rowH / 2 + 4, d.label, { 'text-anchor': 'end', class: 'lbl-ink' });
        if (len > 0) s('path', { d: hbarPath(x0, by, len, bh, 4, pos ? 1 : -1), fill: color, class: 'mark' }, svg);
        else s('rect', { x: x0 - 1, y: by, width: 2, height: bh, fill: color }, svg);
        const vx = pos ? x0 + len + 6 : x0 - len - 6;
        text(svg, vx, y + rowH / 2 + 4, (d.value > 0 ? '+' : d.value < 0 ? '−' : '') + Math.abs(d.value), { 'text-anchor': pos ? 'start' : 'end', class: 'lbl-ink tabular' });
        const hit = s('rect', { x: 0, y, width: W, height: rowH, class: 'hit', tabindex: 0 }, svg);
        const on = (e) => showTip(e, d.label, [{ color, value: (d.value > 0 ? '+' : '') + d.value, label: d.tip || '' }]);
        hit.addEventListener('pointerenter', on);
        hit.addEventListener('pointermove', moveTip);
        hit.addEventListener('pointerleave', hideTip);
        if (opts.onClick) hit.addEventListener('click', () => { hideTip(); opts.onClick(d); });
      });
    });
  }

  // ---------- multi-series line chart ----------
  // xs: [label], series: [{name, color, values:[n|null]}]
  function lines(container, xs, series, opts = {}) {
    const H = opts.height || 210;
    const holder = document.createElement('div'); holder.className = 'chart';
    const legend = document.createElement('div'); legend.className = 'legend';
    container.replaceChildren(holder, legend);
    let focus = null;
    const legendKeys = {};
    for (const sr of series) {
      const k = document.createElement('span'); k.className = 'k'; k.tabIndex = 0;
      const ln = document.createElement('i'); ln.className = 'ln'; ln.style.background = sr.color;
      k.append(ln, document.createTextNode(sr.name));
      k.title = 'Click to isolate';
      k.addEventListener('click', () => { focus = focus === sr.name ? null : sr.name; applyFocus(); });
      legend.appendChild(k); legendKeys[sr.name] = k;
    }
    let svgRef = null;
    function applyFocus() {
      for (const n in legendKeys) legendKeys[n].classList.toggle('off', !!focus && focus !== n);
      if (!svgRef) return;
      svgRef.classList.toggle('hl', !!focus);
      svgRef.querySelectorAll('[data-series]').forEach(el => el.classList.toggle('on', el.dataset.series === focus));
    }
    if (!xs.length) { holder.innerHTML = '<div class="empty">No history yet</div>'; return; }
    mount(holder, (W) => {
      const m = { l: 30, r: 40, t: 10, b: 22 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const all = series.flatMap(sr => sr.values.filter(v => v !== null && v !== undefined));
      let lo = Math.min(0, ...all), hi = Math.max(0, ...all);
      const pad = Math.max(1, Math.ceil((hi - lo) * 0.08)); lo -= pad; hi += pad;
      const X = i => m.l + (xs.length === 1 ? iw / 2 : iw * i / (xs.length - 1));
      const Y = v => m.t + ih - ih * (v - lo) / (hi - lo);
      const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || 'line chart' }, holder);
      svgRef = svg;
      const g = s('g', { class: 'grid' }, svg);
      const tickStep = niceMax((hi - lo) / 4) / 2 >= 1 ? Math.max(1, Math.round((hi - lo) / 4)) : 1;
      for (let v = Math.ceil(lo / tickStep) * tickStep; v <= hi; v += tickStep) {
        if (v !== 0) s('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, g);
        text(svg, m.l - 6, Y(v) + 3.5, (v > 0 ? '+' : '') + v, { 'text-anchor': 'end' });
      }
      s('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), class: 'axis' }, svg);
      const every = Math.ceil(56 / (iw / Math.max(1, xs.length - 1)));
      xs.forEach((x, i) => { if (i % every === 0 || i === xs.length - 1) text(svg, X(i), H - 6, x, { 'text-anchor': 'middle' }); });
      const ends = [];
      for (const sr of series) {
        let d = '', pen = false;
        sr.values.forEach((v, i) => {
          if (v === null || v === undefined) { pen = false; return; }
          d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1); pen = true;
        });
        s('path', { d, fill: 'none', stroke: sr.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', class: 'mark', 'data-series': sr.name }, svg);
        const li = sr.values.length - 1;
        if (sr.values[li] !== null && sr.values[li] !== undefined) ends.push({ sr, y: Y(sr.values[li]) });
      }
      // direct end labels, nudged apart so they never collide
      ends.sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 11) ends[i].y = ends[i - 1].y + 11;
      const over = ends.length ? ends[ends.length - 1].y - (m.t + ih) : 0;
      if (over > 0) ends.forEach(e => e.y -= over);
      for (const e of ends) {
        const t = text(svg, W - m.r + 6, e.y + 3.5, e.sr.name, { class: 'lbl-ink mark', 'data-series': e.sr.name });
        t.style.fill = e.sr.color;
      }
      const xh = s('line', { y1: m.t, y2: m.t + ih, class: 'xhair', visibility: 'hidden' }, svg);
      const dots = series.map(sr => s('circle', { r: 4, fill: sr.color, stroke: 'var(--surface)', 'stroke-width': 2, visibility: 'hidden' }, svg));
      const hit = s('rect', { x: m.l, y: m.t, width: iw, height: ih, class: 'hit' }, svg);
      hit.style.cursor = 'crosshair';
      hit.addEventListener('pointermove', (e) => {
        const r = svg.getBoundingClientRect();
        const px = (e.clientX - r.left) * (W / r.width);
        const i = Math.max(0, Math.min(xs.length - 1, Math.round((px - m.l) / (iw / Math.max(1, xs.length - 1)))));
        xh.setAttribute('x1', X(i)); xh.setAttribute('x2', X(i)); xh.setAttribute('visibility', 'visible');
        series.forEach((sr, k) => {
          const v = sr.values[i];
          if (v === null || v === undefined) dots[k].setAttribute('visibility', 'hidden');
          else { dots[k].setAttribute('cx', X(i)); dots[k].setAttribute('cy', Y(v)); dots[k].setAttribute('visibility', 'visible'); }
        });
        const rows = series.map(sr => ({ sr, v: sr.values[i] })).filter(o => o.v !== null && o.v !== undefined)
          .sort((a, b) => b.v - a.v).map(o => ({ color: o.sr.color, value: (o.v > 0 ? '+' : '') + o.v, label: o.sr.name }));
        showTip(e, opts.tipLabel ? opts.tipLabel(i) : xs[i], rows);
      });
      hit.addEventListener('pointerleave', () => { hideTip(); xh.setAttribute('visibility', 'hidden'); dots.forEach(d => d.setAttribute('visibility', 'hidden')); });
      applyFocus();
    });
  }

  return { stacked, diverging, lines, showTip, moveTip, hideTip };
})();

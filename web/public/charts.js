// Lightweight Charts helpers — theme-aware, swap-safe.
window.__lw = window.__lw || [];

window.lwcIsDark = () =>
  document.documentElement.dataset.theme === 'dark' ||
  (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);

window.lwcTheme = () => (window.lwcIsDark()
  ? { text: '#9ca3af', grid: '#333a47', cross: '#6b7280' }
  : { text: '#6b7280', grid: '#e5e7eb', cross: '#9ca3af' });

// Create a chart that tracks theme and cleans up after content swaps.
window.mkChart = (el, opts = {}) => {
  const t = window.lwcTheme();
  const chart = LightweightCharts.createChart(el, Object.assign({
    autoSize: true,
    height: 280,
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: t.text, attributionLogo: false },
    grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
    crosshair: {
      vertLine: { color: t.cross, labelBackgroundColor: '#2563eb' },
      horzLine: { color: t.cross, labelBackgroundColor: '#2563eb' },
    },
    rightPriceScale: { borderColor: t.grid },
    timeScale: { borderColor: t.grid, rightOffset: 2 },
    localization: { locale: 'he-IL' },
  }, opts));
  window.__lw.push({ c: chart, el });
  return chart;
};

window.lwcRetheme = () => {
  const t = window.lwcTheme();
  window.__lw = window.__lw.filter(({ c, el }) => {
    if (!el.isConnected) { try { c.remove(); } catch (e) {} return false; }
    c.applyOptions({
      layout: { textColor: t.text },
      grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
      crosshair: { vertLine: { color: t.cross }, horzLine: { color: t.cross } },
      rightPriceScale: { borderColor: t.grid },
      timeScale: { borderColor: t.grid },
    });
    return true;
  });
};

// Value chart: ₪ raw / ₪ adjusted (ex deposits) / % modes + range selector.
window.mkValueChart = (el, data, legend, flows = {}) => {
  const chart = window.mkChart(el);
  const ilsFmt = v => '₪' + v.toLocaleString('he-IL', { maximumFractionDigits: 0 });
  const pctFmt = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  const area = chart.addAreaSeries({
    lineColor: '#2563eb', lineWidth: 2,
    topColor: 'rgba(37,99,235,.28)', bottomColor: 'rgba(37,99,235,0)',
    priceFormat: { type: 'custom', formatter: ilsFmt, minMove: 0.01 },
  });
  const base = chart.addBaselineSeries({
    baseValue: { type: 'price', price: 0 },
    topLineColor: '#16a34a', topFillColor1: 'rgba(22,163,74,.3)', topFillColor2: 'rgba(22,163,74,.05)',
    bottomLineColor: '#dc2626', bottomFillColor1: 'rgba(220,38,38,.05)', bottomFillColor2: 'rgba(220,38,38,.3)',
    lineWidth: 2, visible: false,
    priceFormat: { type: 'custom', formatter: pctFmt, minMove: 0.01 },
  });

  // adjusted = value minus cumulative external flow (deposits - withdrawals)
  const fKeys = Object.keys(flows).sort();
  const cumAt = t => { let c = 0; for (const k of fKeys) { if (k <= t) c = flows[k]; else break; } return c; };
  const adj = data.map(d => ({ time: d.time, value: d.value - cumAt(d.time) }));

  let mode = 'adj', range = 'all';
  const RANGES = [['w', 'שבוע', 7], ['m', 'חודש', 30], ['q', 'רבעון', 92], ['y', 'שנה', 365], ['all', 'הכל', 0]];
  const MODES = [['ils', '₪'], ['adj', 'מתואם'], ['pct', '%']];
  const src = () => mode === 'pct' ? adj : (mode === 'adj' ? adj : data);
  const filtered = () => {
    const days = (RANGES.find(r => r[0] === range) || [])[2];
    if (!days || !data.length) return src();
    const end = Date.parse(data[data.length - 1].time) / 1000;
    return src().filter(d => Date.parse(d.time) / 1000 >= end - days * 86400);
  };
  const fmt = () => mode === 'pct' ? pctFmt : ilsFmt;

  const apply = () => {
    const vis = filtered();
    if (mode === 'pct') {
      const b0 = vis.length ? vis[0].value : 1;
      base.setData(vis.map(d => ({ time: d.time, value: b0 ? (d.value / b0 - 1) * 100 : 0 })));
      base.applyOptions({ visible: true });
      area.applyOptions({ visible: false });
    } else {
      area.setData(vis);
      area.applyOptions({ visible: true });
      base.applyOptions({ visible: false });
    }
    chart.timeScale().fitContent();
    showLast();
  };

  const btns = document.createElement('span');
  btns.style.cssText = 'float:left;direction:ltr;display:inline-flex;gap:.7rem';
  const mkBtns = (items, cur, set) => {
    const g = document.createElement('span');
    items.forEach(([id, label]) => {
      const b = document.createElement('button');
      b.className = 'link';
      b.textContent = label;
      b.style.fontWeight = id === cur() ? '700' : '400';
      b.onclick = () => { set(id); g.querySelectorAll('button').forEach(x => x.style.fontWeight = x === b ? '700' : '400'); };
      g.appendChild(b);
    });
    return g;
  };
  btns.appendChild(mkBtns(MODES, () => mode, m => { mode = m; apply(); }));
  btns.appendChild(mkBtns(RANGES.map(r => [r[0], r[1]]), () => range, r => { range = r; apply(); }));
  legend && legend.parentElement && legend.parentElement.appendChild(btns);

  const showLast = () => {
    if (!legend) return;
    const vis = filtered();
    const l = vis[vis.length - 1];
    if (!l) { legend.textContent = ''; return; }
    legend.textContent = `${l.time} · ${fmt()(mode === 'pct' && vis[0].value ? (l.value / vis[0].value - 1) * 100 : l.value)}`;
  };
  chart.subscribeCrosshairMove(p => {
    if (!legend) return;
    const s = mode === 'pct' ? base : area;
    const v = p.seriesData && p.seriesData.get(s);
    if (v === undefined || p.time === undefined) { showLast(); return; }
    const val = v.value !== undefined ? v.value : v;
    const t = typeof p.time === 'string' ? p.time : new Date(p.time * 1000).toLocaleDateString('he-IL');
    legend.textContent = `${t} · ${fmt()(val)}`;
  });
  apply();
  return { chart, area, base };
};

// Area series for a value-over-time chart with a hover legend.
window.mkAreaChart = (el, data, legend, priceFmt) => {
  const chart = window.mkChart(el);
  const fmt = priceFmt || (v => '₪' + v.toLocaleString('he-IL', { maximumFractionDigits: 0 }));
  const series = chart.addAreaSeries({
    lineColor: '#2563eb', lineWidth: 2,
    topColor: 'rgba(37,99,235,.28)', bottomColor: 'rgba(37,99,235,0)',
    priceFormat: { type: 'custom', formatter: fmt, minMove: 0.01 },
  });
  series.setData(data);
  chart.timeScale().fitContent();
  if (legend) {
    const last = data[data.length - 1];
    const set = (t, v) => { legend.textContent = `${t} · ${fmt(v)}`; };
    if (last) set(last.time, last.value);
    chart.subscribeCrosshairMove(p => {
      const v = p.seriesData && p.seriesData.get(series);
      if (v !== undefined && p.time !== undefined) set(typeof p.time === 'string' ? p.time : new Date(p.time * 1000).toLocaleDateString('he-IL'), v.value !== undefined ? v.value : v);
    });
  }
  return { chart, series };
};

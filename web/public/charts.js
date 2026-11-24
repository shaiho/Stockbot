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

// Value chart with ₪/% mode toggle + hover legend.
window.mkValueChart = (el, data, legend) => {
  const chart = window.mkChart(el);
  const ilsFmt = v => '₪' + v.toLocaleString('he-IL', { maximumFractionDigits: 0 });
  const pctFmt = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  const area = chart.addAreaSeries({
    lineColor: '#2563eb', lineWidth: 2,
    topColor: 'rgba(37,99,235,.28)', bottomColor: 'rgba(37,99,235,0)',
    priceFormat: { type: 'custom', formatter: ilsFmt, minMove: 0.01 },
  });
  const d0 = data.length ? data[0].value : 1;
  const base = chart.addBaselineSeries({
    baseValue: { type: 'price', price: 0 },
    topLineColor: '#16a34a', topFillColor1: 'rgba(22,163,74,.3)', topFillColor2: 'rgba(22,163,74,.05)',
    bottomLineColor: '#dc2626', bottomFillColor1: 'rgba(220,38,38,.05)', bottomFillColor2: 'rgba(220,38,38,.3)',
    lineWidth: 2, visible: false,
    priceFormat: { type: 'custom', formatter: pctFmt, minMove: 0.01 },
  });
  area.setData(data);
  base.setData(data.map(d => ({ time: d.time, value: d0 ? (d.value / d0 - 1) * 100 : 0 })));
  chart.timeScale().fitContent();

  const wrap = el.parentElement;
  const btns = document.createElement('span');
  btns.style.cssText = 'float:left;direction:ltr';
  const bI = document.createElement('button'), bP = document.createElement('button');
  bI.className = bP.className = 'link';
  bI.textContent = '₪'; bP.textContent = '%';
  let mode = 'ils';
  const fmt = () => mode === 'ils' ? ilsFmt : pctFmt;
  const setMode = m => {
    mode = m;
    area.applyOptions({ visible: m === 'ils' });
    base.applyOptions({ visible: m === 'pct' });
    bI.style.fontWeight = m === 'ils' ? '700' : '400';
    bP.style.fontWeight = m === 'pct' ? '700' : '400';
    showLast();
  };
  bI.onclick = () => setMode('ils');
  bP.onclick = () => setMode('pct');
  btns.append(bI, bP);
  legend && legend.parentElement && legend.parentElement.appendChild(btns);

  const showLast = () => {
    if (!legend || !data.length) return;
    const l = data[data.length - 1];
    legend.textContent = `${l.time} · ${mode === 'ils' ? ilsFmt(l.value) : pctFmt(d0 ? (l.value / d0 - 1) * 100 : 0)}`;
  };
  showLast();
  chart.subscribeCrosshairMove(p => {
    if (!legend) return;
    const s = mode === 'ils' ? area : base;
    const v = p.seriesData && p.seriesData.get(s);
    if (v === undefined || p.time === undefined) { showLast(); return; }
    const val = v.value !== undefined ? v.value : v;
    const t = typeof p.time === 'string' ? p.time : new Date(p.time * 1000).toLocaleDateString('he-IL');
    legend.textContent = `${t} · ${fmt()(val)}`;
  });
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

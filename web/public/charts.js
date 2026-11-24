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

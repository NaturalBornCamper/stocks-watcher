/* =====================================================================
   Rank-over-time line chart on the stock details page.
   One line per SA category the stock has ever been ranked in. The data
   comes from the view via a json_script block (#chart-data); Chart.js
   itself is vendored at static/js/vendor/chart.umd.min.js.

   The Y axis is REVERSED (rank 1 at the top) because a lower rank is
   better -- a line going up means the stock is climbing the top-100.
   Months where the stock dropped out of a category show as gaps, not as
   a line connecting across the hole (spanGaps: false).

   Zoom / pan (chartjs-plugin-zoom + hammer.js, also vendored):
   - Shift + wheel  -> zoom the time axis only
   - Alt + wheel    -> zoom the rank axis only
   - plain wheel    -> ignored, the page scrolls normally
   - drag           -> pan around when zoomed in
   - double-click   -> reset to the full view
   ===================================================================== */
(() => {
    const dataEl = document.getElementById('chart-data');
    const canvas = document.getElementById('rank-chart-canvas');
    if (!dataEl || !canvas || typeof Chart === 'undefined') return;

    // The script-tag build of the zoom plugin exposes a ChartZoom global;
    // registering is a no-op if the bundle already registered itself.
    if (typeof ChartZoom !== 'undefined') Chart.register(ChartZoom);

    const chartData = JSON.parse(dataEl.textContent);
    if (!chartData.series.length) return;

    // Match the dark theme from style.css.
    Chart.defaults.color = '#b0b0b0';
    Chart.defaults.borderColor = '#333';

    // Distinct line colours that read well on the dark background.
    const COLORS = ['#66b3ff', '#ffa94d', '#69db7c', '#ff6b6b', '#da77f2', '#ffd43b', '#4dd4c0', '#f783ac'];

    const datasets = chartData.series.map((series, i) => ({
        label: series.label,
        data: series.data,
        borderColor: COLORS[i % COLORS.length],
        backgroundColor: COLORS[i % COLORS.length],
        borderWidth: 2,
        pointRadius: 3,       // keep isolated single-month points visible
        spanGaps: false,
    }));

    const rankChart = new Chart(canvas, {
        type: 'line',
        data: { labels: chartData.labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,  // fill the .rank-chart wrapper height
            interaction: { mode: 'index', intersect: false },  // hover a month -> tooltip lists every category
            scales: {
                y: {
                    reverse: true,  // rank 1 (best) at the top
                    min: 1,
                    max: 100,
                    title: { display: true, text: 'Rank (1 = best)' },
                    grid: { color: '#2a2a2a' },
                },
                x: {
                    grid: { color: '#2a2a2a' },
                },
            },
            plugins: {
                legend: { labels: { usePointStyle: true } },  // click a category to hide/show its line
                zoom: {
                    zoom: {
                        wheel: { enabled: true },
                        mode: 'xy',  // real axis is picked per wheel event in onZoomStart
                        onZoomStart: ({ chart, event }) => {
                            // Shift+wheel zooms the time axis, Alt+wheel the rank axis.
                            // Returning false for a plain wheel rejects the zoom BEFORE
                            // preventDefault, so the page scrolls normally.
                            if (event.shiftKey) { chart.options.plugins.zoom.zoom.mode = 'x'; return true; }
                            if (event.altKey) { chart.options.plugins.zoom.zoom.mode = 'y'; return true; }
                            return false;
                        },
                    },
                    pan: { enabled: true, mode: 'xy' },  // drag to pan (needs hammer.js); inert until zoomed in
                    // Never zoom/pan past the full data range.
                    limits: {
                        x: { min: 'original', max: 'original' },
                        y: { min: 'original', max: 'original' },
                    },
                },
            },
        },
    });

    // The zoom plugin has no built-in reset gesture; double-click restores the full view.
    canvas.addEventListener('dblclick', () => rankChart.resetZoom());
})();

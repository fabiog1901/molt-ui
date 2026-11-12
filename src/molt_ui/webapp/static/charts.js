document.addEventListener('alpine:init', () => {
  Alpine.data('moltCharts', () => {
    // Canvas instances stay outside Alpine's reactive proxy.
    const plots = new Map();
    let timer = null, observer = null, generation = 0;
    let cachedFrames = null, cachedFilters = '', seriesCache = new Map();
    const colors = ['#a6d8bb', '#8cc9ff', '#d0b4ff', '#efd58a', '#ffb4ac', '#6ee7dc', '#f5a9d5', '#abb9ff'];
    return {
      contextKey: '', active: false, live: false, available: false,
      panels: [], frames: [], state: {}, message: '', loading: false,
      schema: '', table: '', shard: '', detailsOpen: false,
      init() {
        if (globalThis.ResizeObserver) {
          observer = new ResizeObserver(() => { this.renderCharts(); this.resizeCharts(); });
          this.$nextTick(() => observer.observe(this.$refs.chartGrid));
        }
      },
      destroy() { generation++; clearTimeout(timer); observer?.disconnect(); this.destroyPlots(); },
      destroyPlots() { for (const {plot} of plots.values()) plot.destroy(); plots.clear(); },
      setContext(kind, id, active, live) {
        const key = id ? `${kind}/${encodeURIComponent(id)}` : '';
        const changed = key !== this.contextKey, opening = active && !this.active;
        const finished = this.live && !live;
        if (changed) {
          generation++; clearTimeout(timer); this.destroyPlots();
          this.contextKey = key; this.panels = []; this.frames = []; this.state = {};
          this.schema = ''; this.table = ''; this.shard = ''; this.message = '';
          this.available = false; this.loading = false;
        }
        this.active = active; this.live = live;
        if (!active) { clearTimeout(timer); this.destroyPlots(); return; }
        if (key && (changed || opening || finished)) this.refresh();
      },
      async refresh() {
        clearTimeout(timer);
        const key = this.contextKey, version = ++generation;
        if (!key || !this.active) return;
        this.loading = true;
        try {
          const after = this.frames.at(-1)?.timestamp || 0;
          const response = await fetch(`/api/${key}/metrics?after=${after}`);
          const data = await response.json();
          if (version !== generation || key !== this.contextKey) return;
          if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load metrics.');
          this.available = data.available; this.panels = data.panels; this.state = data.state;
          this.frames = [...this.frames, ...data.frames.filter(frame => frame.timestamp > after)].slice(-1800);
          this.message = '';
          this.$nextTick(() => this.renderCharts());
        } catch (error) {
          if (version === generation && key === this.contextKey) this.message = error.message;
        } finally {
          if (version === generation && key === this.contextKey) {
            this.loading = false;
            if (this.active && this.live) timer = setTimeout(() => this.refresh(), 2000);
          }
        }
      },
      get statPanels() { return this.panels.filter(panel => panel.type === 'stat'); },
      get chartPanels() { return this.panels.filter(panel => panel.type === 'timeseries'); },
      get lastUpdated() { return this.frames.at(-1)?.timestamp; },
      get hasSamples() { return this.frames.some(frame => Object.values(frame.values).some(values => values.length)); },
      get statusText() {
        if (!this.available) return 'Charts are available for fetch and verify jobs run with metrics collection. Imported logs do not contain Prometheus samples.';
        if (this.state.error) return this.state.error + (this.live ? ' Retrying…' : ' Showing any saved samples.');
        if (!this.hasSamples) return this.live ? 'Waiting for Molt to expose metrics…' : 'No metrics were captured for this job.';
        return this.live ? 'Live · updates every 2 seconds' : 'Saved metrics';
      },
      optionsFor(name) {
        const values = new Set();
        for (const frame of this.frames) for (const series of Object.values(frame.values))
          for (const item of series) {
            if (name === 'table' && this.schema && item.labels.schema !== this.schema) continue;
            if (item.labels[name] !== undefined) values.add(item.labels[name]);
          }
        return [...values].sort();
      },
      matches(labels) {
        return (!this.schema || labels.schema === undefined || labels.schema === this.schema)
          && (!this.table || labels.table === undefined || labels.table === this.table)
          && (!this.shard || labels.shard === undefined || labels.shard === this.shard);
      },
      label(labels) {
        const name = [labels.schema, labels.table].filter(Boolean).join('.');
        const details = Object.entries(labels).filter(([key]) => !['schema', 'table'].includes(key))
          .map(([key, value]) => key === 'quantile' ? value : `${key}=${value}`);
        return [name, ...details].filter(Boolean).join(' · ') || 'Overall';
      },
      format(value, unit = '') {
        if (value === null || value === undefined || !Number.isFinite(value)) return '—';
        return new Intl.NumberFormat(undefined, {maximumFractionDigits: 2, notation: Math.abs(value) >= 1e6 ? 'compact' : 'standard'}).format(value) + (unit ? ` ${unit}` : '');
      },
      latestValues(panel) {
        // Run metadata stays independent of chart filters and transient scrape gaps.
        for (let index = this.frames.length - 1; index >= 0; index--) {
          const values = this.frames[index].values[panel.id];
          if (values?.length) return values;
        }
        return [];
      },
      get runTablePanels() {
        if (!this.available) return [];
        const names = {
          molt_fetch_table_overall_duration_ms: 'Total time',
          molt_fetch_table_export_duration_ms: 'Export',
          molt_fetch_table_import_duration_ms: 'Import',
          molt_fetch_num_data_errors: 'Data errors',
        };
        return this.statPanels.filter(panel => names[panel.metric])
          .sort((a, b) => Object.keys(names).indexOf(a.metric) - Object.keys(names).indexOf(b.metric))
          .map(panel => ({...panel, label: names[panel.metric]}));
      },
      get runOverview() {
        if (!this.available) return [];
        const names = {'10': 'Duration', '20': 'Duration', '1': 'Tables', '7': 'Task errors',
          '16': 'Tables verified', '17': 'Missing tables', '18': 'Extra tables'};
        const order = ['10', '20', '1', '16', '7', '17', '18'];
        return this.statPanels.filter(panel => names[panel.id])
          .sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id))
          .flatMap(panel => {
            const values = this.latestValues(panel);
            return (values.length ? values : [{value: null, labels: {}}]).map(item => ({
              key: panel.id + JSON.stringify(item.labels),
              label: names[panel.id] + (values.length > 1 ? ` · ${this.label(item.labels)}` : ''),
              value: item.value, unit: panel.unit,
              attention: ['7', '17', '18'].includes(panel.id) && item.value > 0,
            }));
          });
      },
      get runTableRows() {
        const rows = new Map();
        for (const panel of this.runTablePanels) for (const item of this.latestValues(panel)) {
          const key = JSON.stringify(item.labels);
          if (!rows.has(key)) rows.set(key, {key, name: this.label(item.labels), values: {}});
          rows.get(key).values[panel.id] = item.value;
        }
        return [...rows.values()].sort((a, b) => a.name.localeCompare(b.name));
      },
      formatRunValue(value, unit = '') {
        if (value === null || value === undefined || !Number.isFinite(value)) return '—';
        const number = new Intl.NumberFormat(undefined, {maximumFractionDigits: 2});
        if (!['ms', 's'].includes(unit)) return number.format(value);
        const seconds = unit === 'ms' ? value / 1000 : value;
        if (seconds > 0 && seconds < 1) return number.format(seconds * 1000) + ' ms';
        if (seconds < 60) return number.format(seconds) + ' s';
        const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60);
        const remainder = Math.floor(seconds % 60);
        return [hours ? `${hours}h` : '', minutes ? `${minutes}m` : '', remainder ? `${remainder}s` : '']
          .filter(Boolean).join(' ');
      },
      seriesFor(panel) {
        const filters = JSON.stringify([this.schema, this.table, this.shard]);
        if (cachedFrames !== this.frames || cachedFilters !== filters) {
          cachedFrames = this.frames; cachedFilters = filters; seriesCache.clear();
        }
        if (seriesCache.has(panel.id)) return seriesCache.get(panel.id);
        const series = new Map();
        for (const frame of this.frames) for (const item of frame.values[panel.id] || []) {
          if (!this.matches(item.labels)) continue;
          const key = JSON.stringify(item.labels);
          if (!series.has(key)) series.set(key, {key, label: this.label(item.labels), values: new Map()});
          series.get(key).values.set(frame.timestamp, item.value);
        }
        const result = [...series.values()].sort((a, b) => a.label.localeCompare(b.label));
        seriesCache.set(panel.id, result);
        return result;
      },
      filterChanged() { this.$nextTick(() => this.renderCharts()); },
      resizeCharts() {
        if (!this.active) return;
        for (const {plot, node} of plots.values()) if (node.clientWidth > 0)
          plot.setSize({width: node.clientWidth, height: 230});
      },
      renderCharts() {
        if (!this.active || !this.$refs.chartGrid) return;
        if (!globalThis.uPlot) { this.message = 'The chart library could not be loaded. Reload to try again.'; return; }
        for (const panel of this.chartPanels) {
          const node = this.$refs.chartGrid.querySelector(`[data-chart-id="${panel.id}"]`);
          if (!node || node.clientWidth === 0) continue;
          const series = this.seriesFor(panel).slice(0, 24);
          const signature = JSON.stringify(series.map(item => item.key));
          const times = this.frames.map(frame => frame.timestamp);
          const data = [times, ...series.map(item => times.map(t => item.values.get(t) ?? null))];
          let existing = plots.get(panel.id);
          if (existing && existing.signature !== signature) {
            existing.plot.destroy(); plots.delete(panel.id); existing = null;
          }
          if (!series.length) continue;
          if (existing) { existing.plot.setData(data); continue; }
          const format = value => this.format(value, panel.unit);
          const plot = new uPlot({width: node.clientWidth, height: 230,
            scales: {x: {time: true}, y: {range: (u, min, max) => [Math.min(0, min), Math.max(1, max * 1.1)]}},
            axes: [{stroke: '#a8b0c0', grid: {stroke: '#343a4644'}},
              {stroke: '#a8b0c0', size: 60, grid: {stroke: '#343a4688'}, values: (u, ticks) => ticks.map(value => this.format(value))}],
            series: [{}, ...series.map((item, index) => ({label: item.label,
              stroke: colors[index % colors.length], width: 1.5, spanGaps: false,
              value: (u, value) => format(value)}))],
          }, data, node);
          plots.set(panel.id, {plot, node, signature});
        }
      },
    };
  });
});

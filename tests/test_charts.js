const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createCharts(responses = []) {
  let factory, scheduled = 0, resizeCallback;
  const plots = [], calls = [];
  const node = {clientWidth: 500};
  class Plot {
    constructor(options, data) { this.options = options; this.data = data; plots.push(this); }
    setData(data) { this.data = data; }
    setSize(size) { this.size = size; }
    destroy() { this.destroyed = true; }
  }
  const context = {
    document: {addEventListener: (_, callback) => callback()},
    Alpine: {data: (_, callback) => { factory = callback; }},
    setTimeout: () => ++scheduled, clearTimeout() {}, uPlot: Plot,
    ResizeObserver: class {
      constructor(callback) { resizeCallback = callback; }
      observe() {}
      disconnect() {}
    },
    fetch: async path => {
      calls.push(path);
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return {ok: true, json: async () => typeof next === 'function' ? next() : next};
    },
  };
  vm.runInNewContext(fs.readFileSync('src/molt_ui/webapp/static/charts.js', 'utf8'), context);
  const app = factory();
  app.$nextTick = callback => callback();
  app.$refs = {chartGrid: {querySelector: () => node}};
  return {app, plots, calls, node, resize: () => resizeCallback(), scheduled: () => scheduled};
}

const panel = {id: '13', title: 'Rows exported', type: 'timeseries', unit: ''};
const item = (table, value, extra = {}) => ({labels: {schema: 'public', table, ...extra}, value});
const frame = (timestamp, items) => ({timestamp, values: {'13': items}});
const reply = frames => ({available: true, state: {status: 'collecting'}, panels: [panel], frames});

test('charts collect incrementally, preserve gaps, and update an existing uPlot', async () => {
  const {app, plots, calls, scheduled} = createCharts([
    reply([frame(10, [item('actor', 10)]), frame(12, [])]),
    reply([frame(14, [item('actor', 30)])]),
  ]);
  app.contextKey = 'jobs/run1'; app.active = true; app.live = true;
  await app.refresh();
  assert.equal(calls[0], '/api/jobs/run1/metrics?after=0');
  assert.deepEqual(Array.from(plots[0].data[1]), [10, null]);
  await app.refresh();
  assert.equal(calls[1], '/api/jobs/run1/metrics?after=12');
  assert.equal(plots.length, 1);
  assert.deepEqual(Array.from(plots[0].data[1]), [10, null, 30]);
  assert.equal(scheduled(), 2);
  app.destroy();
  assert.equal(plots[0].destroyed, true);
});

test('filters use metric labels and rebuild chart series without losing samples', () => {
  const {app, plots} = createCharts();
  app.active = true; app.panels = [panel];
  app.frames = [frame(10, [item('actor', 10, {shard: '0'}), item('film', 20, {shard: '1'})])];
  app.renderCharts();
  assert.equal(plots[0].data.length, 3);
  app.table = 'actor'; app.filterChanged();
  assert.equal(plots[0].destroyed, true);
  assert.equal(plots[1].data.length, 2);
  assert.equal(app.frames[0].values['13'].length, 2);
  assert.deepEqual(Array.from(app.optionsFor('table')), ['actor', 'film']);
  app.shard = '1'; app.filterChanged();
  assert.equal(app.seriesFor(panel).length, 0);
  assert.equal(plots[1].destroyed, true);
});

test('run metadata preserves the last measured values independently of chart filters', () => {
  const {app} = createCharts();
  app.frames = [frame(10, [item('actor', 10), item('film', 20)]), frame(12, [])];
  app.table = 'actor';
  const values = app.latestValues(panel);
  assert.equal(values.length, 2);
  assert.equal(values[1].labels.table, 'film');
  assert.equal(values[1].value, 20);
});

test('run summary groups totals and aligns table measurements without filling missing values', () => {
  const {app} = createCharts();
  app.available = true;
  app.panels = JSON.parse(fs.readFileSync('src/molt_ui/webapp/static/metrics-dashboard.json', 'utf8')).filter(panel => panel.command === 'fetch');
  app.frames = [{timestamp: 10, values: {
    '10': [{labels: {}, value: 125}], '1': [{labels: {}, value: 2}], '7': [{labels: {}, value: 1}],
    '4': [item('actor', 1000), item('film', 2000)],
    '9': [item('actor', 250)], '8': [item('film', 3)],
  }}];
  app.table = 'actor';
  assert.deepEqual(Array.from(app.runOverview, item => item.label), ['Duration', 'Tables', 'Task errors']);
  assert.equal(app.runOverview[2].attention, true);
  assert.equal(app.runTableRows.length, 2);
  assert.equal(app.runTableRows[1].name, 'public.film');
  assert.equal(app.runTableRows[0].values['9'], 250);
  assert.equal(app.runTableRows[1].values['9'], undefined);
  assert.equal(app.formatRunValue(app.runTableRows[1].values['9'], 'ms'), '—');
  assert.equal(app.formatRunValue(125, 's'), '2m 5s');
  assert.equal(app.formatRunValue(250, 'ms'), '250 ms');
  assert.equal(app.formatRunValue(3600, 's'), '1h');
  app.available = false;
  assert.equal(app.runOverview.length, 0);
  assert.equal(app.runTableRows.length, 0);
});

test('charts render after a hidden history view becomes visible', () => {
  const {app, plots, node, resize} = createCharts();
  app.init(); app.active = true; app.panels = [panel];
  app.frames = [frame(10, [item('actor', 10)])];
  node.clientWidth = 0;
  app.renderCharts();
  assert.equal(plots.length, 0);
  node.clientWidth = 320;
  resize();
  assert.equal(plots.length, 1);
  assert.equal(plots[0].size.width, 320);
});

test('switching jobs discards late metrics responses from the old job', async () => {
  let resolve, notifyReady;
  const ready = new Promise(done => { notifyReady = done; });
  const {app} = createCharts([() => new Promise(done => { resolve = done; notifyReady(); })]);
  app.contextKey = 'jobs/old'; app.active = true;
  const pending = app.refresh();
  await ready;
  app.setContext('history', 'new', false, false);
  resolve(reply([frame(10, [item('old-table', 10)])]));
  await pending;
  assert.equal(app.contextKey, 'history/new');
  assert.equal(app.frames.length, 0);
  assert.equal(app.panels.length, 0);
});

test('a completed history view does not poll and retains captured data on network failure', async () => {
  const {app, scheduled} = createCharts([reply([frame(10, [item('actor', 10)])]), new Error('offline')]);
  app.contextKey = 'history/record1'; app.active = true;
  await app.refresh();
  assert.equal(scheduled(), 0);
  assert.equal(app.statusText, 'Saved metrics');
  await app.refresh();
  assert.equal(app.message, 'offline');
  assert.equal(app.frames.length, 1);
});

test('large inventories limit rendered series and sample retention', async () => {
  const frames = Array.from({length: 2000}, (_, index) => frame(index + 1,
    Array.from({length: 30}, (_, table) => item(`table${table}`, table + index))));
  const {app, plots} = createCharts([reply(frames)]);
  app.contextKey = 'history/record1'; app.active = true;
  await app.refresh();
  assert.equal(app.frames.length, 1800);
  assert.equal(app.seriesFor(panel).length, 30);
  assert.equal(plots[0].data.length, 25);
});

test('unsupported jobs explain missing metrics without fabricating zero values', async () => {
  const {app} = createCharts([{available: false, state: {status: 'unavailable'}, panels: [], frames: []}]);
  app.contextKey = 'history/imported'; app.active = true;
  await app.refresh();
  assert.match(app.statusText, /Imported logs/);
  assert.equal(app.hasSamples, false);
  assert.equal(app.format(null), '—');
});

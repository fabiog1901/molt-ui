const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createApp(responses) {
  let factory;
  const calls = [];
  let scheduled = 0;
  const context = {
    document: { addEventListener: (_, callback) => callback() },
    Alpine: { data: (_, callback) => { factory = callback; } },
    setTimeout: () => { scheduled++; return scheduled; }, clearTimeout: () => {},
    fetch: async (path, options) => {
      calls.push({ path, options });
      const response = responses.shift();
      if (response instanceof Error) throw response;
      if (!response) throw new Error('Unexpected request');
      return { ok: (response.status || 200) < 400, status: response.status || 200, json: async () => response.body, blob: async () => response.blobBody };
    },
  };
  vm.runInNewContext(fs.readFileSync('src/molt_ui/web/static/app.js', 'utf8'), context);
  return { app: factory(), calls, scheduled: () => scheduled };
}

const snapshot = (events = [], status = 'running') => ({ id: 'run1', command: 'fetch', status, cursor: events.at(-1)?.sequence || 0, returncode: status === 'running' ? null : 0, events, truncated: false });
const catalog = [{ id: 'fetch', options: [{ name: 'source', kind: 'string' }, { name: 'direct-copy', kind: 'bool' }] }];

test('starts a typed command, polls incremental logs, and handles completion', async () => {
  const first = { sequence: 1, stream: 'stdout', text: 'first', data: null };
  const second = { sequence: 2, stream: 'stderr', text: 'second', data: { level: 'warn', message: 'warning', table: 'example' } };
  const { app, calls } = createApp([{ body: snapshot([first]) }, { body: snapshot([second], 'succeeded') }]);
  app.commands = catalog;
  app.values = { source: 'connection', 'direct-copy': 'false' };
  await app.start();
  assert.deepEqual(JSON.parse(calls[0].options.body), { command: 'fetch', options: { source: 'connection', 'direct-copy': false }, help_only: false });
  await app.poll();
  assert.equal(calls[1].path, '/api/jobs/run1?after=1');
  assert.equal(app.events.length, 2);
  assert.equal(app.running, false);
  assert.match(app.formatEvent(second), /\[warn\] warning.*example/);
});

test('restores the running job after refresh', async () => {
  const { app, scheduled } = createApp([{ body: catalog }, { body: snapshot() }]);
  await app.init();
  assert.equal(app.job.id, 'run1');
  assert.equal(app.running, true);
  assert.equal(scheduled(), 1);
});

test('retries network failure but stops polling when the job is gone', async () => {
  const { app, scheduled } = createApp([new Error('Offline'), { status: 404, body: { detail: 'Run not found' } }]);
  app.job = snapshot();
  await app.poll();
  assert.match(app.error, /Retrying/);
  assert.equal(scheduled(), 1);
  await app.poll();
  assert.equal(app.job.status, 'unavailable');
  assert.equal(scheduled(), 1);
});

test('validation failure leaves the form usable and bounded output reports loss', async () => {
  const { app } = createApp([{ status: 422, body: { detail: 'Provide a source' } }]);
  app.commands = catalog;
  await app.start();
  assert.equal(app.error, 'Provide a source');
  assert.equal(app.busy, false);
  assert.equal(app.job, null);
  app.applySnapshot(snapshot(Array.from({ length: 2100 }, (_, index) => ({ sequence: index + 1 }))));
  assert.equal(app.events.length, 2000);
  assert.equal(app.truncated, true);
});

test('renders authoritative full-run aggregates even when the console lost events', () => {
  const { app } = createApp([]);
  const state = snapshot([]);
  state.truncated = true;
  state.aggregation = {
    totals: { tables: 2, warnings: 19, errors: 0, exported: 63307, imported: 0 },
    tables: [
      { name: 'public.actor', target: 'new.actor', exported: 200, imported: null },
      { name: 'public.film', target: 'public.film', exported: 1000, imported: null },
    ],
  };
  app.applySnapshot(state);
  assert.equal(app.totals.exported, 63307);
  assert.equal(app.totals.warnings, 19);
  assert.equal(app.events.length, 0);
  app.tableFilter = 'ACTOR';
  assert.equal(app.visibleTables.length, 1);
  assert.equal(app.visibleTables[0].name, 'public.actor');
  app.tableFilter = 'new.actor';
  assert.equal(app.filteredTables.length, 1);
  assert.equal(app.number(null), '—');
  assert.equal(app.number(0), '0');
});

test('table details are fetched on expansion and collapse does not make a request', async () => {
  const { app, calls } = createApp([{ body: { name: 'public.actor', total: 5000, truncated: true, events: [{ sequence: 4999, text: 'latest' }] } }]);
  app.job = snapshot();
  await app.toggleTable('public.actor');
  assert.equal(calls[0].path, '/api/jobs/run1/table-logs?table=public.actor');
  assert.equal(app.tableDetail.total, 5000);
  assert.equal(app.tableDetail.events.length, 1);
  await app.toggleTable('public.actor');
  assert.equal(app.expandedTable, '');
  assert.equal(calls.length, 1);
});

test('large table inventories are paginated to fifty visible rows', () => {
  const { app } = createApp([]);
  app.aggregation = { totals: { tables: 10000 }, tables: Array.from({ length: 10000 }, (_, index) => ({ name: `public.table_${index}` })) };
  assert.equal(app.visibleTables.length, 50);
  assert.equal(app.tablePages, 200);
  app.tablePage = 200;
  assert.equal(app.visibleTables[49].name, 'public.table_9999');
  app.tableFilter = 'does-not-exist';
  assert.equal(app.visibleTables.length, 0);
});

test('imports the chosen file directly and renders a preview without a command request', async () => {
  const state = snapshot([], 'imported');
  state.returncode = null;
  state.aggregation = { totals: { exported: 63307 }, tables: [] };
  const { app, calls } = createApp([{ body: state }]);
  const file = { name: 'fetch.jsonl' };
  await app.importFile(file);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/log-imports');
  assert.equal(calls[0].options.body, file);
  assert.equal(app.job.status, 'imported');
  assert.equal(app.job.returncode, null);
  assert.equal(app.totals.exported, 63307);
  assert.equal(app.busy, false);
});

test('sample import uses the same upload path', async () => {
  const { app, calls } = createApp([
    { body: null, blobBody: 'sample log bytes' },
    { body: { ...snapshot([], 'imported'), returncode: null } },
  ]);
  await app.loadSample();
  assert.equal(calls[0].path, '/static/sample-fetch.jsonl');
  assert.equal(calls[1].path, '/api/log-imports');
  assert.equal(calls[1].options.body, 'sample log bytes');
  assert.equal(app.job.status, 'imported');
});

test('import failures keep the previous result and imports cannot replace a running command', async () => {
  const { app, calls } = createApp([{ status: 422, body: { detail: 'The log file is empty.' } }]);
  app.job = snapshot([], 'succeeded');
  await app.importFile({ name: 'empty.log' });
  assert.equal(app.error, 'The log file is empty.');
  assert.equal(app.job.status, 'succeeded');
  app.job.status = 'running';
  await app.importFile({ name: 'another.log' });
  assert.equal(calls.length, 1);
});

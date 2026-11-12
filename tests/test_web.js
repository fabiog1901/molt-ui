const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createApp(responses, viewport = {}) {
  let factory;
  const calls = [];
  let scheduled = 0;
  const context = {
    innerWidth: 1200, innerHeight: 800, ...viewport,
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
  vm.runInNewContext(fs.readFileSync('src/molt_ui/webapp/static/app.js', 'utf8'), context);
  return { app: factory(), calls, scheduled: () => scheduled };
}

const snapshot = (events = [], status = 'running') => ({ id: 'run1', command: 'fetch', status, cursor: events.at(-1)?.sequence || 0, returncode: status === 'running' ? null : 0, events, truncated: false });
const catalog = [{ id: 'fetch', options: [{ name: 'source', kind: 'string' }, { name: 'direct-copy', kind: 'bool' }] }];

test('failed jobs display the process diagnostic and stop polling', async () => {
  const failure = {...snapshot([], 'failed'), returncode: 2,
    error: 'Molt exited with code 2. connection refused', history_error: 'History could not be saved'};
  const {app, scheduled} = createApp([{body: failure}]);
  app.job = snapshot();
  await app.poll();
  assert.equal(app.running, false);
  assert.equal(app.error, failure.error + ' ' + failure.history_error);
  assert.equal(scheduled(), 0);
});

test('a job that fails before the start response displays its error immediately', async () => {
  const failure = {...snapshot([], 'failed'), returncode: 2,
    error: 'Molt exited with code 2. connection refused'};
  const {app, scheduled} = createApp([{body: failure}]);
  app.commands = catalog;
  await app.start();
  assert.equal(app.running, false);
  assert.equal(app.error, failure.error);
  assert.equal(scheduled(), 0);
});

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
  assert.equal(app.formatEvent(second), 'warning table=example');
});

test('restores the running job after refresh', async () => {
  const { app, scheduled } = createApp([{ body: catalog }, { body: snapshot() }, { body: [] }]);
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
  assert.equal(calls[0].options.headers['X-Log-Filename'], encodeURIComponent(file.name));
  assert.equal(app.job.status, 'imported');
  assert.equal(app.job.returncode, null);
  assert.equal(app.totals.exported, 63307);
  assert.equal(app.busy, false);
});

test('history selection follows the final log timestamp while the live run keeps its polling ID', () => {
  const {app} = createApp([]);
  const reserved = '2026-11-12T17.50.57Z', saved = '2026-11-12T17.50.58Z';
  app.job = {...snapshot(), id: reserved, record: {id: reserved}};
  app.selectedRecord = app.job.record;
  app.applySnapshot({...snapshot([], 'succeeded'), id: reserved, record: {id: saved}});
  assert.equal(app.job.id, reserved);
  assert.equal(app.selectedRecord.id, saved);
  assert.equal(app.tableLogBase, '/api/history/' + encodeURIComponent(saved));
});

test('timestamp run IDs are encoded when polling the job API', async () => {
  const id = '2026-11-12T17.50.58Z';
  const {app, calls} = createApp([{body: {...snapshot([], 'succeeded'), id}}]);
  app.job = {...snapshot(), id};
  await app.poll();
  assert.equal(calls[0].path, '/api/jobs/' + encodeURIComponent(id) + '?after=0');
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

test('wizard clears incompatible values before review and preserves the run record', async () => {
  const plan = {invocation: 'MOLT_SOURCE=postgres://user:secret@source/db molt fetch --direct-copy=true'};
  const record = {id: 'saved', invocation: plan.invocation};
  const {app,calls} = createApp([{body:plan},{body:{...snapshot(),record}}]);
  app.commands = [{id:'fetch', options:[
    {name:'source',kind:'string',stage:'connections',rules:[]},
    {name:'target',kind:'string',stage:'connections',rules:[]},
    {name:'direct-copy',kind:'bool',stage:'operation',rules:[{test:'data-load'}]},
    {name:'bucket-path',kind:'string',stage:'common',rules:[{test:'staged'}]},
    {name:'assume-role',kind:'string',stage:'advanced',rules:[{test:'staged'},{test:'bucket'}]},
    {name:'source-cdb',kind:'string',stage:'connections',rules:[{test:'dialect',value:'oracle'}]},
  ]}];
  app.values = {source:'postgres://user:secret@source/db',target:'postgres://target/db','direct-copy':'true','bucket-path':'s3://bucket','assume-role':'role','source-cdb':'oracle://cdb'};
  app.parametersChanged();
  assert.equal(app.values['bucket-path'],undefined);
  assert.equal(app.values['assume-role'],undefined);
  assert.equal(app.values['source-cdb'],undefined);
  assert.equal(app.prunedOptions.length,3);
  await app.goStep(app.reviewStep);
  assert.equal(calls[0].path,'/api/command-preview');
  assert.equal(app.step,app.reviewStep);
  assert.equal(app.preview.invocation,plan.invocation);
  await app.start();
  assert.equal(calls[1].path,'/api/jobs');
  assert.equal(app.job.record.invocation,plan.invocation);
  app.values.source='postgres://edited/db';
  assert.equal(app.job.record.invocation,plan.invocation);
});

test('review validation failure stays in the wizard and does not start a command', async () => {
  const {app,calls} = createApp([{status:422,body:{detail:'Provide a source connection'}}]);
  app.commands=catalog;
  app.step=1;
  await app.goStep(app.reviewStep);
  assert.equal(app.step,1);
  assert.equal(app.preview,null);
  assert.equal(app.wizardError,'Provide a source connection');
  assert.equal(app.busy,false);
  assert.equal(calls.length,1);
  assert.equal(calls[0].path,'/api/command-preview');
});

test('history is independent of in-memory output and can restore a saved invocation', async () => {
  const record={id:'previous',invocation:'molt fetch --direct-copy=true',status:'succeeded'};
  const {app,calls} = createApp([{body:[record]}]);
  await app.refreshHistory();
  assert.equal(calls[0].path,'/api/history');
  assert.equal(app.history[0].invocation,record.invocation);
  assert.equal(app.job,null);
});

test('defaults are shown without emitting untouched flags and checkboxes preserve explicit false', () => {
  const {app} = createApp([]);
  const mode={name:'mode',kind:'string',default:'data-load',rules:[]};
  const rows={name:'rows',kind:'bool',default:true,rules:[]};
  app.commands=[{id:'fetch', options:[mode,rows]}];
  assert.equal(app.fieldValue(mode),'data-load');
  assert.equal(app.fieldValue(rows),true);
  assert.deepEqual(JSON.parse(JSON.stringify(app.options())),{});
  app.setOption(rows,false);
  assert.equal(app.fieldValue(rows),false);
  assert.equal(app.options().rows,false);
});

test('source radios prune source-specific options before a connection string is provided', () => {
  const {app} = createApp([]);
  const oracle={name:'oracle-application-users',kind:'string',rules:[{test:'dialect',value:'oracle'}]};
  const slot={name:'pglogical-replication-slot-name',kind:'string',rules:[{test:'dialect',value:'postgres'}]};
  app.commands=[{id:'fetch', options:[oracle,slot]}];
  app.sourceKind='postgres';
  app.values={'oracle-application-users':'app','pglogical-replication-slot-name':'slot'};
  app.setSource('oracle');
  assert.equal(app.values['pglogical-replication-slot-name'],undefined);
  assert.equal(app.values['oracle-application-users'],'app');
  assert.equal(app.optionApplies(oracle,{}),true);
  assert.equal(app.optionApplies(slot,{}),false);
  assert.equal(app.requestPayload().source_kind,'oracle');
});

test('mandatory fields account for inherited connections and source selection changes', () => {
  const {app} = createApp([]);
  const source={name:'source',kind:'string',required:false,from_environment:true,rules:[]};
  app.commands=[{id:'fetch',default_source_dialect:'postgres',options:[source]}];
  app.sourceKind='postgres';
  assert.equal(app.isRequired(source),false);
  assert.equal(app.fieldPlaceholder(source),'Provided by MOLT_SOURCE');
  app.sourceKind='oracle';
  assert.equal(app.isRequired(source),true);
});

test('logging and metrics are separate from advanced and review remains the final step', async () => {
  const {app} = createApp([{body:{invocation:'molt fetch --help'}}]);
  app.commands=[{id:'fetch',options:[
    {name:'logging',kind:'string',stage:'logging',rules:[]},
    {name:'opt-out-telemetry',kind:'bool',stage:'metrics',rules:[]},
    {name:'table-concurrency',kind:'int',stage:'advanced',rules:[]},
  ]}];
  assert.equal(app.steps.length,7);
  await app.goStep(app.stages.indexOf('logging'));
  assert.equal(app.stepOptions.length,1);
  assert.equal(app.stepOptions[0].name,'logging');
  await app.goStep(app.step+1);
  assert.equal(app.currentStage,'metrics');
  assert.equal(app.stepOptions[0].name,'opt-out-telemetry');
  await app.goStep(app.step+1);
  assert.equal(app.currentStage,'review');
  assert.equal(app.step,app.steps.length-1);
});

test('disable logging preserves the selected level and restores it when unchecked', () => {
  const {app}=createApp([]);
  const option={name:'logging',kind:'string',default:'info',stage:'logging',rules:[],choices:[
    {value:'trace',label:'trace'},{value:'info',label:'info'},
  ]};
  app.commands=[{id:'fetch',options:[option]}];
  assert.equal(app.fieldValue(option),'info');
  app.setOption(option,'trace');
  app.toggleLogging(option,true);
  assert.equal(app.fieldValue(option),'disabled');
  assert.equal(app.options().logging,'disabled');
  assert.equal(app.choiceValue(option),'trace');
  app.toggleLogging(option,false);
  assert.equal(app.fieldValue(option),'trace');
  assert.equal(app.options().logging,'trace');
  app.setOption(option,'');
  assert.equal(Object.hasOwn(app.options(),'logging'),false);
  assert.equal(app.fieldValue(option),'info');
});

test('catalog incompatibility is visible and leaves command configuration unavailable', async () => {
  const { app, calls } = createApp([{ status: 503, body: { detail: 'Cannot display fetch: catalog changed.' } }, { body: null }, { body: [] }]);
  await app.init();
  assert.equal(app.error, 'Cannot display fetch: catalog changed.');
  assert.equal(app.commands.length, 0);
  assert.equal(calls.length, 3);
  assert.equal(app.historyLoaded, true);
});

test('a discovered command can become the initial selection when fetch is absent', async () => {
  const { app } = createApp([{ body: [{ id: 'future', options: [] }] }, { body: null }, { body: [] }]);
  await app.init();
  assert.equal(app.command, 'future');
  assert.equal(app.definition.id, 'future');
});

test('clearing a nonempty CLI default preserves an explicit empty argument', () => {
  const { app } = createApp([]);
  const url = { name: 'url', kind: 'string', default: 'postgres://root@localhost/db' };
  const source = { name: 'source', kind: 'string', default: '' };
  app.commands = [{ id: 'convert-postgres', options: [url, source] }];
  app.command = 'convert-postgres';
  assert.equal(app.fieldValue(url), url.default);
  assert.deepEqual(Object.keys(app.options()), []);
  app.setOption(url, '');
  assert.equal(app.fieldValue(url), '');
  assert.deepEqual(JSON.parse(JSON.stringify(app.options())), { url: '' });
  app.setOption(source, '');
  assert.deepEqual(JSON.parse(JSON.stringify(app.options())), { url: '' });
});

test('output collapse keeps its previous height and resizing stays within the viewport', () => {
  const { app } = createApp([]);
  app.setOutputHeight(320);
  app.toggleOutput();
  assert.equal(app.outputCollapsed, true);
  assert.equal(app.outputHeight, 320);
  app.toggleOutput();
  assert.equal(app.outputCollapsed, false);
  assert.equal(app.outputHeight, 320);
  app.resizeOutputBy(10000);
  assert.equal(app.outputHeight, 480);
  app.resizeOutputBy(-10000);
  assert.equal(app.outputHeight, 80);
  const { app: small } = createApp([], { innerHeight: 400 });
  small.setOutputHeight(400);
  assert.equal(small.outputHeight, 140);
});

test('maximizing output preserves its size and restores from maximized or minimized states', () => {
  const {app} = createApp([]);
  app.setOutputHeight(320);
  app.toggleOutputMaximized();
  assert.equal(app.outputMaximized, true);
  assert.equal(app.outputCollapsed, false);
  assert.equal(app.outputHeight, 320);
  app.toggleOutputMaximized();
  assert.equal(app.outputMaximized, false);
  assert.equal(app.outputHeight, 320);
  app.toggleOutput();
  app.toggleOutputMaximized();
  assert.equal(app.outputMaximized, true);
  assert.equal(app.outputCollapsed, false);
  app.toggleOutput();
  assert.equal(app.outputMaximized, false);
  assert.equal(app.outputCollapsed, true);
  app.toggleOutput();
  assert.equal(app.outputHeight, 320);
});

test('maximized output ignores drag resizing and restores normal size for explicit resizing', () => {
  const {app} = createApp([]);
  app.toggleOutputMaximized();
  app.beginOutputResize({button: 0});
  assert.equal(app.resizingOutput, false);
  app.setOutputHeight(300);
  assert.equal(app.outputMaximized, false);
  assert.equal(app.outputHeight, 300);
});

test('output splitter captures the pointer and ignores other pointers', () => {
  const { app } = createApp([]);
  const captures = [];
  const currentTarget = {
    setPointerCapture: id => captures.push(id),
    hasPointerCapture: id => captures.includes(id),
    releasePointerCapture: id => captures.splice(captures.indexOf(id), 1),
  };
  app.beginOutputResize({ button: 0, clientY: 600, pointerId: 1, currentTarget });
  app.moveOutputResize({ clientY: 500, pointerId: 2 });
  assert.equal(app.outputHeight, 240);
  app.moveOutputResize({ clientY: 500, pointerId: 1 });
  assert.equal(app.outputHeight, 340);
  app.endOutputResize({ pointerId: 1, currentTarget });
  assert.equal(app.resizingOutput, false);
  assert.equal(captures.length, 0);
});

test('history loads at startup and remains independent of the current output', async () => {
  const record = { id: 'older', command: 'verify', status: 'succeeded' };
  const current = { ...snapshot(), record: { id: 'current' } };
  const { app, calls } = createApp([{ body: catalog }, { body: current }, { body: [record] }]);
  await app.init();
  assert.equal(calls[2].path, '/api/history');
  assert.equal(app.historyLoaded, true);
  app.reviewRecord(record);
  assert.equal(app.reviewingHistory, true);
  assert.equal(app.job.id, current.id);
  app.selectedRecord = app.job.record;
  assert.equal(app.reviewingHistory, true);
  app.showCurrentSession();
  assert.equal(app.reviewingHistory, false);
  assert.equal(app.job.id, current.id);
});

test('manual output scrolling pauses follow and resuming follow reaches the latest line', () => {
  const { app } = createApp([]);
  const output = { scrollTop: 0, scrollHeight: 1000, clientHeight: 200 };
  app.$refs = { output };
  app.$nextTick = callback => callback();
  app.outputScrolled();
  assert.equal(app.followOutput, false);
  app.applySnapshot(snapshot([{ sequence: 1, text: 'new' }]));
  assert.equal(output.scrollTop, 0);
  app.followOutput = true;
  app.scrollOutputToEnd();
  assert.equal(output.scrollTop, 1000);
});

test('history drawer stays open through selection and current session until explicitly closed', async () => {
  const { app } = createApp([{ body: catalog }, { body: null }, { body: [] }], { innerWidth: 390, innerHeight: 650 });
  await app.init();
  assert.equal(app.historyOpen, true);
  app.historyOpen = true;
  await app.reviewRecord({ id: 'saved' });
  assert.equal(app.historyOpen, true);
  app.showCurrentSession();
  assert.equal(app.historyOpen, true);
  app.closeHistory();
  assert.equal(app.historyOpen, false);
});

test('clearing output preserves the live cursor, aggregates, and command history', async () => {
  const next = { ...snapshot([{ sequence: 102, stream: 'stdout', text: 'next line' }]), aggregation: { totals: { exported: 200 }, tables: [] } };
  const { app, calls } = createApp([{ body: next }]);
  const current = { ...snapshot([{ sequence: 101, stream: 'stdout', text: 'old line' }]), aggregation: next.aggregation, record: { id: 'saved' } };
  app.applySnapshot(current);
  app.history = [current.record];
  app.truncated = true;
  app.clearOutput();
  assert.equal(app.events.length, 0);
  assert.equal(app.cursor, 101);
  assert.equal(app.totals.exported, 200);
  assert.equal(app.history[0].id, 'saved');
  assert.equal(app.job.record.id, 'saved');
  assert.equal(app.truncated, false);
  assert.equal(app.outputCleared, true);
  await app.poll();
  assert.equal(calls[0].path, '/api/jobs/run1?after=101');
  assert.equal(app.events.length, 1);
  assert.equal(app.events[0].sequence, 102);
  assert.equal(app.outputCleared, false);
});

test('log emoji cover severities, aliases, and unstructured output', () => {
  const { app } = createApp([]);
  for (const [level, emoji] of Object.entries({ trace: '🔬', debug: '🐛', info: 'ℹ️', warn: '⚠️', warning: '⚠️', error: '❌', fatal: '💥', panic: '🚨' })) {
    assert.equal(app.logEmoji({ data: { level } }), emoji);
    assert.equal(app.logEmoji({ data: { level: level.toUpperCase() } }), emoji);
  }
  for (const stream of ['stdout', 'stderr', 'log']) {
    for (const data of [null, {}, { message: 'No level' }]) {
      assert.equal(app.showLogEmoji({ stream, data }), false);
      assert.equal(app.logEmoji({ stream, data }), '');
    }
    assert.equal(app.showLogEmoji({ stream, data: { level: 'warn' } }), true);
    assert.equal(app.logEmoji({ stream, data: { level: 'warn' } }), '⚠️');
  }
  assert.equal(app.logEmoji({ data: { level: 'custom' } }), '🔹');
});

test('formatted logs replace severity labels with the existing emoji and readable key=value fields', () => {
  const { app } = createApp([]);
  const text = '{"level":"info","table":"public.address","type":"summary","num_rows":603,"export_duration_ms":1000,"export_duration":"000h 00m 01s"}';
  const event = { stream: 'stdout', text, data: JSON.parse(text) };
  assert.equal(app.formatEvent(event), 'table=public.address, type=summary, num_rows=603, export_duration_ms=1000, export_duration=000h 00m 01s');
  assert.equal(app.logEmoji(event), 'ℹ️');
  assert.equal(event.text, text);
  assert.equal(JSON.stringify(event.data), text);
  assert.equal(app.formatEvent({ stream: 'stdout', data: { time: '2026-11-10T12:00:00Z', level: 'warn', message: 'Slow table', rows: 0 } }), '2026-11-10 12:00:00 Slow table rows=0');
});

test('formatted fields preserve complex values and plain output without textual stream labels', () => {
  const { app } = createApp([]);
  assert.equal(app.formatEvent({ data: { level: 'debug', enabled: false, cursor: null, options: { batch: 4 }, tables: ['public.actor'] } }), 'enabled=false, cursor=null, options={"batch":4}, tables=["public.actor"]');
  assert.equal(app.formatEvent({ stream: 'stderr', text: 'plain error' }), 'plain error');
  assert.equal(app.formatEvent({ data: { level: 'info', message: 'Ready' } }), 'Ready');
});

test('formatted UTC log timestamps use a space and second precision without changing the time', () => {
  const { app } = createApp([]);
  for (const time of ['2026-09-22T16.16.07Z', '2026-09-22T16:16:07Z', '2026-09-22T16:16:07.123Z', '2026-09-22T16:16:07.123456+00:00']) {
    const event = { data: { time, level: 'info', message: 'Ready' } };
    assert.equal(app.formatEvent(event), '2026-09-22 16:16:07 Ready');
    assert.equal(event.data.time, time);
    assert.equal(app.formatTimestamp(time), '2026-09-22 16:16:07');
  }
});

test('Connections tab shows source and target as text even with stale masking metadata', () => {
  const { app } = createApp([]);
  for (const name of ['source', 'target']) {
    assert.equal(app.inputType({ name, secret: true }), 'text');
    assert.equal(app.inputType({ name, secret: false }), 'text');
  }
  assert.equal(app.inputType({ name: 'password', secret: true }), 'password');
});

test('Re-run restores the modal and only starts a new job after review and Run', async () => {
  const saved = { id: 'saved', command: 'fetch', origin: 'command',
    argv: ['molt', 'fetch', '--direct-copy=false', '--logging=disabled'],
    options: { 'direct-copy': false, logging: 'disabled' },
    environment: { MOLT_SOURCE: 'mysql://saved/source', MOLT_TARGET: 'postgres://saved/target' } };
  const state = { ...snapshot(), record: { id: 'new' } };
  const { app, calls, scheduled } = createApp([{ body: { invocation: 'reviewed command' } }, { body: state }]);
  app.commands = [{ id: 'fetch', arguments: ['fetch'], default_source_dialect: 'postgres', options: [
    { name: 'source', kind: 'string', environment_variable: 'MOLT_SOURCE' },
    { name: 'target', kind: 'string', environment_variable: 'MOLT_TARGET' },
    { name: 'direct-copy', kind: 'bool' }, { name: 'logging', kind: 'string' },
  ] }];
  let opened = 0;
  app.$refs = { wizard: { showModal: () => opened++, querySelector: () => null } };
  app.$nextTick = callback => callback();
  app.values = { source: 'changed', target: 'changed' };
  app.selectedRecord = saved;
  app.rerunJob(saved);
  assert.equal(opened, 1);
  assert.equal(calls.length, 0);
  assert.equal(app.job, null);
  assert.equal(app.values.source, 'mysql://saved/source');
  assert.equal(app.values.target, 'postgres://saved/target');
  assert.equal(app.values['direct-copy'], false);
  assert.equal(app.values.logging, 'disabled');
  assert.equal(app.sourceKind, 'mysql');
  assert.equal(app.selectedRecord.id, 'saved');
  app.setOption(app.definition.options[0], 'mysql://edited/source');
  await app.goStep(app.reviewStep);
  assert.equal(calls[0].path, '/api/command-preview');
  assert.equal(app.job, null);
  await app.start();
  assert.equal(calls[1].path, '/api/jobs');
  assert.equal(JSON.parse(calls[1].options.body).options.source, 'mysql://edited/source');
  assert.equal(app.job.record.id, 'new');
  assert.equal(scheduled(), 1);
  assert.equal(saved.environment.MOLT_SOURCE, 'mysql://saved/source');
});

test('changing operations after Re-run preserves values and only submits applicable flags', () => {
  const {app, calls} = createApp([]);
  const common = [
    {name: 'source', kind: 'string'}, {name: 'target', kind: 'string'},
    {name: 'logging', kind: 'string'}, {name: 'log-file', kind: 'string', default: 'default.log'},
    {name: 'opt-out-telemetry', kind: 'bool'},
  ];
  app.commands = [
    {id: 'fetch', arguments: ['fetch'], default_source_dialect: 'postgres', options: [
      ...common, {name: 'direct-copy', kind: 'bool'}, {name: 'mode', kind: 'string'},
    ]},
    {id: 'verify', arguments: ['verify'], options: [...common, {name: 'rows', kind: 'bool', default: true}]},
  ];
  app.$refs = {wizard: {showModal() {}}};
  const options = {source: 'mysql://saved/source', target: 'postgres://saved/target', logging: 'disabled',
    'log-file': '', 'opt-out-telemetry': false, 'direct-copy': false, mode: 'data-load'};
  app.rerunJob({id: 'saved', command: 'fetch', origin: 'command', argv: ['molt', 'fetch'], options});
  app.previousLogLevel = 'debug';
  app.preview = {invocation: 'old command'};
  app.command = 'verify'; app.changeCommand();
  assert.equal(app.values.source, options.source);
  assert.equal(app.values.target, options.target);
  assert.equal(app.values.logging, 'disabled');
  assert.equal(app.previousLogLevel, 'debug');
  assert.equal(app.values['log-file'], '');
  assert.equal(app.options()['opt-out-telemetry'], false);
  assert.equal(Object.hasOwn(app.options(), 'direct-copy'), false);
  assert.equal(Object.hasOwn(app.options(), 'mode'), false);
  assert.equal(app.preview, null);
  app.setOption(app.definition.options.find(option => option.name === 'target'), 'postgres://edited/target');
  app.command = 'fetch'; app.changeCommand();
  assert.equal(app.sourceKind, 'mysql');
  assert.equal(app.options()['direct-copy'], false);
  assert.equal(app.options().mode, 'data-load');
  assert.equal(app.options().source, options.source);
  assert.equal(app.options().target, 'postgres://edited/target');
  assert.equal(calls.length, 0);
});

test('history rerun is unavailable for imports, missing argv, busy UI, or an active job', async () => {
  const { app, calls } = createApp([]);
  const saved = { id: 'saved', origin: 'command', argv: ['molt', 'fetch'] };
  assert.equal(app.canRerun({ origin: 'import', argv: [] }), false);
  assert.equal(app.canRerun({ origin: 'command', argv: [] }), false);
  assert.equal(app.canRerun(saved), true);
  app.busy = true;
  await app.rerunJob(saved);
  app.busy = false;
  app.job = snapshot();
  await app.rerunJob(saved);
  assert.equal(calls.length, 0);
});

test('an unavailable saved command leaves the history selection and output unchanged', () => {
  const saved = { id: 'saved', command: 'removed-command', origin: 'command', argv: ['molt', 'removed-command'] };
  const { app, calls } = createApp([]);
  app.selectedRecord = saved;
  app.job = snapshot([], 'succeeded');
  app.rerunJob(saved);
  assert.match(app.error, /unavailable in the current Molt version/);
  assert.equal(app.selectedRecord.id, 'saved');
  assert.equal(app.job.status, 'succeeded');
  assert.equal(calls.length, 0);
});

test('clear history deletes saved records without clearing the current logs or aggregates', async () => {
  const record = { id: 'saved', origin: 'command', argv: ['molt', 'fetch'] };
  const { app, calls } = createApp([{ body: { deleted: 1 } }]);
  app.history = [record]; app.selectedRecord = record;
  app.job = { ...snapshot([], 'succeeded'), record };
  app.events = [{ sequence: 1, text: 'output' }];
  app.aggregation = { totals: { exported: 200 }, tables: [] };
  await app.clearHistory();
  assert.equal(calls[0].path, '/api/history');
  assert.equal(calls[0].options.method, 'DELETE');
  assert.equal(app.history.length, 0);
  assert.equal(app.selectedRecord, null);
  assert.equal(app.job.record, null);
  assert.equal(app.events[0].text, 'output');
  assert.equal(app.totals.exported, 200);
  assert.equal(app.historyBusy, false);
  assert.equal(app.busy, false);
});

test('deleting the selected history item clears its view and preserves other items', async () => {
  const { app, calls } = createApp([{ body: { deleted: 1 } }]);
  const record = { id: 'selected' }, other = { id: 'other' };
  app.history = [record, other]; app.selectedRecord = record;
  app.job = { ...snapshot([], 'succeeded'), record };
  app.events = [{ sequence: 1, text: 'deleted output' }];
  app.historyOutput = { events: [{ sequence: 1, text: 'saved output' }] };
  await app.deleteHistoryRecord(record);
  assert.equal(calls[0].path, '/api/history/selected');
  assert.equal(calls[0].options.method, 'DELETE');
  assert.equal(app.history.length, 1);
  assert.equal(app.history[0].id, 'other');
  assert.equal(app.selectedRecord, null);
  assert.equal(app.historyOutput, null);
  assert.equal(app.job, null);
  assert.equal(app.events.length, 0);
  assert.equal(app.historyBusy, false);
});

test('deleting another history item preserves selected details and output', async () => {
  const { app } = createApp([{ body: { deleted: 1 } }]);
  const record = { id: 'remove' }, selected = { id: 'keep' };
  app.history = [record, selected]; app.selectedRecord = selected;
  app.historyOutput = { events: [{ sequence: 1, text: 'keep output' }] };
  app.job = { ...snapshot([], 'succeeded'), record };
  await app.deleteHistoryRecord(record);
  assert.equal(app.selectedRecord.id, 'keep');
  assert.equal(app.outputEvents[0].text, 'keep output');
  assert.equal(app.job.record, null);
});

test('failed single history deletion preserves selection and displays the error', async () => {
  const { app } = createApp([{ status: 503, body: { detail: 'Database unavailable' } }]);
  const record = { id: 'keep' };
  app.history = [record]; app.selectedRecord = record;
  await app.deleteHistoryRecord(record);
  assert.equal(app.history[0].id, 'keep');
  assert.equal(app.selectedRecord.id, 'keep');
  assert.equal(app.historyError, 'Database unavailable');
  assert.equal(app.historyBusy, false);
});

test('single history deletion is blocked during active jobs and pending operations', async () => {
  const { app, calls } = createApp([]);
  const record = { id: 'keep' };
  app.job = snapshot();
  await app.deleteHistoryRecord(record);
  app.job = null; app.busy = true;
  await app.deleteHistoryRecord(record);
  app.busy = false; app.historyBusy = true;
  await app.deleteHistoryRecord(record);
  app.historyBusy = false;
  await app.deleteHistoryRecord(null);
  assert.equal(calls.length, 0);
});

test('clear history is unavailable for active jobs, pending operations, or empty history', async () => {
  const { app, calls } = createApp([]);
  await app.clearHistory();
  app.history = [{ id: 'saved' }];
  app.job = snapshot();
  await app.clearHistory();
  app.job = null; app.historyBusy = true;
  await app.clearHistory();
  app.historyBusy = false; app.busy = true;
  await app.clearHistory();
  assert.equal(calls.length, 0);
});

test('failed history deletion preserves the selection and saved records', async () => {
  const { app } = createApp([{ status: 503, body: { detail: 'Database unavailable' } }]);
  const saved = { id: 'saved' };
  app.history = [saved]; app.selectedRecord = saved;
  await app.clearHistory();
  assert.equal(app.history.length, 1);
  assert.equal(app.selectedRecord.id, 'saved');
  assert.equal(app.historyError, 'Database unavailable');
  assert.equal(app.busy, false);
});

test('current session starts empty instead of restoring a completed or imported job', async () => {
  for (const status of ['succeeded', 'failed', 'imported']) {
    const previous = snapshot([{ sequence: 1, text: 'old output' }], status);
    const { app } = createApp([{ body: catalog }, { body: previous }, { body: [{ id: 'saved' }] }]);
    await app.init();
    assert.equal(app.job, null);
    assert.equal(app.events.length, 0);
    assert.equal(app.aggregation.tables.length, 0);
    assert.equal(app.selectedRecord, null);
    assert.equal(app.history.length, 1);
  }
});

test('returning to current session clears completed results while keeping saved history', () => {
  const { app, calls } = createApp([]);
  const saved = { id: 'saved', command: 'fetch' };
  app.history = [saved];
  app.applySnapshot({ ...snapshot([{ sequence: 1, text: 'old output' }], 'succeeded'), aggregation: { totals: { exported: 200 }, tables: [{ name: 'public.actor' }] } });
  app.reviewRecord(saved);
  app.showCurrentSession();
  assert.equal(app.job, null);
  assert.equal(app.events.length, 0);
  assert.equal(app.cursor, 0);
  assert.equal(app.aggregation.tables.length, 0);
  assert.equal(app.selectedRecord, null);
  assert.equal(app.history[0].id, 'saved');
  assert.equal(calls.length, 1); // Selecting the record reads its saved output.
});

test('selecting history reads saved output without replacing live output or its cursor', async () => {
  const page = { source: 'file', log_file: '/logs/previous.log', total: 2500, next_before: 501, events: [{ sequence: 501, stream: 'log', text: 'saved line' }] };
  const { app, calls } = createApp([{ body: page }]);
  app.applySnapshot({ ...snapshot([{ sequence: 100, text: 'live line' }]), record: { id: 'active' } });
  await app.reviewRecord({ id: 'older', command: 'verify' });
  assert.equal(calls[0].path, '/api/history/older/output');
  assert.equal(app.outputEvents[0].text, 'saved line');
  assert.equal(app.outputCursor, 2500);
  assert.equal(app.cursor, 100);
  app.applySnapshot({ ...snapshot([{ sequence: 101, text: 'new live line' }]), record: { id: 'active' } });
  assert.equal(app.outputEvents[0].text, 'saved line');
  app.clearOutput();
  assert.equal(app.outputEvents.length, 0);
  assert.equal(app.events.length, 2);
  app.showCurrentSession();
  assert.equal(app.outputEvents[1].text, 'new live line');
});

test('history displays rebuilt tables and expands saved table logs without replacing live progress', async () => {
  const savedAggregation = {totals: {tables: 1, exported: 603}, tables: [{name: 'public.actor', exported: 603, status: 'exported'}]};
  const page = {source: 'file', total: 5000, events: [{sequence: 5000, text: 'tail'}], aggregation: savedAggregation};
  const detail = {name: 'public.actor', total: 2, events: [{sequence: 1, text: 'saved actor log'}]};
  const {app, calls} = createApp([{body: page}, {body: detail}]);
  const live = {totals: {tables: 1, exported: 9}, tables: [{name: 'public.live', exported: 9}]};
  app.applySnapshot({...snapshot(), aggregation: live, record: {id: 'active'}});
  app.tableFilter = 'old filter'; app.tablePage = 10; app.expandedTable = 'old table';
  await app.reviewRecord({id: 'saved', command: 'fetch'});
  assert.equal(app.totals.exported, 603);
  assert.equal(app.visibleTables[0].name, 'public.actor');
  assert.equal(app.visibleTables[0].status, 'exported');
  assert.equal(app.tablePage, 1);
  assert.equal(app.expandedTable, '');
  await app.toggleTable('public.actor');
  assert.equal(calls[1].path, '/api/history/saved/table-logs?table=public.actor');
  assert.equal(app.tableDetail.events[0].text, 'saved actor log');
  app.applySnapshot({...snapshot(), aggregation: {...live, totals: {exported: 10}}});
  assert.equal(app.totals.exported, 603);
  app.showCurrentSession();
  assert.equal(app.totals.exported, 10);
  assert.equal(app.visibleTables[0].name, 'public.live');
  assert.equal(app.expandedTable, '');
});

test('history never displays live table statistics when saved logs cannot be loaded', async () => {
  const {app} = createApp([{status: 503, body: {detail: 'Log file is missing'}}]);
  app.applySnapshot({...snapshot(), aggregation: {totals: {exported: 100}, tables: [{name: 'public.live'}]}});
  await app.reviewRecord({id: 'missing', command: 'fetch'});
  assert.equal(app.visibleTables.length, 0);
  assert.equal(app.totals.exported, undefined);
  assert.equal(app.aggregation.totals.exported, 100);
  assert.equal(app.historyOutputError, 'Log file is missing');
});

test('saved output pagination replaces the page and can return to the latest lines', async () => {
  const older = { source: 'captured', total: 3000, next_before: null, events: [{ sequence: 1, text: 'first' }] };
  const latest = { source: 'captured', total: 3000, next_before: 1001, events: [{ sequence: 3000, text: 'last' }] };
  const { app, calls } = createApp([{ body: older }, { body: latest }]);
  app.selectedRecord = { id: 'saved' };
  await app.loadHistoryOutput(1001);
  assert.equal(calls[0].path, '/api/history/saved/output?before=1001');
  assert.equal(app.historyBefore, 1001);
  assert.equal(app.outputEvents[0].text, 'first');
  await app.loadHistoryOutput();
  assert.equal(app.historyBefore, null);
  assert.equal(app.outputEvents.length, 1);
  assert.equal(app.outputEvents[0].text, 'last');
});

test('late history output responses cannot replace a newly selected record', async () => {
  let resolveFirst;
  const first = new Promise(resolve => { resolveFirst = resolve; });
  const { app } = createApp([{ body: first }, { body: { source: 'captured', total: 1, events: [{ sequence: 1, text: 'second' }] } }]);
  const pending = app.reviewRecord({ id: 'first' });
  await app.reviewRecord({ id: 'second' });
  resolveFirst({ source: 'captured', total: 1, events: [{ sequence: 1, text: 'first' }] });
  await pending;
  assert.equal(app.selectedRecord.id, 'second');
  assert.equal(app.outputEvents[0].text, 'second');
  assert.equal(app.historyOutputLoading, false);
});

test('missing log files show an error without presenting unrelated live output', async () => {
  const { app } = createApp([{ status: 503, body: { detail: 'Could not open saved log file' } }]);
  app.applySnapshot(snapshot([{ sequence: 1, text: 'live line' }]));
  await app.reviewRecord({ id: 'previous' });
  assert.equal(app.historyOutputError, 'Could not open saved log file');
  assert.equal(app.outputEvents.length, 0);
  assert.equal(app.events[0].text, 'live line');
});

test('the active record shows live output and switches to its saved output on completion', async () => {
  const record = { id: 'active', command: 'fetch' };
  const completed = { ...snapshot([{ sequence: 2, text: 'last live line' }], 'succeeded'), record };
  const saved = { source: 'file', log_file: '/logs/fetch.log', total: 3, events: [{ sequence: 3, stream: 'log', text: 'saved file line' }] };
  const { app, calls } = createApp([{ body: completed }, { body: saved }]);
  app.applySnapshot({ ...snapshot([{ sequence: 1, text: 'live line' }]), record });
  await app.reviewRecord(record);
  assert.equal(app.showingSavedOutput, false);
  assert.equal(calls.length, 0);
  await app.poll();
  assert.equal(calls[1].path, '/api/history/active/output');
  assert.equal(app.showingSavedOutput, true);
  assert.equal(app.outputEvents[0].text, 'saved file line');
});

test('successful escape-password output on stderr is informational, not an error', () => {
  const { app } = createApp([]);
  app.job = { command: 'escape-password', status: 'succeeded' };
  const event = { stream: 'stderr', text: 'example%40value', data: null };
  assert.equal(app.logLevel(event), 'info');
  assert.equal(app.logEmoji(event), '');
  assert.equal(app.logEmoji({ ...event, data: { level: 'error', message: 'Explicit error' } }), '❌');
});

test('Re-run restores legacy argv values, explicit empty strings, and logging level', () => {
  const { app, calls } = createApp([]);
  app.commands = [{ id: 'convert-postgres', arguments: ['convert', 'postgres'], options: [
    { name: 'url', kind: 'string', default: 'postgres://default/db' },
    { name: 'out', kind: 'string', default: '' },
  ] }];
  let opened = false;
  app.$refs = { wizard: { showModal: () => { opened = true; } } };
  const record = { id: 'saved', command: 'convert-postgres', origin: 'command', argv: ['molt', 'convert', 'postgres', '--url=', '--out=file=name.sql'], options: {} };
  app.rerunJob(record);
  assert.equal(opened, true);
  assert.equal(app.values.url, '');
  assert.equal(app.values.out, 'file=name.sql');
  assert.equal(app.options().url, '');
  assert.equal(calls.length, 0);
});

test('Re-run preserves help-only jobs and allows switching to normal execution', () => {
  const { app } = createApp([]);
  app.commands = [{ id: 'fetch', arguments: ['fetch'], options: [{ name: 'source', kind: 'string', required: true }] }];
  app.$refs = { wizard: { showModal() {} } };
  app.rerunJob({ id: 'help', command: 'fetch', origin: 'help', argv: ['molt', 'fetch', '--help'], options: {} });
  assert.equal(app.wizardHelpOnly, true);
  assert.equal(app.requestPayload().help_only, true);
  assert.equal(app.isRequired(app.definition.options[0]), false);
  app.wizardHelpOnly = false;
  assert.equal(app.requestPayload().help_only, false);
  assert.equal(app.isRequired(app.definition.options[0]), true);
});

test('saved flags missing from the catalog produce a clear error before opening the modal', () => {
  const { app, calls } = createApp([]);
  app.commands = [{ id: 'fetch', arguments: ['fetch'], options: [] }];
  app.values = { source: 'draft' };
  app.rerunJob({ id: 'saved', command: 'fetch', origin: 'command', argv: ['molt', 'fetch', '--removed-flag=old'], options: {} });
  assert.match(app.error, /Cannot restore saved argument/);
  assert.equal(app.values.source, 'draft');
  assert.equal(calls.length, 0);
});

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
  assert.equal(app.reviewingHistory, false);
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

test('small screens begin with a closed history drawer and selecting a record closes it', async () => {
  const { app } = createApp([{ body: catalog }, { body: null }, { body: [] }], { innerWidth: 390, innerHeight: 650 });
  await app.init();
  assert.equal(app.historyOpen, false);
  app.historyOpen = true;
  app.reviewRecord({ id: 'saved' });
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
  assert.equal(app.logEmoji({ stream: 'stdout' }), '📄');
  assert.equal(app.logEmoji({ stream: 'stderr' }), '❌');
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
  for (const time of ['2026-09-22T16:16:07Z', '2026-09-22T16:16:07.123Z']) {
    const event = { data: { time, level: 'info', message: 'Ready' } };
    assert.equal(app.formatEvent(event), '2026-09-22 16:16:07 Ready');
    assert.equal(event.data.time, time);
  }
});

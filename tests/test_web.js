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
  const { app, calls } = createApp([{ status: 503, body: { detail: 'Cannot display fetch: catalog changed.' } }]);
  await app.init();
  assert.equal(app.error, 'Cannot display fetch: catalog changed.');
  assert.equal(app.commands.length, 0);
  assert.equal(calls.length, 1);
});

test('a discovered command can become the initial selection when fetch is absent', async () => {
  const { app } = createApp([{ body: [{ id: 'future', options: [] }] }, { body: null }]);
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

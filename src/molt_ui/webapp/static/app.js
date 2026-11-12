document.addEventListener('alpine:init', () => {
  Alpine.data('cliApp', () => ({
    commands: [], command: 'fetch', values: {}, advanced: false,
    job: null, events: [], cursor: 0, error: '', busy: false,
    timer: null, polling: false, truncated: false, outputCleared: false,
    aggregation: {totals: {}, tables: []}, tableFilter: '', tablePage: 1,
    expandedTable: '', tableDetail: null, detailError: '', detailLoading: false,
    rawOutput: false, followOutput: true,
    historyOpen: true, historyLoaded: false,
    outputHeight: 240, outputCollapsed: false, outputMaximized: false, resizingOutput: false,
    resizeStartY: 0, resizeStartHeight: 240, resizePointer: null,
    steps: ['Operation', 'Connections', 'Common options', 'Advanced', 'Logging', 'Metrics', 'Review'],
    stages: ['operation', 'connections', 'common', 'advanced', 'logging', 'metrics', 'review'],
    step: 0, preview: null, wizardError: '', wizardHelpOnly: false, advancedSearch: '', prunedOptions: [],
    history: [], historyBusy: false, historyError: '', selectedRecord: null, copyMessage: '',
    historyOutput: null, historyOutputError: '', historyOutputLoading: false, historyBefore: null,
    historyOutputCleared: false, historyOutputRequest: 0,
    sourceKind: '',
    previousLogLevel: 'info',
    overviewView: 'tables',

    get reviewingHistory() { return Boolean(this.selectedRecord); },
    get displayedRecord() { return this.reviewingHistory ? this.selectedRecord : this.job?.record; },
    get displayedAggregation() { return this.showingSavedOutput ? (this.historyOutput?.aggregation || {totals: {}, tables: []}) : this.aggregation; },
    get tableLogBase() { return this.showingSavedOutput ? `/api/history/${encodeURIComponent(this.selectedRecord.id)}` : (this.job ? `/api/jobs/${encodeURIComponent(this.job.id)}` : null); },
    get showingSavedOutput() { return this.reviewingHistory && !(this.running && this.selectedRecord.id === this.job?.record?.id); },
    get outputEvents() { return this.showingSavedOutput ? (this.historyOutput?.events || []) : this.events; },
    get outputCursor() { return this.showingSavedOutput ? (this.historyOutput?.total || 0) : this.cursor; },
    get displayedOutputCleared() { return this.showingSavedOutput ? this.historyOutputCleared : this.outputCleared; },
    get outputContext() {
      if (this.showingSavedOutput) return this.selectedRecord.command + ' · saved ' + (this.historyOutput?.source === 'file' ? 'log file' : 'output');
      return this.job ? this.job.command + ' · ' + this.job.status : 'No command running';
    },
    closeHistory() {
      this.historyOpen = false;
      this.$nextTick?.(() => this.$refs?.historyHandle?.focus());
    },
    showCurrentSession() {
      this.selectedRecord = null; this.copyMessage = '';
      this.historyOutputRequest++;
      this.historyOutput = null; this.historyOutputError = ''; this.historyOutputLoading = false;
      this.expandedTable = ''; this.tableDetail = null; this.detailError = ''; this.detailLoading = false;
      this.tableFilter = ''; this.tablePage = 1;
      if (!this.running) this.resetSession();
    },
    async reviewRecord(record) {
      this.selectedRecord = record; this.copyMessage = '';
      this.historyOutput = null; this.historyOutputError = ''; this.historyOutputCleared = false;
      this.historyBefore = null;
      this.expandedTable = ''; this.tableDetail = null; this.detailError = ''; this.detailLoading = false;
      this.tableFilter = ''; this.tablePage = 1;
      if (this.showingSavedOutput) await this.loadHistoryOutput();
    },
    async loadHistoryOutput(before = null) {
      if (!this.selectedRecord) return;
      const recordId = this.selectedRecord.id, requestId = ++this.historyOutputRequest;
      this.historyOutputLoading = true; this.historyOutputError = '';
      try {
        const page = await this.request(`/api/history/${encodeURIComponent(recordId)}/output${before === null ? '' : '?before=' + before}`);
        if (this.selectedRecord?.id !== recordId || requestId !== this.historyOutputRequest) return;
        this.historyOutput = page; this.historyBefore = before; this.historyOutputCleared = false;
        if (this.followOutput) this.scrollOutputToEnd();
      } catch (error) {
        if (this.selectedRecord?.id === recordId && requestId === this.historyOutputRequest) this.historyOutputError = error.message;
      } finally {
        if (requestId === this.historyOutputRequest) this.historyOutputLoading = false;
      }
    },
    outputMaxHeight() {
      const height = globalThis.innerHeight || 800;
      return Math.max(80, Math.min(Math.floor(height * .6), height - 260));
    },
    fitOutput() { this.outputHeight = Math.min(this.outputMaxHeight(), Math.max(80, this.outputHeight)); },
    setOutputHeight(height) {
      this.outputMaximized = false;
      this.outputCollapsed = false;
      this.outputHeight = height;
      this.fitOutput();
      if (this.followOutput) this.scrollOutputToEnd();
    },
    resizeOutputBy(delta) { this.setOutputHeight(this.outputHeight + delta); },
    toggleOutput() {
      this.outputMaximized = false;
      this.outputCollapsed = !this.outputCollapsed;
      if (!this.outputCollapsed) { this.fitOutput(); if (this.followOutput) this.scrollOutputToEnd(); }
    },
    toggleOutputMaximized() {
      this.outputMaximized = !this.outputMaximized;
      this.outputCollapsed = false;
      this.resizingOutput = false;
      if (!this.outputMaximized) this.fitOutput();
      if (this.followOutput) this.scrollOutputToEnd();
    },
    beginOutputResize(event) {
      if (this.outputMaximized) return;
      if (event.button !== undefined && event.button !== 0) return;
      if (this.outputCollapsed) this.setOutputHeight(80);
      this.resizingOutput = true;
      this.resizeStartY = event.clientY; this.resizeStartHeight = this.outputHeight;
      this.resizePointer = event.pointerId;
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    moveOutputResize(event) {
      if (!this.resizingOutput || event.pointerId !== this.resizePointer) return;
      this.setOutputHeight(this.resizeStartHeight + this.resizeStartY - event.clientY);
    },
    endOutputResize(event) {
      if (event.pointerId !== this.resizePointer) return;
      this.resizingOutput = false;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      this.resizePointer = null;
    },
    clearOutput() {
      if (this.showingSavedOutput) {
        if (this.historyOutput) this.historyOutput = {...this.historyOutput, events: []};
        this.historyOutputCleared = true;
        return;
      }
      this.events = [];
      this.truncated = false;
      this.outputCleared = true;
    },
    logLevel(event) { return String(event.data?.level || 'info').toLowerCase(); },
    showLogEmoji(event) { return Object.hasOwn(event.data ?? {}, 'level'); },
    logEmoji(event) {
      if (!this.showLogEmoji(event)) return '';
      return ({trace: '🔬', debug: '🐛', info: 'ℹ️', warn: '⚠️', warning: '⚠️',
        error: '❌', fatal: '💥', panic: '🚨'})[this.logLevel(event)] || '🔹';
    },
    scrollOutputToEnd() {
      if (!this.$refs?.output) return;
      this.$nextTick(() => { const panel = this.$refs?.output; if (panel) panel.scrollTop = panel.scrollHeight; });
    },
    outputScrolled() {
      if (this.outputCollapsed || this.showingSavedOutput) return;
      const panel = this.$refs?.output;
      if (panel) this.followOutput = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
    },

    get definition() { return this.commands.find(item => item.id === this.command); },
    get running() { return this.job?.status === 'running'; },
    get totals() { return this.displayedAggregation.totals || {}; },
    get currentStage() { return this.stages[this.step]; },
    get reviewStep() { return this.stages.indexOf('review'); },
    get stepOptions() {
      const values = this.rawOptions();
      return (this.definition?.options || []).filter(option =>
        option.stage === this.stages[this.step] && this.optionApplies(option, values) &&
        (this.currentStage !== 'advanced' || `${option.name} ${option.label} ${option.description}`.toLowerCase().includes(this.advancedSearch.toLowerCase())));
    },
    optionApplies(option, values) {
      const mode = values.mode || 'data-load';
      const direct = mode === 'data-load' && values['direct-copy'] === true;
      const schemes = {postgres: 'postgres', postgresql: 'postgres', mysql: 'mysql', oracle: 'oracle', cockroachdb: 'cockroachdb', cockroach: 'cockroachdb'};
      const dialect = (this.command === 'fetch' && this.sourceKind) || (values.source ? (schemes[values.source.split(':')[0].toLowerCase()] || 'unknown') : (this.definition?.default_source_dialect || 'unknown'));
      return (option.rules || []).every(rule => {
        switch (rule.test) {
          case 'data-load': return mode === 'data-load';
          case 'staged': return !direct;
          case 'bucket': return Boolean(values['bucket-path']);
          case 'local': return Boolean(values['local-path']);
          case 'recreate': return values['table-handling'] === 'drop-on-target-and-recreate' && !values['fetch-id'];
          case 'empty-target': return !['truncate-if-exists', 'drop-on-target-and-recreate'].includes(values['table-handling']) && !values['fetch-id'] && !values['continuation-token'] && mode !== 'export-only';
          case 'dialect': return dialect === 'unknown' || dialect === rule.value;
          default: return true;
        }
      });
    },
    parametersChanged() {
      this.preview = null; this.wizardError = '';
      for (let pass = 0; pass < 3; pass++) {
        const values = this.rawOptions();
        for (const option of this.definition?.options || []) {
          if (!this.optionApplies(option, values) && Object.hasOwn(this.values, option.name)) {
            delete this.values[option.name];
            if (!this.prunedOptions.includes(option.name)) this.prunedOptions.push(option.name);
          }
        }
      }
    },
    inputType(option) {
      if (['source', 'target'].includes(option.name)) return 'text';
      return option.secret ? 'password' : 'text';
    },
    fieldValue(option) {
      const value = this.values[option.name];
      if (value !== undefined) return option.kind === 'bool' ? value === true || value === 'true' : value;
      const dialect = this.sourceKind || this.definition?.default_source_dialect;
      return option.default_by_source?.[dialect] ?? option.default ?? (option.kind === 'bool' ? false : '');
    },
    setOption(option, value) {
      if (value === '' && (!option.default || option.choices?.length)) delete this.values[option.name];
      else this.values[option.name] = value;
      if (option.name === 'logging' && value && value !== 'disabled') this.previousLogLevel = value;
      this.parametersChanged();
    },
    choiceValue(option) {
      return option.name === 'logging' && this.fieldValue(option) === 'disabled' ? this.previousLogLevel : this.fieldValue(option);
    },
    toggleLogging(option, disabled) {
      if (disabled && this.fieldValue(option) !== 'disabled') this.previousLogLevel = this.fieldValue(option);
      this.setOption(option, disabled ? 'disabled' : this.previousLogLevel);
    },
    setSource(kind) {
      if (this.sourceKind === kind) return;
      this.sourceKind = kind;
      delete this.values.source;
      this.parametersChanged();
    },
    isRequired(option) {
      if (this.wizardHelpOnly) return false;
      if (option.name === 'source' && this.command === 'fetch' && this.sourceKind && option.from_environment) {
        const configured = this.definition?.default_source_dialect;
        if (configured !== 'unknown' && configured !== this.sourceKind && !(configured === 'cockroachdb' && this.sourceKind === 'postgres')) return true;
      }
      return Boolean(option.required);
    },
    fieldPlaceholder(option) {
      if (option.from_environment && !this.isRequired(option)) return 'Provided by MOLT_' + option.name.toUpperCase().replaceAll('-', '_');
      return option.default_label || 'Not set';
    },
    requestPayload(helpOnly = false) {
      return {command: this.command, options: this.options(), help_only: helpOnly || this.wizardHelpOnly,
        ...(this.command === 'fetch' && this.sourceKind ? {source_kind: this.sourceKind} : {})};
    },
    openWizard(helpOnly = false) {
      if (this.running || this.busy) return;
      this.wizardHelpOnly = helpOnly === true;
      if (this.command === 'fetch' && !this.sourceKind) {
        const scheme = String(this.values.source || '').split(':')[0].toLowerCase();
        const dialect = ({postgresql:'postgres', postgres:'postgres', cockroach:'postgres', cockroachdb:'postgres', mysql:'mysql', oracle:'oracle'})[scheme] || this.definition?.default_source_dialect;
        this.sourceKind = ['postgres', 'oracle', 'mysql'].includes(dialect) ? dialect : 'postgres';
      }
      this.step = 0; this.preview = null; this.wizardError = ''; this.prunedOptions = []; this.advancedSearch = '';
      this.$refs.wizard.showModal();
    },
    closeWizard() { if (!this.busy) this.$refs.wizard.close(); },
    async goStep(index) {
      if (this.busy) return;
      index = Math.max(0, Math.min(this.steps.length - 1, index));
      if (index === this.reviewStep) {
        this.parametersChanged();
        this.busy = true; this.wizardError = '';
        try {
          this.preview = await this.request('/api/command-preview', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(this.requestPayload()),
          });
        } catch (error) { this.wizardError = error.message; return; }
        finally { this.busy = false; }
      }
      this.step = index;
      if (this.$refs?.wizard) this.$nextTick(() => this.$refs.wizard.querySelector('#wizard-step-' + index)?.focus());
    },
    async refreshHistory() {
      this.historyBusy = true; this.historyError = '';
      try {
        this.history = await this.request('/api/history');
        this.historyLoaded = true;
        if (this.selectedRecord) this.selectedRecord = this.history.find(record => record.id === this.selectedRecord.id) || this.selectedRecord;
      }
      catch (error) { this.historyError = error.message; }
      finally { this.historyBusy = false; }
    },
    async deleteHistoryRecord(record) {
      if (!record || this.running || this.busy || this.historyBusy) return;
      this.historyBusy = true; this.historyError = '';
      try {
        await this.request(`/api/history/${encodeURIComponent(record.id)}`, {method: 'DELETE'});
        this.history = this.history.filter(item => item.id !== record.id);
        if (this.job?.record?.id === record.id) this.job.record = null;
        if (this.selectedRecord?.id === record.id) this.showCurrentSession();
      } catch (error) { this.historyError = error.message; }
      finally { this.historyBusy = false; }
    },
    async clearHistory() {
      if (this.running || this.busy || this.historyBusy || !this.history.length) return;
      this.busy = true; this.historyBusy = true; this.historyError = '';
      try {
        await this.request('/api/history', {method: 'DELETE'});
        this.history = []; this.selectedRecord = null; this.copyMessage = '';
        this.historyOutputRequest++; this.historyOutput = null; this.historyOutputError = ''; this.historyOutputLoading = false;
        this.historyLoaded = true;
        if (this.job) this.job.record = null;
      } catch (error) { this.historyError = error.message; }
      finally { this.busy = false; this.historyBusy = false; }
    },
    canRerun(record) {
      return Boolean(record && ['command', 'help'].includes(record.origin) && record.argv?.length > 1);
    },
    rerunJob(record) {
      if (!this.canRerun(record) || this.running || this.busy) return;
      this.error = '';
      try {
        const definition = this.commands.find(item => item.id === record.command);
        if (!definition) throw new Error('This saved command is unavailable in the current Molt version.');
        const known = new Map(definition.options.map(option => [option.name, option]));
        const path = definition.arguments || [record.command];
        if (!path.every((argument, index) => record.argv[index + 1] === argument)) {
          throw new Error('The saved command arguments no longer match the command catalog.');
        }
        const values = {};
        let helpOnly = record.origin === 'help';
        const args = record.argv.slice(path.length + 1);
        for (let index = 0; index < args.length; index++) {
          const argument = args[index];
          if (argument === '--help' || argument === '-h') { helpOnly = true; continue; }
          const match = /^--([^=]+)(?:=(.*))?$/s.exec(argument);
          const option = match && known.get(match[1]);
          if (!option) throw new Error(`Cannot restore saved argument ${argument}: update the command configuration for this Molt version.`);
          let value = match[2];
          if (value === undefined) value = option.kind === 'bool' ? 'true' : args[++index];
          if (value === undefined) throw new Error(`The saved --${option.name} argument has no value.`);
          if (option.kind === 'bool') {
            if (!['true', 'false'].includes(value)) throw new Error(`The saved --${option.name} value cannot be displayed as a checkbox.`);
            value = value === 'true';
          }
          values[option.name] = value;
        }
        for (const [name, value] of Object.entries(record.options || {})) {
          if (!known.has(name)) throw new Error(`The saved --${name} option is unavailable in this Molt version.`);
          values[name] = value;
        }
        for (const option of definition.options) {
          if (option.environment_variable && !Object.hasOwn(values, option.name) && Object.hasOwn(record.environment || {}, option.environment_variable)) {
            values[option.name] = record.environment[option.environment_variable];
          }
        }
        this.command = record.command;
        this.values = values;
        this.sourceKind = '';
        const scheme = String(values.source || '').split(':')[0].toLowerCase();
        const dialect = ({postgresql:'postgres', postgres:'postgres', cockroach:'postgres', cockroachdb:'postgres', mysql:'mysql', oracle:'oracle'})[scheme];
        if (this.command === 'fetch') {
          this.sourceKind = dialect || (Object.keys(values).some(name => values[name] && (name.startsWith('oracle-') || name === 'source-cdb' || name === 'source-oracle-wallet-location')) ? 'oracle' : '');
        }
        this.previousLogLevel = values.logging && values.logging !== 'disabled' ? values.logging : 'info';
        this.openWizard(helpOnly);
      } catch (error) { this.error = error.message; }
    },
    async copyCommand(text) {
      try { await navigator.clipboard.writeText(text); this.copyMessage = 'Copied'; }
      catch { this.copyMessage = 'Select and copy the command below.'; }
    },
    get filteredTables() {
      const term = this.tableFilter.toLowerCase();
      return (this.displayedAggregation.tables || []).filter(table => `${table.name} ${table.target || ''}`.toLowerCase().includes(term));
    },
    get tablePages() { return Math.max(1, Math.ceil(this.filteredTables.length / 50)); },
    get visibleTables() {
      const page = Math.min(this.tablePage, this.tablePages);
      return this.filteredTables.slice((page - 1) * 50, page * 50);
    },
    number(value) { return value === null || value === undefined ? '—' : Number(value).toLocaleString(); },
    async toggleTable(name) {
      if (this.expandedTable === name) { this.expandedTable = ''; return; }
      this.expandedTable = name; this.tableDetail = null; this.detailError = '';
      await this.loadTableLogs();
    },
    async loadTableLogs() {
      if (!this.expandedTable || !this.tableLogBase || this.detailLoading) return;
      const name = this.expandedTable, base = this.tableLogBase;
      this.detailLoading = true;
      try {
        const detail = await this.request(`${base}/table-logs?table=${encodeURIComponent(name)}`);
        if (this.expandedTable === name && this.tableLogBase === base) {
          this.tableDetail = detail; this.detailError = '';
        }
      } catch (error) {
        if (this.expandedTable === name && this.tableLogBase === base) this.detailError = error.message;
      } finally {
        if (this.tableLogBase === base) {
          this.detailLoading = false;
          if (this.expandedTable && this.expandedTable !== name) await this.loadTableLogs();
        }
      }
    },

    async init() {
      if ((globalThis.innerWidth || 1200) <= 600) this.outputHeight = 160;
      this.fitOutput();
      try {
        this.commands = await this.request('/api/commands');
        if (!this.definition) this.command = this.commands[0]?.id || '';
      } catch (error) { this.error = error.message; }
      try {
        const latest = await this.request('/api/jobs');
        if (latest?.status === 'running') {
          if (this.commands.some(item => item.id === latest.command)) this.command = latest.command;
          this.applySnapshot(latest);
          if (this.running) this.schedulePoll();
        }
      } catch (error) { if (!this.error) this.error = error.message; }
      await this.refreshHistory();
    },
    destroy() { clearTimeout(this.timer); },
    changeCommand() {
      // Keep entered values when switching operations. rawOptions() limits
      // the command to its catalog, so other operations' settings stay parked
      // here and are available again when the user switches back.
      if (this.command === 'fetch') {
        const scheme = String(this.values.source || '').split(':')[0].toLowerCase();
        const dialect = ({postgresql:'postgres', postgres:'postgres', cockroach:'postgres', cockroachdb:'postgres', mysql:'mysql', oracle:'oracle'})[scheme];
        const configured = this.definition?.default_source_dialect;
        this.sourceKind = dialect || this.sourceKind || (['postgres', 'oracle', 'mysql'].includes(configured) ? configured : 'postgres');
      }
      this.preview = null; this.wizardError = ''; this.prunedOptions = [];
      this.parametersChanged();
    },
    resetSession() {
      clearTimeout(this.timer);
      this.job = null; this.selectedRecord = null;
      this.historyOutputRequest++;
      this.historyOutput = null; this.historyOutputError = ''; this.historyOutputLoading = false;
      this.events = []; this.cursor = 0; this.truncated = false; this.outputCleared = false;
      this.aggregation = {totals: {}, tables: []};
      this.expandedTable = ''; this.tableDetail = null; this.detailError = '';
      this.tableFilter = ''; this.tablePage = 1;
    },
    resetRun(snapshot) {
      this.resetSession();
      this.applySnapshot(snapshot);
      this.selectedRecord = null;
      if (this.historyLoaded) this.refreshHistory();
    },
    async importFile(file) {
      if (!file || this.running || this.busy) return;
      this.busy = true; this.error = '';
      try {
        this.resetRun(await this.request('/api/log-imports', {
          method: 'POST', headers: {'Content-Type': 'application/octet-stream',
            ...(file.name ? {'X-Log-Filename': encodeURIComponent(file.name)} : {})}, body: file,
        }));
        this.$refs?.importer?.close();
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
    async loadSample() {
      if (this.running || this.busy) return;
      this.busy = true; this.error = '';
      try {
        const response = await fetch('/static/sample-fetch.jsonl');
        if (!response.ok) throw new Error('Could not load the sample log.');
        const snapshot = await this.request('/api/log-imports', {
          method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: await response.blob(),
        });
        this.resetRun(snapshot);
        this.$refs?.importer?.close();
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
    rawOptions() {
      const result = {};
      for (const option of this.definition?.options || []) {
        const value = this.values[option.name];
        if (value !== undefined && (value !== '' || Boolean(option.default))) {
          result[option.name] = option.kind === 'bool' ? value === true || value === 'true' : String(value);
        }
      }
      return result;
    },
    options() {
      const values = this.rawOptions();
      return Object.fromEntries(Object.entries(values).filter(([name]) =>
        this.optionApplies(this.definition.options.find(option => option.name === name), values)));
    },
    async request(path, options = {}) {
      const response = await fetch(path, options);
      const body = await response.json();
      if (!response.ok) {
        const error = new Error(typeof body.detail === 'string' ? body.detail : 'Request failed. Check the form values.');
        error.status = response.status;
        throw error;
      }
      return body;
    },
    applySnapshot(snapshot) {
      const panel = this.$refs?.output;
      const follow = panel && this.followOutput && !this.outputCollapsed && !this.showingSavedOutput;
      if (this.selectedRecord && this.selectedRecord.id === this.job?.record?.id
          && snapshot.record && this.selectedRecord.id !== snapshot.record.id) {
        this.selectedRecord = snapshot.record;
      }
      this.job = snapshot;
      this.error = [snapshot.error, snapshot.history_error].filter(Boolean).join(' ');
      this.aggregation = snapshot.aggregation || {totals: {}, tables: []};
      this.truncated ||= snapshot.truncated || this.events.length + snapshot.events.length > 2000;
      this.events = [...this.events, ...snapshot.events].slice(-2000);
      if (snapshot.events.length) this.outputCleared = false;
      this.cursor = snapshot.cursor;
      if (follow) this.$nextTick(() => { panel.scrollTop = panel.scrollHeight; });
    },
    async start(helpOnly = false) {
      if (this.running || this.busy) return;
      this.busy = true;
      this.error = '';
      try {
        const snapshot = await this.request('/api/jobs', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.requestPayload(helpOnly)),
        });
        this.resetRun(snapshot);
        if (this.$refs?.wizard?.open) this.$refs.wizard.close();
        if (this.running) this.schedulePoll();
      } catch (error) { this.error = error.message; this.wizardError = error.message; }
      finally { this.busy = false; }
    },
    schedulePoll() { clearTimeout(this.timer); this.timer = setTimeout(() => this.poll(), 400); },
    async poll() {
      if (!this.job || this.polling) return;
      this.polling = true;
      const jobId = this.job.id;
      try {
        const snapshot = await this.request(`/api/jobs/${encodeURIComponent(jobId)}?after=${this.cursor}`);
        if (this.job?.id !== jobId) return;
        this.applySnapshot(snapshot);
        if (!this.running && this.historyLoaded) await this.refreshHistory();
        if (!this.running && this.selectedRecord?.id === snapshot.record?.id) await this.loadHistoryOutput();
        const selected = (this.displayedAggregation.tables || []).find(table => table.name === this.expandedTable);
        if (selected && (!this.tableDetail || this.tableDetail.total !== selected.log_lines)) await this.loadTableLogs();
      } catch (error) {
        if (this.job?.id !== jobId) return;
        if (error.status === 404) {
          this.job.status = 'unavailable';
          this.error = error.message;
        } else {
          this.error = `${error.message} Retrying connection…`;
        }
      }
      finally {
        this.polling = false;
        if (this.running) this.schedulePoll();
      }
    },
    async stop() {
      if (!this.job) return;
      try {
        await this.request(`/api/jobs/${encodeURIComponent(this.job.id)}/stop`, {method: 'POST'});
        await this.poll();
      } catch (error) { this.error = error.message; }
    },
    formatTimestamp(value) {
      if (value == null) return '';
      return typeof value === 'string'
        ? value.replace(/^(\d{4}-\d{2}-\d{2})T(\d{2})[.:](\d{2})[.:](\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/, '$1 $2:$3:$4')
        : value;
    },
    formatEvent(event) {
      if (!event.data) return event.text;
      const { time = '', level, message = '', ...fields } = event.data;
      const details = Object.entries(fields).map(([key, value]) =>
        `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`).join(', ');
      const timestamp = this.formatTimestamp(time);
      return [timestamp, message, details].filter(part => part !== '' && part != null).join(' ');
    },
  }));
});

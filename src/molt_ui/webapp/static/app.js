document.addEventListener('alpine:init', () => {
  Alpine.data('cliApp', () => ({
    commands: [], command: 'fetch', values: {}, advanced: false,
    job: null, events: [], cursor: 0, error: '', busy: false,
    timer: null, polling: false, truncated: false, outputCleared: false,
    aggregation: {totals: {}, tables: []}, tableFilter: '', tablePage: 1,
    expandedTable: '', tableDetail: null, detailError: '', detailLoading: false,
    rawOutput: false, followOutput: true,
    historyOpen: true, historyLoaded: false,
    outputHeight: 240, outputCollapsed: false, resizingOutput: false,
    resizeStartY: 0, resizeStartHeight: 240, resizePointer: null,
    steps: ['Operation', 'Connections', 'Common options', 'Advanced', 'Logging', 'Metrics', 'Review'],
    stages: ['operation', 'connections', 'common', 'advanced', 'logging', 'metrics', 'review'],
    step: 0, preview: null, wizardError: '', advancedSearch: '', prunedOptions: [],
    history: [], historyBusy: false, historyError: '', selectedRecord: null, copyMessage: '',
    sourceKind: '',
    previousLogLevel: 'info',

    get reviewingHistory() { return Boolean(this.selectedRecord && this.selectedRecord.id !== this.job?.record?.id); },
    reviewRecord(record) {
      this.selectedRecord = record; this.copyMessage = '';
      if ((globalThis.innerWidth || 1200) <= 850) this.historyOpen = false;
    },
    outputMaxHeight() {
      const height = globalThis.innerHeight || 800;
      return Math.max(80, Math.min(Math.floor(height * .6), height - 260));
    },
    fitOutput() { this.outputHeight = Math.min(this.outputMaxHeight(), Math.max(80, this.outputHeight)); },
    setOutputHeight(height) {
      this.outputCollapsed = false;
      this.outputHeight = height;
      this.fitOutput();
      if (this.followOutput) this.scrollOutputToEnd();
    },
    resizeOutputBy(delta) { this.setOutputHeight(this.outputHeight + delta); },
    toggleOutput() {
      this.outputCollapsed = !this.outputCollapsed;
      if (!this.outputCollapsed) { this.fitOutput(); if (this.followOutput) this.scrollOutputToEnd(); }
    },
    beginOutputResize(event) {
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
      this.events = [];
      this.truncated = false;
      this.outputCleared = true;
    },
    logLevel(event) { return String(event.data?.level || event.stream || 'info').toLowerCase(); },
    logEmoji(event) {
      return ({trace: '🔬', debug: '🐛', info: 'ℹ️', warn: '⚠️', warning: '⚠️',
        error: '❌', fatal: '💥', panic: '🚨', stdout: '📄', stderr: '❌'})[this.logLevel(event)] || '🔹';
    },
    scrollOutputToEnd() {
      if (!this.$refs?.output) return;
      this.$nextTick(() => { const panel = this.$refs?.output; if (panel) panel.scrollTop = panel.scrollHeight; });
    },
    outputScrolled() {
      if (this.outputCollapsed) return;
      const panel = this.$refs?.output;
      if (panel) this.followOutput = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
    },

    get definition() { return this.commands.find(item => item.id === this.command); },
    get running() { return this.job?.status === 'running'; },
    get totals() { return this.aggregation.totals; },
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
      return {command: this.command, options: this.options(), help_only: helpOnly,
        ...(this.command === 'fetch' && this.sourceKind ? {source_kind: this.sourceKind} : {})};
    },
    openWizard() {
      if (this.running || this.busy) return;
      if (this.command === 'fetch' && !this.sourceKind) {
        const scheme = String(this.values.source || '').split(':')[0].toLowerCase();
        const dialect = ({postgresql:'postgres', postgres:'postgres', mysql:'mysql', oracle:'oracle'})[scheme] || this.definition?.default_source_dialect;
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
    async copyCommand(text) {
      try { await navigator.clipboard.writeText(text); this.copyMessage = 'Copied'; }
      catch { this.copyMessage = 'Select and copy the command below.'; }
    },
    get filteredTables() {
      const term = this.tableFilter.toLowerCase();
      return this.aggregation.tables.filter(table => `${table.name} ${table.target || ''}`.toLowerCase().includes(term));
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
      if (!this.expandedTable || !this.job || this.detailLoading) return;
      const name = this.expandedTable, jobId = this.job.id;
      this.detailLoading = true;
      try {
        const detail = await this.request(`/api/jobs/${jobId}/table-logs?table=${encodeURIComponent(name)}`);
        if (this.expandedTable === name && this.job?.id === jobId) {
          this.tableDetail = detail; this.detailError = '';
        }
      } catch (error) {
        if (this.expandedTable === name && this.job?.id === jobId) this.detailError = error.message;
      } finally {
        this.detailLoading = false;
        if (this.expandedTable && (this.expandedTable !== name || this.job?.id !== jobId)) await this.loadTableLogs();
      }
    },

    async init() {
      if ((globalThis.innerWidth || 1200) <= 850) this.historyOpen = false;
      if ((globalThis.innerWidth || 1200) <= 600) this.outputHeight = 160;
      this.fitOutput();
      try {
        this.commands = await this.request('/api/commands');
        if (!this.definition) this.command = this.commands[0]?.id || '';
      } catch (error) { this.error = error.message; }
      try {
        const latest = await this.request('/api/jobs');
        if (latest) {
          if (this.commands.some(item => item.id === latest.command)) this.command = latest.command;
          this.applySnapshot(latest);
          if (this.running) this.schedulePoll();
        }
      } catch (error) { if (!this.error) this.error = error.message; }
      await this.refreshHistory();
    },
    destroy() { clearTimeout(this.timer); },
    changeCommand() {
      this.values = {};
      this.previousLogLevel = 'info';
      const configured = this.definition?.default_source_dialect;
      this.sourceKind = this.command === 'fetch' ? (['postgres', 'oracle', 'mysql'].includes(configured) ? configured : 'postgres') : '';
      this.preview = null; this.wizardError = ''; this.prunedOptions = [];
    },
    resetRun(snapshot) {
      clearTimeout(this.timer);
      this.events = []; this.cursor = 0; this.truncated = false; this.outputCleared = false;
      this.expandedTable = ''; this.tableDetail = null; this.tableFilter = ''; this.tablePage = 1;
      this.applySnapshot(snapshot);
      this.selectedRecord = null;
      if (this.historyLoaded) this.refreshHistory();
    },
    async importFile(file) {
      if (!file || this.running || this.busy) return;
      this.busy = true; this.error = '';
      try {
        this.resetRun(await this.request('/api/log-imports', {
          method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file,
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
      const follow = panel && this.followOutput && !this.outputCollapsed;
      this.job = snapshot;
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
        const snapshot = await this.request(`/api/jobs/${jobId}?after=${this.cursor}`);
        if (this.job?.id !== jobId) return;
        this.applySnapshot(snapshot);
        if (!this.running && this.historyLoaded) await this.refreshHistory();
        const selected = this.aggregation.tables.find(table => table.name === this.expandedTable);
        if (selected && (!this.tableDetail || this.tableDetail.total !== selected.log_lines)) await this.loadTableLogs();
        this.error = snapshot.history_error || '';
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
        await this.request(`/api/jobs/${this.job.id}/stop`, {method: 'POST'});
        await this.poll();
      } catch (error) { this.error = error.message; }
    },
    formatEvent(event) {
      if (!event.data) return event.text;
      const { time = '', level, message = '', ...fields } = event.data;
      const details = Object.entries(fields).map(([key, value]) =>
        `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`).join(', ');
      const timestamp = typeof time === 'string' ? time.replace(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?Z$/, '$1 $2') : time;
      return [timestamp, message, details].filter(part => part !== '' && part != null).join(' ');
    },
  }));
});

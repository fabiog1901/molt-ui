document.addEventListener('alpine:init', () => {
  Alpine.data('cliApp', () => ({
    commands: [], command: 'fetch', values: {}, advanced: false,
    job: null, events: [], cursor: 0, error: '', busy: false,
    timer: null, polling: false, truncated: false,
    aggregation: {totals: {}, tables: []}, tableFilter: '', tablePage: 1,
    expandedTable: '', tableDetail: null, detailError: '', detailLoading: false,
    rawOutput: false,

    get definition() { return this.commands.find(item => item.id === this.command); },
    get running() { return this.job?.status === 'running'; },
    get totals() { return this.aggregation.totals; },
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
      try {
        this.commands = await this.request('/api/commands');
        const latest = await this.request('/api/jobs');
        if (latest) {
          if (this.$refs?.configuration) this.$refs.configuration.open = false;
          this.command = latest.command;
          this.applySnapshot(latest);
          if (this.running) this.schedulePoll();
        }
      }
      catch (error) { this.error = error.message; }
    },
    destroy() { clearTimeout(this.timer); },
    changeCommand() { this.values = {}; },
    resetRun(snapshot) {
      clearTimeout(this.timer);
      this.events = []; this.cursor = 0; this.truncated = false;
      this.expandedTable = ''; this.tableDetail = null; this.tableFilter = ''; this.tablePage = 1;
      this.applySnapshot(snapshot);
      if (this.$refs?.configuration) this.$refs.configuration.open = false;
    },
    async importFile(file) {
      if (!file || this.running || this.busy) return;
      this.busy = true; this.error = '';
      try {
        this.resetRun(await this.request('/api/log-imports', {
          method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file,
        }));
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
      } catch (error) { this.error = error.message; }
      finally { this.busy = false; }
    },
    options() {
      const result = {};
      for (const option of this.definition?.options || []) {
        const value = this.values[option.name];
        if (value !== undefined && value !== '') {
          result[option.name] = option.kind === 'bool' ? value === 'true' : String(value);
        }
      }
      return result;
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
      const follow = panel && panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
      this.job = snapshot;
      this.aggregation = snapshot.aggregation || {totals: {}, tables: []};
      this.truncated ||= snapshot.truncated || this.events.length + snapshot.events.length > 2000;
      this.events = [...this.events, ...snapshot.events].slice(-2000);
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
          body: JSON.stringify({command: this.command, options: this.options(), help_only: helpOnly}),
        });
        this.resetRun(snapshot);
        if (this.running) this.schedulePoll();
      } catch (error) { this.error = error.message; }
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
        const selected = this.aggregation.tables.find(table => table.name === this.expandedTable);
        if (selected && (!this.tableDetail || this.tableDetail.total !== selected.log_lines)) await this.loadTableLogs();
        this.error = '';
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
      if (!event.data) return `[${event.stream}] ${event.text}`;
      const { time = '', level = event.stream, message = '', ...fields } = event.data;
      return `${time} [${level}] ${message}${Object.keys(fields).length ? ' ' + JSON.stringify(fields) : ''}`;
    },
  }));
});

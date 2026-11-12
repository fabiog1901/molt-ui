# Molt UI

<img src="resources/media/logo.png" alt="Molt UI mascot" width="96" height="96">

A web and terminal interface for `molt`, the database migration tool for
CockroachDB. Configure migrations, follow progress, and inspect results from the
interface that suits your workflow.

## Features

- Run Molt commands through a web app or terminal UI.
- Configure commands with a guided, tabbed wizard.
- View live logs with per-table statistics and status.
- View live uPlot charts based on Molt's Grafana dashboard, with schema, table,
  and shard filters.
- Resize, minimize, or maximize the output pane.
- Save job history locally in SQLite.
- Review past jobs and reconstruct their table summaries.
- Re-run saved commands with editable settings.
- Import existing log files for review.
- Automatically update available options when Molt changes.

## Get started

You'll need **Python 3.14+**, **[pipx](https://pipx.pypa.io/stable/how-to/install-pipx.html)**,
**Git**, and the **`molt` executable**.

Install Molt UI directly from GitHub:

```sh
pipx install --python python3.14 git+https://github.com/fabiog1901/molt-ui.git
pipx ensurepath
```

Open a new terminal after `pipx ensurepath`. pipx installs the app in an isolated
environment and makes both `molt-web` and `molt-tui` available on your `PATH`.

Make the Go `molt` executable available on your `PATH`, or set its absolute path:

```sh
export MOLT_EXECUTABLE=/absolute/path/to/molt
```

Start the web app from your terminal:

```sh
molt-web
```

Open <http://127.0.0.1:8000>. Select **Configure command** to choose an operation,
enter your connections, and review the command before clicking **Run**. For a
quick tour without running a migration, select **Review logs → Load sample log**.

To use the terminal interface instead:

```sh
molt-tui
```

You can also open a saved log directly:

```sh
molt-tui --log /path/to/fetch.jsonl
```

On first launch, the app reads Molt's commands and stores their catalog in SQLite;
it refreshes the catalog when the Molt version changes. Job history is saved in
`.data/molt-ui.sqlite3` under the directory where you launch the app. Set
`MOLT_DATABASE` to an absolute path to share the same history across launches
from different directories.

Jobs that exit unsuccessfully are marked **failed**, with their exit code and
latest error diagnostic saved in history. On startup, unfinished jobs whose app
process is no longer running are marked **interrupted**, with an unknown outcome.
Recovery checks local process ownership on POSIX systems; jobs owned by another
host or an owner that cannot be checked are left unchanged.

Select **Charts** beside **Table progress** to view fetch or verify metrics.
The app collects Molt's Prometheus endpoint every two seconds, even when the
Charts view is closed, and saves the latest 1,800 samples (about 1 hour) per
job in SQLite. Saved jobs retain their charts across app restarts. Imported logs
and jobs run before metrics collection was added have no metric samples.

Charts cover the 22 data panels in `molt/grafana_dashboard.json`: fetch durations,
table and error counts, exported/imported rows and rates, five latency histograms
with p50/p75/p90/p99, and verify counts, duration, rows, and row statuses. The
bundled definitions retain the original queries for reference. Rates and histogram
percentiles are local estimates over observed samples, rather than exact PromQL
results. Missing metrics remain empty; some panels only apply to particular
migration modes. Collection is capped at 2,000 raw series, and each chart displays
up to 24 series at once; use filters to narrow larger inventories.

No Prometheus or Grafana server is required. The app uses the configured
`--metrics-listen-addr` (default `127.0.0.1:3030`), mapping wildcard listeners to
loopback when scraping. It defaults `--metrics-scrape-interval` to `2s` so Molt
keeps its final metrics available before exiting; an explicit value takes
precedence. uPlot 1.6.32 and its MIT license are bundled locally.

---

![Molt UI mascot carrying a database with a migration arrow](resources/media/splash.png)

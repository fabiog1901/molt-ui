# Molt UI

One Python core wrapping the Go `molt` CLI, with a Textual TUI and a FastAPI-served
Alpine.js SPA. Both interfaces use the same command catalog, argument validation,
process manager, and JSON log parser.

## Setup and launch

Requires Python 3.14+, Poetry, and `molt`.

```sh
poetry install
poetry run molt-tui
# Or:
poetry run molt-web
```

Open <http://127.0.0.1:8000> for the SPA; API documentation is at `/docs`.
For automatic web reload:

```sh
poetry run uvicorn molt_ui.frontends.api.app:create_app --factory --reload
```

Executable resolution: `MOLT_EXECUTABLE`, then `molt/molt` in this checkout, then
`molt` on PATH. The checkout binary is resolved independently of the working
directory. Platform-specific binaries are not included in the Python package.

```sh
export MOLT_EXECUTABLE=/absolute/path/to/molt
```

## Run commands

To preview logs without executing a command, start the web app and click **Load
sample log**, or choose a saved `.jsonl`/`.log` file under **Preview saved logs**.
The included sample is a condensed version of the supplied fetch output; it
preserves the 19 tables, 63,307 exported rows, and 19 warnings while omitting most
debug output. To preview the full original log, save it with one JSON object per
line and upload that file. The web upload limit is 256 MiB; uploads are processed
as a stream with bounded in-memory history.

In the TUI, enter the local file path and click **Import log**, or launch with:

```sh
poetry run molt-tui --log src/molt_ui/webapp/static/sample-fetch.jsonl
# For your own file:
poetry run molt-tui --log /path/to/fetch.jsonl
```

Imports replace the latest preview/run only when no command is active. They use
the same aggregation and retention as live runs, display status `imported`, and
do not establish a migration exit code. Importing never invokes molt. The file
is processed immediately; original timestamps are displayed but not replayed
with delays. Plain-text/non-JSON lines remain available in the console.

Choose **Fetch data**, **Verify data**, or schema conversion for PostgreSQL,
MySQL, or Oracle. In the web app, click **Configure command** to open the modal
wizard: Operation → Connections/Inputs → Common options → Advanced → Logging →
Metrics → Review.
Logging contains log level, destination, and console formatting. Levels use plain
names; a separate Disable logging checkbox sends `--logging=disabled` and restores
the previous level when unchecked. Metrics contains metrics endpoints, scraping,
telemetry, and profiling settings. Messages appear
above the tabs and remain visible while the parameter panel scrolls.
Long flag help is collapsed; advanced flags are searchable. The Review tab builds
the exact invocation without executing it. Click Run command to launch it.
The TUI retains its common/advanced form; hover over a field for its description.
The web wizard displays concrete defaults such as `data-load`, numeric limits,
and filter expressions. Boolean options use checkboxes, including checked
defaults such as verify's `--rows`. Untouched defaults are not emitted as extra
flags; unchecking a default-true option sends an explicit `false`. Unset options
and runtime-calculated values have descriptive placeholders. Required fields
have a red asterisk; inherited connection environment variables satisfy their
corresponding requirement. The TUI retains its default/yes/no boolean controls.
Command Help works without filling the form and does not run the operation.

Fetch's second tab includes PostgreSQL, Oracle, and MySQL source radio buttons.
The selection filters source-specific fields before a URI is entered. Changing
it clears the previous source connection and inapplicable values. The backend
validates this context too, including mismatches with a recognized source URI
scheme; the source selection itself is never emitted as a molt flag.

For a direct-copy fetch:

1. Open Configure command and select Fetch data.
2. Enter source and target connection strings, or set `MOLT_SOURCE` and
   `MOLT_TARGET` in the environment used to start the app.
3. Check Direct copy on the Operation tab to bypass staging (unchecked by default).
   For staged import, configure bucket/local storage
   instead, using the corresponding options.
4. Set table/schema filters and target table handling as needed.
5. Click Run command (TUI: Run or Ctrl+R).

The shared applicability rules clear options that no longer belong: staged
storage flags during direct copy, direct-copy during export/import-only modes,
Oracle and PostgreSQL flags for incompatible source URI schemes, and DDL capture
flags unless dropping/recreating target tables. Unknown source schemes retain
source-specific options. The backend applies the same rules before launching;
molt still performs its own full compatibility checks.

Run starts the real operation immediately. Stop terminates the process and,
where supported, its process group; it does not roll back database changes.
Standard input is closed. If the operation requires automatic prompt handling,
explicitly choose Non-interactive = Yes after reading the flag's description.
It can allow actions such as clearing exception data; it is never enabled
implicitly. Operation-specific validation and compatibility checks are also
performed by molt, with errors appearing in the output pane.

Fetch/verify preserve molt's default generated `fetch-{datetime}.log` or
`verify-{datetime}.log` file. Leave Log file blank to use this default, enter a
path to choose a file, or enter `stdout` for stdout-only logging. The UI displays
whatever the process emits on stdout/stderr. Schema
conversion defaults to `--out=-` and `--url=`: print converted SQL and skip
database evaluation unless an evaluation URL is provided. File paths refer to
the machine running the backend/TUI, not the browser.

## Live runs

The shared process manager permits one active run per app process. It streams
stdout and stderr concurrently, parsing newline-delimited JSON while retaining
plain text. Output includes timestamps, levels, messages, and extra fields.
Completion shows success/failure and the actual exit code. There is no fixed
migration timeout. Stop sends termination, escalating to a kill after two
seconds if necessary; app shutdown also stops an active run.

Only the latest run and the latest 2,000 output entries are retained in memory.
Entries are bounded to 16,384 characters; larger lines are displayed as chunks.
The web UI polls incremental updates, reconnects after temporary network errors,
and restores the latest run after refresh. Closing a browser tab leaves the
backend operation running; closing the TUI or stopping the web server stops it.
UI log buffers are not a durable audit trail; molt's generated or explicitly
configured log files are separate. Independent TUI/web processes manage
independent runs.

## Aggregated progress

The web view shows run totals and a filterable table with exported/imported rows,
errors, warnings, log-entry counts, and status. Expand a row for recent table logs;
the scrolling console remains available below, including a raw JSON option.
The TUI offers Tables and Output tabs; select a table with Enter for its recent
logs. The web table renders at most 50 rows per page.

Aggregation happens once in the shared core before console eviction. Counts cover
the full run even after old logs disappear. A separate, global buffer retains up
to 2,000 table-attributed entries; table details return the latest 50 available
entries on demand. Retention is bounded across all tables, rather than allocating
a log buffer per table. Counters and table metadata grow only with table count.

Table identity comes from `table`, `source_table`/`target_table`, or recognized
messages that explicitly name a table (fetch start, truncation, COPY, and sharding
warnings). Unlabelled shard/batch logs and global warnings remain unassigned;
concurrent workers are never used to guess a table. Global warnings/errors still
contribute to run totals. Ignored tables are counted as skipped.

Export row totals use `num_rows` on extraction-completion records; import totals
use the corresponding import-completion record. Explicit `rows_exported` and
`rows_imported` counters are also supported. Per-table counts are cumulative high
watermarks, so repeated summaries do not add rows twice. Unknown counts show an
em dash; zero is displayed only when reported. Export completion does not imply
an import count, including direct-copy runs. Run totals sum only reported counts.

## Local run metadata

SQLite stores command records at `.data/molt-ui.sqlite3` relative to the app's
working directory. Set `MOLT_DATABASE` to choose another path. The default data
directory is ignored by Git. New database files are created with owner-only
permissions.

Records include the exact executable/argv, relevant connection environment
values, normalized options, shell-quoted invocation, start/end timestamps,
status, exit code, launch error, and final aggregate totals. Connection strings
and credentials are stored verbatim, as requested. The visible command record
does not change when you edit a new configuration. **Saved run history** restores
records after an app restart; Copy command copies the exact saved invocation.
Imported logs have metadata records with no fabricated command or exit code.

Metadata is committed before a command launches and updated on completion even
when no UI is polling. History retains the last recorded status after an abrupt
process crash; it cannot establish whether external database work finished.
Raw logs and per-table detail buffers remain in memory and are not persisted.

## Architecture

- `core/models.py`: shared Pydantic output and aggregation models.
- `core/service.py`: `MoltService`, the application interface used by both frontends.
- `core/catalog.py`: option metadata captured from the bundled binary's help.
- `core/commands.py`: resolve a single command plan for preview, execution, and history.
- `core/wizard.py`: shared applicability rules and wizard option metadata.
- `core/runs.py`: in-memory run lifecycle and bounded output; no subprocess or SQLite calls.
- `core/logs.py`: JSON-line parsing shared by live processes and imported files.
- `core/aggregation.py`: full-run counters, table progress, and bounded table-log details.
- `molt_process.py`: `MoltProcess` and its process handles own launching, streaming, timeouts, and termination.
- `repo/repo.py`: `Repo` owns all SQLite access, command records, and final summaries.
- `config.py`: executable and database configuration.
- `bootstrap.py`: constructs the service, process adapter, and repository.
- `frontends/models.py`: shared Pydantic request and command-field models.
- `frontends/tui/`: Textual controls and log presentation.
- `frontends/api/`: FastAPI command catalog, start/status/stop endpoints, and static assets.
- `webapp/`: packaged build-free HTML, CSS, and Alpine.js.

Both frontend adapters consume the same validated command-field models. Shared
process output and aggregation types live in `core/models.py`; the core does not
import frontend modules. Models use Pydantic rather than dataclasses. Static
assets are resolved through package resources rather than the API directory's
depth, so frontend directory changes and installed wheels use the same paths.

Frontends call `MoltService` for previews, starting/stopping runs, snapshots,
imports, table logs, and history. They receive Pydantic data models and never
access a process handle or repository directly. Process output flows back into
the in-memory run aggregator. Completion updates storage outside the run's log
lock, including when no frontend is polling. Imported logs use the same state
and aggregation without creating a process. SQLite retains the existing schema
and exact saved values; this directory refactor requires no database migration.

Arguments are passed directly without a shell. Source, target, and source-CDB
connection strings are passed through child environment variables instead of
argv. The command API accepts only catalogued commands and flags. The server is
for local use, binds to loopback, and should use one worker: job state is local
to its process. Authentication and remote/multi-user operation are outside this
scaffold. Alpine.js is pinned and loaded from a CDN.

After upgrading the binary, regenerate and review its option catalog:

```sh
poetry run python scripts/update_command_catalog.py
```

## Verify

```sh
poetry run pytest
node --test tests/test_web.js
poetry build
```

Automated tests use controlled Python subprocesses and injected services; they
never run migrations or connect to databases. Real-binary smoke checks use help
only.

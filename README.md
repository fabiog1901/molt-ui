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

Open http://127.0.0.1:8000 for the SPA; API documentation is at `/docs`.
For automatic web reload:

```sh
poetry run uvicorn molt_ui.api.app:create_app --factory --reload
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
poetry run molt-tui --log src/molt_ui/web/static/sample-fetch.jsonl
# For your own file:
poetry run molt-tui --log /path/to/fetch.jsonl
```

Imports replace the latest preview/run only when no command is active. They use
the same aggregation and retention as live runs, display status `imported`, and
do not establish a migration exit code. Importing never invokes molt. The file
is processed immediately; original timestamps are displayed but not replayed
with delays. Plain-text/non-JSON lines remain available in the console.

Choose **Fetch data**, **Verify data**, or schema conversion for PostgreSQL,
MySQL, or Oracle. Common fields appear first; advanced options expose the rest
of the bundled binary's flags. Hover over a TUI field for its description.
Blank fields preserve CLI defaults; boolean fields offer default/yes/no so flags
with a default of true can also be disabled. Command Help works without filling
the form and does not run the operation.

For a direct-copy fetch:

1. Select Fetch data.
2. Enter source and target connection strings, or set `MOLT_SOURCE` and
   `MOLT_TARGET` in the environment used to start the app.
3. Set Direct copy to Yes. For staged import, configure bucket/local storage
   instead, using the corresponding options.
4. Set table/schema filters and target table handling as needed.
5. Click Run command (TUI: Run or Ctrl+R).

Run starts the real operation immediately. Stop terminates the process and,
where supported, its process group; it does not roll back database changes.
Standard input is closed. If the operation requires automatic prompt handling,
explicitly choose Non-interactive = Yes after reading the flag's description.
It can allow actions such as clearing exception data; it is never enabled
implicitly. Operation-specific validation and compatibility checks are also
performed by molt, with errors appearing in the output pane.

Fetch/verify log output defaults to `--log-file=stdout` for live display. Schema
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
Logs are not a durable audit trail. Use molt's log-file option if durable logs
are required. Independent TUI/web processes manage independent runs.

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

## Architecture

- `core/catalog.py`: option metadata captured from the bundled binary's help.
- `core/commands.py`: shared validation and argument/environment construction.
- `core/jobs.py`: process lifecycle, bounded live output, and stop behavior.
- `core/aggregation.py`: full-run counters, table progress, and bounded table-log details.
- `core/cli.py`: service wiring and the original synchronous help adapter.
- `tui/`: Textual controls and log presentation.
- `api/`: FastAPI command catalog, start/status/stop endpoints, and static assets.
- `web/`: build-free HTML, CSS, and Alpine.js.

Arguments are passed directly without a shell. Source, target, and source-CDB
connection strings are passed through child environment variables instead of
argv. The command API accepts only catalogued commands and flags. The server is
for local use, binds to loopback, and should use one worker: job state is local
to its process. Authentication and remote/multi-user operation are outside this
scaffold. Alpine.js is pinned and loaded from a CDN.

After upgrading the binary, regenerate and review its option catalog:

```sh
python3 scripts/update_command_catalog.py
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

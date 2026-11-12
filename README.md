# Molt UI

<img src="resources/media/logo.png" alt="Molt UI mascot" width="96" height="96">

A web and terminal interface for `molt`, the database migration tool for
CockroachDB. Configure migrations, follow progress, and inspect results from the
interface that suits your workflow.

## Features

- Run Molt commands through a web app or terminal UI.
- Configure commands with a guided, tabbed wizard.
- View live logs with per-table statistics and status.
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

---

![Molt UI mascot carrying a database with a migration arrow](resources/media/splash.png)

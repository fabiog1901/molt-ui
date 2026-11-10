# Molt UI

<img src="resources/media/logo.png" alt="Molt UI mascot" width="96" height="96">

A web and terminal interface for `molt`, the database migration tool for
CockroachDB. Configure migrations, follow progress, and inspect results from the
interface that suits your workflow.

## What you can do

- **Configure commands with guidance.** Run fetch, verification, and schema
  conversion with a wizard that shows relevant options for your source database.
- **See progress clearly.** Follow live output alongside table-level row counts,
  errors, warnings, and skipped tables.
- **Keep a record.** Review the exact command before running it and revisit saved
  commands and results afterward.
- **Explore existing logs.** Import a saved log or load the included sample to
  try the interface without running a migration.

## Get started

You'll need **Python 3.14+**, **Poetry**, and the **`molt` executable**.
Place the executable at `molt/molt` in this checkout or make it available on your
`PATH`. To use another location, set `MOLT_EXECUTABLE` to its path.

From the project directory, install the app:

```sh
poetry install
```

Start the web app:

```sh
poetry run molt-web
```

Open <http://127.0.0.1:8000>. Click **Load sample log** for a quick tour, or
**Configure command** to choose an operation, enter your connections, and review
the command before clicking **Run**.

To use the terminal interface instead:

```sh
poetry run molt-tui
```

You can also open a saved log directly:

```sh
poetry run molt-tui --log /path/to/fetch.jsonl
```

![Molt UI mascot carrying a database with a migration arrow](resources/media/splash.png)

BEGIN;

CREATE TABLE IF NOT EXISTS runs (
    id TIMESTAMP PRIMARY KEY NOT NULL,
    command TEXT NOT NULL,
    origin TEXT NOT NULL,
    invocation TEXT,
    argv TEXT NOT NULL,
    environment TEXT NOT NULL,
    options TEXT NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,
    returncode INTEGER,
    summary TEXT,
    error TEXT,
    log_file TEXT,
    owner_pid INTEGER,
    owner_host TEXT
);

CREATE TABLE IF NOT EXISTS run_output (
    run_id TIMESTAMP NOT NULL REFERENCES runs(id) ON UPDATE CASCADE ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    stream TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS run_metrics_state (
    run_id TIMESTAMP PRIMARY KEY NOT NULL REFERENCES runs(id) ON UPDATE CASCADE ON DELETE CASCADE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TIMESTAMP NOT NULL REFERENCES runs(id) ON UPDATE CASCADE ON DELETE CASCADE,
    timestamp REAL NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, timestamp)
);

CREATE TABLE IF NOT EXISTS command_catalog (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version TEXT NOT NULL,
    payload TEXT NOT NULL,
    generated_at TIMESTAMP NOT NULL
);

COMMIT;

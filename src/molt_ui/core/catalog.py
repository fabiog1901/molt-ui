"""Command metadata captured from the bundled molt binary help.

Regenerate deliberately when upgrading molt; both UIs consume this catalog.
"""

COMMANDS = [
    {
        "id": "fetch",
        "label": "Fetch data",
        "arguments": ["fetch"],
        "options": [
            {
                "name": "source",
                "kind": "string",
                "description": "Connection string of the source database. May also be supplied via "
                "the MOLT_SOURCE environment variable; the flag takes precedence.",
                "advanced": False,
                "secret": True,
                "default": "",
            },
            {
                "name": "target",
                "kind": "string",
                "description": "Connection string of the target database. May also be supplied via "
                "the MOLT_TARGET environment variable; the flag takes precedence.",
                "advanced": False,
                "secret": True,
                "default": "",
            },
            {
                "name": "bucket-path",
                "kind": "string",
                "description": "Path of the s3/gcp/azure bucket where intermediate files are "
                "written (e.g., azure-blob://container/path, s3://bucket/path, or "
                "gs://bucket/path).",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "direct-copy",
                "kind": "bool",
                "description": "Enables direct copy mode, which copies data directly from source to "
                "target without using an intermediate store.",
                "advanced": False,
                "secret": False,
                "default": False,
            },
            {
                "name": "mode",
                "kind": "string",
                "description": "Mode type for fetch (data-load/export-only/import-only). (default "
                "data-load) (default <unknown>)",
                "advanced": False,
                "secret": False,
                "default": "data-load",
            },
            {
                "name": "non-interactive",
                "kind": "bool",
                "description": "If set, automatically skips all user prompting and initiates "
                "actions such as clearing exception log data (preferable if running "
                "in CI) or as an automated job. If not set, prompts user for "
                "confirmation before performing actions.",
                "advanced": False,
                "secret": False,
                "default": False,
            },
            {
                "name": "schema-filter",
                "kind": "string",
                "description": "POSIX regexp filter for schemas to action on. For Oracle sources, "
                "the schema name is the table's owner — use this flag to filter by "
                'Oracle owner (no separate --owner-filter exists). (default ".*")',
                "advanced": False,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "table-filter",
                "kind": "string",
                "description": 'POSIX regexp filter for tables to action on. (default ".*")',
                "advanced": False,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "table-handling",
                "kind": "string",
                "description": "the way to handle the table initialization on the target database: "
                '"none"(default), "drop-on-target-and-recreate" or '
                '"truncate-if-exists". Pair with --dropped-constraints-file under '
                '"drop-on-target-and-recreate" to capture the non-PK constraints '
                "fetch strips so they can be reapplied after the data load. (default "
                '"none")',
                "advanced": False,
                "secret": False,
                "default": "none",
            },
            {
                "name": "allow-tls-mode-disable",
                "kind": "bool",
                "description": "Allows insecure connection to databases. Secure SSL/TLS connections "
                "should be used by default.  Enable this flag only if you cannot "
                "access the source or target database via secure SSL/TLS.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "assume-role",
                "kind": "string",
                "description": "Assume role for cloud storage authentication. For S3, this accepts "
                "CockroachDB's ASSUME_ROLE syntax: '<role>[;external_id=<id>]', "
                "comma-separated for a chained assume. See "
                "https://www.cockroachlabs.com/docs/stable/cloud-storage-authentication "
                "for more details.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "case-sensitive",
                "kind": "bool",
                "description": "If true, schema, table, and column names are compared "
                "case-sensitively between source and target.  If false, we strip the "
                "surrounding quotes from these names and compare them "
                "case-insensitively.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "changefeeds-path",
                "kind": "string",
                "description": "The path to a json file that specifies overrides for the "
                "changefeeds setup command. Only applicable when running failback "
                "mode.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "cleanup",
                "kind": "bool",
                "description": "Whether any created resources should be deleted. Ignored if in "
                "direct-copy mode.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "compression",
                "kind": "string",
                "description": "Compression type for IMPORT INTO mode (gzip/none). (default gzip) "
                "(default <unknown>)",
                "advanced": True,
                "secret": False,
                "default": "gzip",
            },
            {
                "name": "continuation-file-name",
                "kind": "string",
                "description": "If set, restarts the fetch process for at the given file name "
                "instead of the recorded file in the exceptions table",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "continuation-token",
                "kind": "string",
                "description": "If set, restarts the fetch process for the given continuation token "
                "for a specific table",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "crdb-pts-duration",
                "kind": "string",
                "description": "The lifetime of a protected timestamp extension (default 24h0m0s)",
                "advanced": True,
                "secret": False,
                "default": "24h0m0s",
            },
            {
                "name": "crdb-pts-refresh-interval",
                "kind": "string",
                "description": "Duration for the ticker to wait for the next protected timestamp "
                "extension. The new expiration timestamp of the protected timestamp "
                "will be {time when extension happens} + {crdb-pts-duration} "
                "(default 10m0s)",
                "advanced": True,
                "secret": False,
                "default": "10m0s",
            },
            {
                "name": "dropped-constraints-file",
                "kind": "string",
                "description": "The path of a SQL file to which fetch will write re-applicable "
                "ALTER TABLE … ADD … statements for every non-PK constraint (CHECK, "
                "UNIQUE, FOREIGN KEY, EXCLUDE, trigger constraint) that "
                "--table-handling=drop-on-target-and-recreate stripped from the "
                "source schema. Apply the file against the target after the data "
                "load completes (e.g. psql <target> -f dropped-constraints.sql) to "
                "restore the dropped constraints. Requires "
                "--table-handling=drop-on-target-and-recreate and is incompatible "
                "with --fetch-id (which skips schema creation); an error is returned "
                "otherwise.  The captured DDL uses SOURCE schema, table, and column "
                "identifiers. If --transformations-file renamed any tables, schemas, "
                "or columns, the file must be edited by the operator before it is "
                "applied against the target.  Source-syntax compatibility: the "
                "captured ALTER TABLE statements use source-dialect syntax verbatim. "
                "CockroachDB does NOT accept the following constructs that may "
                "appear in the file and the operator must edit them before applying: "
                '- PostgreSQL 15+ "ON DELETE SET NULL (col)" / "ON DELETE SET '
                'DEFAULT (col)" column-list clauses (strip the trailing column '
                "list). - MySQL backtick-quoted identifiers (replace each backtick "
                "with a double-quote, or remove the backticks if the identifier is "
                'simple enough not to need quoting). - PostgreSQL "ON DELETE SET '
                'NULL" / "ON DELETE SET DEFAULT" applied to FOREIGN KEY columns that '
                "map to NOT NULL columns on the target (CockroachDB rejects this; "
                "the operator must either change the action to CASCADE / NO ACTION "
                "or drop the NOT NULL constraint on the target columns first). ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "dropped-indexes-file",
                "kind": "string",
                "description": "The path of a SQL file to which fetch will write the CREATE "
                "[UNIQUE] INDEX statements for every non-PK, non-constraint-backed "
                "secondary index that --table-handling=drop-on-target-and-recreate "
                "stripped from the source schema. Apply the file against the target "
                "after the data load completes (e.g. psql <target> -f "
                "dropped-indexes.sql) to restore the indexes; doing so out-of-band "
                "keeps the bulk load on the IMPORT INTO fast path. Requires "
                "--table-handling=drop-on-target-and-recreate and is incompatible "
                "with --fetch-id (which skips schema creation); an error is returned "
                'otherwise.  Scope. The captured set is "secondary indexes" — '
                "non-PRIMARY KEY and not the implicit index that backs a UNIQUE / "
                "EXCLUDE / PRIMARY KEY constraint. UNIQUE constraints (and their "
                "backing unique indexes) are emitted by --dropped-constraints-file, "
                "so the two output files are complementary and emit no overlapping "
                "DDL. PostgreSQL partial indexes, expression indexes, and the GIN / "
                "GIST / BRIN / HASH access methods are preserved verbatim by "
                "pg_get_indexdef. MySQL secondary KEY declarations are rewritten "
                "into portable CREATE INDEX statements scoped to the source "
                "schema.table.  The captured DDL uses SOURCE schema, table, and "
                "column identifiers. If --transformations-file renamed any tables, "
                "schemas, or columns, the file must be edited by the operator before "
                "it is applied against the target.  Source-syntax compatibility: the "
                "captured CREATE INDEX statements use source-dialect syntax "
                "verbatim. CockroachDB does NOT accept the following constructs that "
                "may appear in the file and the operator must edit them before "
                'applying: - PostgreSQL "USING brin" / "USING hash" access methods '
                "(drop the USING clause, or fall back to a regular BTREE index on "
                'the same columns). - PostgreSQL "INCLUDE (col, ...)" covering-index '
                'clauses (CockroachDB uses a different "STORING (col, ...)" syntax; '
                "rewrite by hand). - PostgreSQL expression indexes referencing "
                "PostgreSQL-only functions or operator classes; rewrite the "
                "expression to a CockroachDB-supported equivalent or drop the index. "
                '- MySQL prefix-length indexes "(col(N))" (CockroachDB does not '
                "support per-index prefix lengths on string columns; strip the (N) "
                "or model differently).  MySQL FULLTEXT and SPATIAL indexes are NOT "
                "captured by this flag — CockroachDB has no direct equivalent and "
                "the captured DDL would not apply. Operators using these must "
                "reconstruct the indexes from the source schema by hand (e.g. by "
                "inspecting the source SHOW CREATE TABLE output and modelling the "
                "search differently on the target). ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "export-concurrency",
                "kind": "int",
                "description": "Number of threads to use for data export. (default 4)",
                "advanced": True,
                "secret": False,
                "default": "4",
            },
            {
                "name": "export-retry-max-attempts",
                "kind": "int",
                "description": "Maximum number of retry attempts for source export queries when "
                "connection failures occur (limited to Postgres and CockroachDB) "
                "(default 3)",
                "advanced": True,
                "secret": False,
                "default": "3",
            },
            {
                "name": "export-retry-max-duration",
                "kind": "string",
                "description": "Maximum total duration for retrying source export queries. If 0, no "
                "time limit is enforced (limited to Postgres and CockroachDB) "
                "(default 5m0s)",
                "advanced": True,
                "secret": False,
                "default": "5m0s",
            },
            {
                "name": "export-statement-timeout",
                "kind": "string",
                "description": "Timeout limit for SQL statements used during data export. (default "
                "1h0m0s)",
                "advanced": True,
                "secret": False,
                "default": "1h0m0s",
            },
            {
                "name": "fail-on-no-tables",
                "kind": "bool",
                "description": "If set, fetch exits with an error instead of exiting successfully "
                "when table verification leaves zero tables to process. Use this to "
                "catch a misconfigured run — a --table-filter or --schema-filter "
                "that matches nothing, or tables missing on the target — that would "
                "otherwise report success while migrating no data. Default false "
                'keeps the graceful "nothing to do" exit for scripted no-op '
                "invocations.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "fetch-id",
                "kind": "string",
                "description": "If set, restarts the fetch process for all failed tables of the "
                "given ID",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "filter-path",
                "kind": "string",
                "description": "The file path to filter expressions for exporting only a subset of "
                "the source data",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "flatten-partitioned-tables",
                "kind": "bool",
                "description": "PostgreSQL sources only. When set, discovery enumerates each "
                "declaratively partitioned table exactly once at its root and loads "
                "the whole tree into a single flat target; the declarative partition "
                "leaves are invisible to both discovery and --table-filter, so a "
                "--table-filter matching only leaf names selects zero tables (pair "
                "with --fail-on-no-tables to surface that as an error). Legacy "
                "INHERITS tables are unaffected — their behavior is byte-identical "
                "with or without this flag. When a partitioned tree is discovered "
                "and PostgreSQL logical-replication setup is requested "
                "(--pglogical-replication-slot-name), the source must be PostgreSQL "
                "13 or later: with "
                "--pglogical-publication-and-slot-drop-and-recreate the publication "
                "is created WITH (publish_via_partition_root = true), so changes to "
                "every leaf are published under the root; otherwise the existing "
                "publication must have publish_via_partition_root enabled and "
                "include each flattened root. A TRUNCATE of a single partition is "
                "not published under publish_via_partition_root, and PostgreSQL "
                "never replicates DETACH PARTITION or DROP TABLE, so rows removed "
                "that way stay on the flattened target; delete them yourself. Rows "
                "already in a table that is attached as a partition after the "
                "replication slot was created are never replicated, and no error is "
                "raised; copy them yourself. molt verify reports both. Opt-in; "
                "default false keeps the historical per-leaf workflow. No effect on "
                "non-PostgreSQL sources, and a no-op on CockroachDB sources "
                "(CockroachDB partitions are not separate catalog relations, so "
                "there is nothing to flatten).",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "flush-rows",
                "kind": "int",
                "description": "If set, number of rows before the source data is flushed to "
                "intermediate files.",
                "advanced": True,
                "secret": False,
                "default": "0",
            },
            {
                "name": "flush-size",
                "kind": "int",
                "description": "If set, size (in bytes) before the source data is flushed to "
                "intermediate files.",
                "advanced": True,
                "secret": False,
                "default": "0",
            },
            {
                "name": "ignore-replication-check",
                "kind": "bool",
                "description": "For MySQL, PostgreSQL, and Oracle. If set, MOLT will skip querying "
                "for replication checkpoints like pg_current_wal_insert_lsn() on "
                "PostgreSQL, gtid_executed on MySQL, and CURRENT_SCN on Oracle. "
                "Intended for use in non-replication modes with planned application "
                "downtime, or testing. This avoids setting up replication-specific "
                "configurations such as GTID-based replication in MySQL, logical "
                "replication in PostgreSQL, and permissions on V$DATABASE, "
                "V$SESSION, and V$TRANSACTION for Oracle. Setting this flag also "
                "skips the Oracle redo-log / archive-log retention preflight "
                "performed at fetch startup.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "import-assume-role",
                "kind": "string",
                "description": "Role chain CockroachDB assumes to read the bucket during IMPORT "
                "INTO, in CockroachDB's ASSUME_ROLE syntax "
                "('<role>[;external_id=<id>]', comma-separated for chained roles). "
                "Defaults to --assume-role. S3 only; requires --use-implicit-auth.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "import-batch-size",
                "kind": "int",
                "description": "The number of files in a batch to be imported in one IMPORT JOB to "
                "the target side. Will only take effect if using the import mode for "
                "ingesting data into the target. (default 1000)",
                "advanced": True,
                "secret": False,
                "default": "1000",
            },
            {
                "name": "import-region",
                "kind": "string",
                "description": "Explicitly specify the region of the cloud storage bucket when "
                "using IMPORT INTO for data movement. This applies to AWS_REGION "
                "only.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "local-path",
                "kind": "string",
                "description": "Path to upload files to locally.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "local-path-crdb-access-addr",
                "kind": "string",
                "description": "Address of data that CockroachDB can access to import from a local "
                "store (defaults to local-path-listen-addr).",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "local-path-listen-addr",
                "kind": "string",
                "description": "Address of a local store server to listen to for traffic.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "log-file",
                "kind": "string",
                "description": "By default, writes to a file named fetch-{datetime}.log. If set as "
                '"stdout", writes will only go to stdout',
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "logging",
                "kind": "string",
                "description": 'Level to log at (maps to zerolog.Level). (default "info")',
                "advanced": True,
                "secret": False,
                "default": "info",
            },
            {
                "name": "metrics-listen-addr",
                "kind": "string",
                "description": "Address for the metrics endpoint to listen to. (default "
                '"127.0.0.1:3030")',
                "advanced": True,
                "secret": False,
                "default": "127.0.0.1:3030",
            },
            {
                "name": "metrics-scrape-interval",
                "kind": "string",
                "description": "Scrape interval of your prometheus source. Allows for metrics to be "
                "scraped before exiting.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "opt-out-telemetry",
                "kind": "bool",
                "description": "Suppress MOLT telemetry-event emission. Telemetry is on by default; "
                "pass this flag to opt out.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "oracle-application-users",
                "kind": "string",
                "description": "Optional comma-separated list of Oracle usernames to filter active "
                "transactions when computing the replication backfill SCN, e.g. "
                "--oracle-application-users=user1,user2. When unset, MOLT "
                "auto-discovers application users by joining ALL_USERS WHERE "
                "ORACLE_MAINTAINED='N' (requires Oracle 12.1+ and SELECT on "
                "ALL_USERS, both standard). On Oracle 11g, or when stricter "
                "filtering is desired, set this flag explicitly. Include every user "
                "that may have an in-flight transaction at cutover, including users "
                "that DML against tables they do not own.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "oracle-narrow-snapshot-scn-by-table-touch",
                "kind": "bool",
                "description": "Optional. When set, filters the active-transaction SCN scan to only "
                "those active Oracle transactions that hold a table-modification "
                "lock (V$LOCK type='TM') on a table owned by a migrating schema. "
                "Tightens the replicationBackfillSCN bound at the cost of two extra "
                "catalog joins (V$LOCK and ALL_OBJECTS) at fetch start. Requires "
                "SELECT on V$LOCK and ALL_OBJECTS (both granted to PUBLIC by "
                "default; may need explicit grant on hardened catalogs). Do not "
                "enable for parallel-DML workloads (TM locks are held by parallel "
                "slave sessions, not the query coordinator; the filter may "
                "over-narrow). Default false; behavior unchanged when omitted.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "oracle-tablespace-filter",
                "kind": "string",
                "description": "POSIX regexp filter for the Oracle tablespace name. Only applied to "
                "Oracle sources; ignored (with a warning) for other dialects. "
                '(default ".*")',
                "advanced": True,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "pglogical-publication-and-slot-drop-and-recreate",
                "kind": "bool",
                "description": "If set, drops the publication and slots if they exist and then "
                "recreates them. Used in the replication-only mode.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "pglogical-publication-name",
                "kind": "string",
                "description": "If set, the name of the publication that will be created or used. "
                '(default "molt_fetch")',
                "advanced": True,
                "secret": False,
                "default": "molt_fetch",
            },
            {
                "name": "pglogical-replication-slot-name",
                "kind": "string",
                "description": "If set, the name of a replication slot that will be created before "
                "taking a snapshot of data.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "pglogical-replication-slot-plugin",
                "kind": "string",
                "description": "If set, the output plugin used for logical replication under "
                'pglogical-replication-slot-name. (default "pgoutput")',
                "advanced": True,
                "secret": False,
                "default": "pgoutput",
            },
            {
                "name": "pprof-listen-addr",
                "kind": "string",
                "description": "Address for the pprof endpoint to listen to. (default "
                '"127.0.0.1:3031")',
                "advanced": True,
                "secret": False,
                "default": "127.0.0.1:3031",
            },
            {
                "name": "require-empty-target",
                "kind": "bool",
                "description": "If set, fetch aborts before writing any data when any in-scope "
                "target table contains rows. Use as a non-destructive pre-flight "
                "check when TRUNCATE rights are unavailable or when investigating "
                "stale state from a prior interrupted run. Mutually exclusive with "
                "--table-handling=truncate-if-exists, "
                "--table-handling=drop-on-target-and-recreate, --fetch-id, "
                "--continuation-token, and --mode=export-only.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "row-batch-size",
                "kind": "int",
                "description": "Number of rows to select at a time for export from the source "
                "database. (default 100000)",
                "advanced": True,
                "secret": False,
                "default": "100000",
            },
            {
                "name": "skip-pk-check",
                "kind": "bool",
                "description": "Whether to skip the primary key check for the source and target "
                "tables. You need to set this to true to allow data movement for "
                "table with no primary key. If true, all tables will be considered "
                "as without a primary key, and will be exported in one batch, i.e. "
                "export-concurrency and row-batch-size settings will be ignored.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "skip-sequence-sync",
                "kind": "bool",
                "description": "Skip advancing target sequences past the extreme loaded value (max "
                "for ascending, min for descending sequences) after the data load. "
                "By default, sequences backing loaded columns are advanced so the "
                "first post-migration INSERT drawing nextval does not collide with a "
                "loaded row.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "source-cdb",
                "kind": "string",
                "description": "Optional connection string of the source CDB database for an Oracle "
                "database set up using a multi-tenant (CDB) architecture. May also "
                "be supplied via the MOLT_SOURCE_CDB environment variable; the flag "
                "takes precedence.",
                "advanced": True,
                "secret": True,
                "default": "",
            },
            {
                "name": "source-oracle-wallet-location",
                "kind": "string",
                "description": "Path to the Oracle wallet / config directory (godror configDir) "
                "used to locate cwallet.sso, sqlnet.ora, and tnsnames.ora when the "
                "source is an Oracle endpoint configured for SSL/TLS via an Oracle "
                "wallet. Equivalent to embedding 'configDir=<path>' as a query "
                "parameter on --source; if both are supplied, the values must match. "
                "Password-protected wallets are not supported by the underlying "
                "godror driver — configure the wallet password via sqlnet.ora in the "
                "same directory.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "table-concurrency",
                "kind": "int",
                "description": "Number of tables to move at a time. (default 4)",
                "advanced": True,
                "secret": False,
                "default": "4",
            },
            {
                "name": "table-exclusion-filter",
                "kind": "string",
                "description": 'POSIX regexp filter for tables to exclude. (default ".*")',
                "advanced": True,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "transformations-file",
                "kind": "string",
                "description": "The path to a json file that specifies transformations that should "
                "be applied to the relevant tables or columns before the data is "
                "fully migrated to the target. These include column exclusions and "
                "table aliases. ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "type-map-file",
                "kind": "string",
                "description": "The path to a json file that add to or override specified type "
                "mapping from the source dialect to CockroachDB for given column. It "
                "is consulted for automatic schema recreation "
                "(--table-handling=drop-on-target-and-recreate) and, in every "
                "table-handling mode, by the pre-load column-mismatch check: a "
                "column whose source and target types are not directly comparable is "
                "accepted (rather than aborting the load) when the file carries an "
                "entry for that table and column whose source_type and crdb_type "
                "also match the actual source and target column types; a "
                "non-matching entry is ignored with a WARN and the mismatch still "
                "aborts the load. Because a matching entry waives that check, a "
                "mapping between value-incompatible types (e.g. bool source to inet "
                "target) passes the check and instead fails later during data export "
                'with a conversion error; the earlier "waived by --type-map-file" '
                'log line is the breadcrumb. If a rule has specified column "*", all '
                "columns with matching source type will apply this mapping rule, "
                "unless specifically specified. Oracle NUMBER columns can be "
                "overridden to INT2, INT4, INT8, FLOAT4, or FLOAT8. See "
                "https://www.cockroachlabs.com/docs/molt/molt-fetch#type-mapping for "
                "more details. ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "use-console-writer",
                "kind": "bool",
                "description": "Use the console writer, which has cleaner log output but introduces "
                "more latency (defaults to false, which logs as structured JSON).",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "use-copy",
                "kind": "bool",
                "description": "Use COPY FROM instead of `IMPORT INTO` during the data movement "
                "phase. This keeps your table online during the process.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "use-implicit-auth",
                "kind": "bool",
                "description": "Whether implicit auth is used for cloud storage import URIs. See "
                "https://www.cockroachlabs.com/docs/stable/cloud-storage-authentication "
                "for more details. Note: MOLT disables AWS IMDS-based credential "
                "lookup by default to avoid multi-minute hangs on non-AWS hosts; set "
                "AWS_EC2_METADATA_DISABLED=false to re-enable IMDS on EC2.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "use-stats-based-sharding",
                "kind": "bool",
                "description": "Enable statistics-based sharding to balance data distribution "
                "across export shards. Supports primary keys of any data type "
                "(unlike the default range-based sharding). Enabled by default for "
                "PostgreSQL sources; pass --use-stats-based-sharding=false to opt "
                "out. Has no effect on non-PostgreSQL sources. Stats-based sharding "
                "requires PostgreSQL 11+. Before using, run ANALYZE on source tables "
                "to ensure up-to-date statistics.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
        ],
    },
    {
        "id": "verify",
        "label": "Verify data",
        "arguments": ["verify"],
        "options": [
            {
                "name": "source",
                "kind": "string",
                "description": "Connection string of the source database. May also be supplied via "
                "the MOLT_SOURCE environment variable; the flag takes precedence.",
                "advanced": False,
                "secret": True,
                "default": "",
            },
            {
                "name": "target",
                "kind": "string",
                "description": "Connection string of the target database. May also be supplied via "
                "the MOLT_TARGET environment variable; the flag takes precedence.",
                "advanced": False,
                "secret": True,
                "default": "",
            },
            {
                "name": "non-interactive",
                "kind": "bool",
                "description": "If set, automatically skips all user prompting and initiates "
                "actions such as show connection string debug logging (preferable if "
                "running in CI) or as an automated job. If not set, prompts user for "
                "confirmation before performing actions.",
                "advanced": False,
                "secret": False,
                "default": False,
            },
            {
                "name": "schema-filter",
                "kind": "string",
                "description": "POSIX regexp filter for schemas to action on. For Oracle sources, "
                "the schema name is the table's owner — use this flag to filter by "
                'Oracle owner (no separate --owner-filter exists). (default ".*")',
                "advanced": False,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "table-filter",
                "kind": "string",
                "description": 'POSIX regexp filter for tables to action on. (default ".*")',
                "advanced": False,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "allow-tls-mode-disable",
                "kind": "bool",
                "description": "Allows insecure connection to databases. Secure SSL/TLS connections "
                "should be used by default.  Enable this flag only if you cannot "
                "access the source or target database via secure SSL/TLS.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "case-sensitive",
                "kind": "bool",
                "description": "If true, schema, table, and column names are compared "
                "case-sensitively between source and target.  If false, we strip the "
                "surrounding quotes from these names and compare them "
                "case-insensitively.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "concurrency",
                "kind": "int",
                "description": "Number of tables to process at a time (defaults to number of CPUs).",
                "advanced": True,
                "secret": False,
                "default": "0",
            },
            {
                "name": "concurrency-per-table",
                "kind": "int",
                "description": "Number of shards per table to verify at a time. (default 1)",
                "advanced": True,
                "secret": False,
                "default": "1",
            },
            {
                "name": "fail-on-mismatch",
                "kind": "bool",
                "description": "If set, exit non-zero when verification finds one or more "
                "definitive data inconsistencies (missing/extraneous tables, "
                "mismatching table definitions, missing/mismatching/extraneous "
                "rows). Column mismatches flagged as conditional success are "
                "excluded, as are advisory cannot-verify findings (source missing a "
                "PRIMARY KEY, or PK collation mismatch) which are reported as "
                "warnings because the table cannot be row-compared. Off by default, "
                "preserving the standard exit-0 behavior.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "filter-path",
                "kind": "string",
                "description": "The path to a JSON file that specifies the selective data filters "
                "that should be applied to the relevant tables before the data is "
                "verified. ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "log-file",
                "kind": "string",
                "description": "By default, writes to a file named verify-{datetime}.log. If set as "
                '"stdout", writes will only go to stdout.',
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "logging",
                "kind": "string",
                "description": 'Level to log at (maps to zerolog.Level). (default "info")',
                "advanced": True,
                "secret": False,
                "default": "info",
            },
            {
                "name": "metrics-listen-addr",
                "kind": "string",
                "description": "Address for the metrics endpoint to listen to. (default "
                '"127.0.0.1:3030")',
                "advanced": True,
                "secret": False,
                "default": "127.0.0.1:3030",
            },
            {
                "name": "metrics-scrape-interval",
                "kind": "string",
                "description": "Scrape interval of your prometheus source. Allows for metrics to be "
                "scraped before exiting.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "opt-out-telemetry",
                "kind": "bool",
                "description": "Suppress MOLT telemetry-event emission. Telemetry is on by default; "
                "pass this flag to opt out.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "oracle-tablespace-filter",
                "kind": "string",
                "description": "POSIX regexp filter for the Oracle tablespace name. Only applied to "
                "Oracle sources; ignored (with a warning) for other dialects. "
                '(default ".*")',
                "advanced": True,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "row-batch-size",
                "kind": "int",
                "description": "Number of source/target rows to scan at a time. (default 20000)",
                "advanced": True,
                "secret": False,
                "default": "20000",
            },
            {
                "name": "rows",
                "kind": "bool",
                "description": "If true, verify both the schema (columns, types) and row data. If "
                "false, verify only the schema. (default true)",
                "advanced": True,
                "secret": False,
                "default": True,
            },
            {
                "name": "rows-per-second",
                "kind": "int",
                "description": "If set, maximum number of rows to read per second on each shard.",
                "advanced": True,
                "secret": False,
                "default": "0",
            },
            {
                "name": "source-cdb",
                "kind": "string",
                "description": "Optional connection string of the source CDB database for an Oracle "
                "database set up using a multi-tenant (CDB) architecture. May also "
                "be supplied via the MOLT_SOURCE_CDB environment variable; the flag "
                "takes precedence.",
                "advanced": True,
                "secret": True,
                "default": "",
            },
            {
                "name": "source-oracle-wallet-location",
                "kind": "string",
                "description": "Path to the Oracle wallet / config directory (godror configDir) "
                "used to locate cwallet.sso, sqlnet.ora, and tnsnames.ora when the "
                "source is an Oracle endpoint configured for SSL/TLS via an Oracle "
                "wallet. Equivalent to embedding 'configDir=<path>' as a query "
                "parameter on --source; if both are supplied, the values must match. "
                "Password-protected wallets are not supported by the underlying "
                "godror driver — configure the wallet password via sqlnet.ora in the "
                "same directory.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "table-exclusion-filter",
                "kind": "string",
                "description": 'POSIX regexp filter for tables to exclude. (default ".*")',
                "advanced": True,
                "secret": False,
                "default": ".*",
            },
            {
                "name": "transformations-file",
                "kind": "string",
                "description": "The path to a json file that specifies transformations that should "
                "be applied to the relevant tables or columns before the data is "
                "fully migrated to the target. These include column exclusions and "
                "table aliases. ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "type-map-file",
                "kind": "string",
                "description": "The path to a JSON file that maps per-column source types to "
                "CockroachDB types. When set, a column whose source and target types "
                "are not directly comparable is not reported as a definition "
                "mismatch when the file carries an entry for that table and column "
                "whose source_type and crdb_type also match the actual source and "
                "target column types; a non-matching entry is ignored with a WARN. "
                "Such a column is compared at the value level only when the source "
                "value has a text/coercion path (range types are supported); other "
                "substitutions instead surface as per-row column-mismatch counts. "
                "Mirrors the molt fetch flag. ",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "use-console-writer",
                "kind": "bool",
                "description": "Use the console writer, which has cleaner log output but introduces "
                "more latency (defaults to false, which logs as structured JSON).",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "verify-statement-timeout",
                "kind": "string",
                "description": "Timeout limit for SQL statements used during data verification. "
                "(default 1h0m0s)",
                "advanced": True,
                "secret": False,
                "default": "1h0m0s",
            },
        ],
    },
    {
        "id": "convert-postgres",
        "label": "Convert PostgreSQL schema",
        "arguments": ["convert", "postgres"],
        "options": [
            {
                "name": "schema",
                "kind": "string",
                "description": "Filename of the source schema. It will find the file that matches "
                "'filename.N' with the greatest suffix.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "url",
                "kind": "string",
                "description": "CockroachDB connection url. It will create a temporary database and "
                "evaluate the resulting schema, reporting any errors. Set to '' to "
                "skip evaluation. (default "
                '"postgres://root@localhost:26257?sslmode=disable")',
                "advanced": False,
                "secret": True,
                "default": "postgres://root@localhost:26257?sslmode=disable",
            },
            {
                "name": "out",
                "kind": "string",
                "description": "Output schema location. If not specified, it will use 'schema.N+1'. "
                "Use '-' for stout.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "autoIncrement",
                "kind": "string",
                "description": "Auto increment option "
                "([unordered_rowid]/[rowid]/[sequence]/[uuid]). (default rowid)",
                "advanced": True,
                "secret": False,
                "default": "rowid",
            },
            {
                "name": "defaultIntSize",
                "kind": "int",
                "description": "Default int size. (default 4)",
                "advanced": True,
                "secret": False,
                "default": "4",
            },
            {
                "name": "db",
                "kind": "string",
                "description": "Database to use to execute converted schema. If not provided, a "
                "temporary database will be used.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "format",
                "kind": "string",
                "description": "Output format. Defines what kind of the schema to produce "
                "([original]/[target|crdb]). (default original)",
                "advanced": True,
                "secret": False,
                "default": "original",
            },
        ],
    },
    {
        "id": "convert-mysql",
        "label": "Convert MySQL schema",
        "arguments": ["convert", "mysql"],
        "options": [
            {
                "name": "schema",
                "kind": "string",
                "description": "Filename of the source schema. It will find the file that matches "
                "'filename.N' with the greatest suffix.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "url",
                "kind": "string",
                "description": "CockroachDB connection url. It will create a temporary database and "
                "evaluate the resulting schema, reporting any errors. Set to '' to "
                "skip evaluation. (default "
                '"postgres://root@localhost:26257?sslmode=disable")',
                "advanced": False,
                "secret": True,
                "default": "postgres://root@localhost:26257?sslmode=disable",
            },
            {
                "name": "out",
                "kind": "string",
                "description": "Output schema location. If not specified, it will use 'schema.N+1'. "
                "Use '-' for stout.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "autoIncrement",
                "kind": "string",
                "description": "Auto increment option "
                "([sequence]/[uuid]/[unordered_rowid]/[rowid]). (default rowid)",
                "advanced": True,
                "secret": False,
                "default": "rowid",
            },
            {
                "name": "caseKeep",
                "kind": "bool",
                "description": "Keeps the case of the input name.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "enumConversion",
                "kind": "string",
                "description": "Enum option ([combine]/[unique]). (default combine)",
                "advanced": True,
                "secret": False,
                "default": "combine",
            },
            {
                "name": "db",
                "kind": "string",
                "description": "Database to use to execute converted schema. If not provided, a "
                "temporary database will be used.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "format",
                "kind": "string",
                "description": "Output format. Defines what kind of the schema to produce "
                "([original]/[target|crdb]). (default original)",
                "advanced": True,
                "secret": False,
                "default": "original",
            },
        ],
    },
    {
        "id": "convert-oracle",
        "label": "Convert Oracle schema",
        "arguments": ["convert", "oracle"],
        "options": [
            {
                "name": "schema",
                "kind": "string",
                "description": "Filename of the source schema. It will find the file that matches "
                "'filename.N' with the greatest suffix.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "url",
                "kind": "string",
                "description": "CockroachDB connection url. It will create a temporary database and "
                "evaluate the resulting schema, reporting any errors. Set to '' to "
                "skip evaluation. (default "
                '"postgres://root@localhost:26257?sslmode=disable")',
                "advanced": False,
                "secret": True,
                "default": "postgres://root@localhost:26257?sslmode=disable",
            },
            {
                "name": "out",
                "kind": "string",
                "description": "Output schema location. If not specified, it will use 'schema.N+1'. "
                "Use '-' for stout.",
                "advanced": False,
                "secret": False,
                "default": "",
            },
            {
                "name": "autoIncrement",
                "kind": "string",
                "description": "Auto increment option "
                "([rowid]/[sequence]/[uuid]/[unordered_rowid]). (default rowid)",
                "advanced": True,
                "secret": False,
                "default": "rowid",
            },
            {
                "name": "caseKeep",
                "kind": "bool",
                "description": "Keeps the case of the input name.",
                "advanced": True,
                "secret": False,
                "default": False,
            },
            {
                "name": "db",
                "kind": "string",
                "description": "Database to use to execute converted schema. If not provided, a "
                "temporary database will be used.",
                "advanced": True,
                "secret": False,
                "default": "",
            },
            {
                "name": "format",
                "kind": "string",
                "description": "Output format. Defines what kind of the schema to produce "
                "([original]/[target|crdb]). (default original)",
                "advanced": True,
                "secret": False,
                "default": "original",
            },
        ],
    },
]

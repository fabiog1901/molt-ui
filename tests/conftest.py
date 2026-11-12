"""Small explicit catalogs keep tests independent of the bundled Go binary."""

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from molt_ui.core.models import CommandCatalog, CommandSpec, OptionSpec


@pytest.fixture
def command_catalog():
    commands = []
    definitions = [
        ('convert-mysql', ('convert', 'mysql'), [
            ('format', 'string', 'original', None),
            ('out', 'string', '', None),
            ('schema', 'string', '', None),
            ('url', 'string', 'postgres://root@localhost:26257?sslmode=disable', None),
        ]),
        ('convert-oracle', ('convert', 'oracle'), [
            ('format', 'string', 'original', None),
            ('out', 'string', '', None),
            ('schema', 'string', '', None),
            ('url', 'string', 'postgres://root@localhost:26257?sslmode=disable', None),
        ]),
        ('convert-postgres', ('convert', 'postgres'), [
            ('format', 'string', 'original', None),
            ('out', 'string', '', None),
            ('schema', 'string', '', None),
            ('url', 'string', 'postgres://root@localhost:26257?sslmode=disable', None),
        ]),
        ('fetch', ('fetch',), [
            ('allow-tls-mode-disable', 'bool', False, None),
            ('assume-role', 'string', '', None),
            ('bucket-path', 'string', '', None),
            ('compression', 'string', 'gzip', None),
            ('direct-copy', 'bool', False, None),
            ('dropped-constraints-file', 'string', '', None),
            ('local-path', 'string', '', None),
            ('log-file', 'string', '', None),
            ('logging', 'string', 'info', None),
            ('metrics-listen-addr', 'string', '127.0.0.1:3030', None),
            ('metrics-scrape-interval', 'string', '', None),
            ('mode', 'string', 'data-load', None),
            ('opt-out-telemetry', 'bool', False, None),
            ('oracle-application-users', 'string', '', None),
            ('pglogical-replication-slot-name', 'string', '', None),
            ('pprof-listen-addr', 'string', '127.0.0.1:3031', None),
            ('require-empty-target', 'bool', False, None),
            ('schema-filter', 'string', '.*', None),
            ('source', 'string', '', 'MOLT_SOURCE'),
            ('source-cdb', 'string', '', 'MOLT_SOURCE_CDB'),
            ('table-concurrency', 'int', '4', None),
            ('table-filter', 'string', '.*', None),
            ('table-handling', 'string', 'none', None),
            ('target', 'string', '', 'MOLT_TARGET'),
            ('use-console-writer', 'bool', False, None),
            ('use-copy', 'bool', False, None),
            ('use-stats-based-sharding', 'bool', False, None),
        ]),
        ('verify', ('verify',), [
            ('concurrency', 'int', '0', None),
            ('log-file', 'string', '', None),
            ('logging', 'string', 'info', None),
            ('metrics-listen-addr', 'string', '127.0.0.1:3030', None),
            ('metrics-scrape-interval', 'string', '', None),
            ('opt-out-telemetry', 'bool', False, None),
            ('rows', 'bool', True, None),
            ('source', 'string', '', 'MOLT_SOURCE'),
            ('target', 'string', '', 'MOLT_TARGET'),
            ('use-console-writer', 'bool', False, None),
        ]),
    ]
    for name, arguments, fields in definitions:
        commands.append(CommandSpec(
            id=name, arguments=arguments, options=tuple(
                OptionSpec(name=flag, kind=kind, default=default,
                           description=flag.replace("-", " "), environment_variable=env)
                for flag, kind, default, env in fields
            ),
        ))
    return CommandCatalog(schema_version=1, commands=tuple(commands))


@pytest.fixture(autouse=True)
def isolated_metadata_database(monkeypatch, tmp_path):
    monkeypatch.setenv("MOLT_DATABASE", str(tmp_path / "runs.sqlite3"))


@pytest.fixture(autouse=True)
def repository_clock(monkeypatch):
    """Give unrelated test operations distinct seconds; collision tests freeze this clock."""
    ticks = count()
    start = datetime(2026, 11, 12, tzinfo=timezone.utc)
    monkeypatch.setattr('molt_ui.repo.repo.timestamp',
                        lambda: (start + timedelta(seconds=next(ticks))).strftime('%Y-%m-%dT%H.%M.%SZ'))

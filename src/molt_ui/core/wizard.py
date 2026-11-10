"""Shared option presentation and applicability rules for the command wizard."""

from copy import deepcopy
import os

from .catalog import COMMANDS

STAGING = {
    'bucket-path', 'local-path', 'local-path-crdb-access-addr', 'local-path-listen-addr',
    'compression', 'cleanup', 'flush-rows', 'flush-size', 'assume-role', 'import-assume-role',
    'import-batch-size', 'import-region', 'use-implicit-auth', 'use-copy',
}
CHOICES = {
    'logging': [(level, level) for level in ('trace', 'debug', 'info', 'warn', 'error', 'fatal', 'panic')],
    'mode': [('data-load', 'Load data'), ('export-only', 'Export only'), ('import-only', 'Import only')],
    'table-handling': [('none', 'Keep existing tables'), ('truncate-if-exists', 'Truncate existing tables'), ('drop-on-target-and-recreate', 'Drop and recreate tables')],
    'compression': [('none', 'None'), ('gzip', 'Gzip')],
    'format': [('original', 'Original'), ('target', 'Target'), ('crdb', 'CockroachDB')],
}
LABELS = {
    'source': 'Source connection', 'target': 'Target connection', 'source-cdb': 'Oracle CDB connection',
    'direct-copy': 'Direct copy (no staging)', 'mode': 'Fetch mode', 'table-handling': 'Target table handling',
    'schema': 'Schema file', 'out': 'Output file', 'url': 'Evaluation database URL',
    'non-interactive': 'Automatic prompt handling', 'bucket-path': 'Staging bucket', 'local-path': 'Local staging directory',
}


def source_dialect(source: str) -> str:
    scheme = source.partition(':')[0].lower()
    return {'postgres': 'postgres', 'postgresql': 'postgres', 'mysql': 'mysql', 'oracle': 'oracle',
            'cockroach': 'cockroachdb', 'cockroachdb': 'cockroachdb'}.get(scheme, 'unknown')


def wizard_catalog() -> list[dict]:
    catalog = deepcopy(COMMANDS)
    for command in catalog:
        command['default_source_dialect'] = source_dialect(os.environ.get('MOLT_SOURCE', ''))
        for option in command['options']:
            name = option['name']
            option['required'] = (name in {'source', 'target'} and command['id'] in {'fetch', 'verify'}
                                  and not os.environ.get('MOLT_' + name.upper())) or name == 'schema'
            option['environment_variable'] = {'source': 'MOLT_SOURCE', 'target': 'MOLT_TARGET', 'source-cdb': 'MOLT_SOURCE_CDB'}.get(name)
            option['from_environment'] = bool(option['environment_variable'] and os.environ.get(option['environment_variable']))
            option['default_label'] = ''
            if name == 'log-file':
                option['default_label'] = command['id'] + '-{datetime}.log (generated automatically)'
            if command['id'].startswith('convert-'):
                if name == 'out':
                    option['default'] = '-'
                if name == 'url':
                    option['default'] = ''
                    option['default_label'] = 'Disabled (no evaluation)'
            if name == 'concurrency' and command['id'] == 'verify':
                option['default'] = ''
                option['default_label'] = 'Automatic (CPU count)'
            if name == 'use-stats-based-sharding':
                option['default_by_source'] = {'postgres': True}
            stage = 'advanced' if option['advanced'] else 'common'
            if name in {'source', 'target', 'source-cdb', 'source-oracle-wallet-location', 'schema', 'out', 'url'}:
                stage = 'connections'
            elif command['id'] == 'fetch' and name in {'mode', 'direct-copy'}:
                stage = 'operation'
            elif name in {'bucket-path', 'local-path'}:
                stage = 'common'
            elif name in {'logging', 'log-file', 'use-console-writer'}:
                stage = 'logging'
            elif name.startswith('metrics-') or name in {'opt-out-telemetry', 'pprof-listen-addr'}:
                stage = 'metrics'
            rules = []
            if command['id'] == 'fetch':
                if name == 'direct-copy':
                    rules.append({'test': 'data-load'})
                if name in STAGING:
                    rules.append({'test': 'staged'})
                if name in {'assume-role', 'import-assume-role', 'import-region', 'use-implicit-auth'}:
                    rules.append({'test': 'bucket'})
                if name in {'local-path-crdb-access-addr', 'local-path-listen-addr'}:
                    rules.append({'test': 'local'})
                if name in {'dropped-constraints-file', 'dropped-indexes-file'}:
                    rules.append({'test': 'recreate'})
                if name == 'require-empty-target':
                    rules.append({'test': 'empty-target'})
            if name.startswith('oracle-') or name in {'source-cdb', 'source-oracle-wallet-location'}:
                rules.append({'test': 'dialect', 'value': 'oracle'})
            if name.startswith('pglogical-') or name in {'flatten-partitioned-tables', 'use-stats-based-sharding'}:
                rules.append({'test': 'dialect', 'value': 'postgres'})
            option.update(stage=stage, rules=rules, label=LABELS.get(name, name.replace('-', ' ').capitalize()))
            option['choices'] = [{'value': value, 'label': label} for value, label in CHOICES.get(name, [])]
            option['brief'] = option['description'].split('. ', 1)[0].strip()[:180]
    return catalog


def applies(option: dict, values: dict, dialect: str) -> bool:
    mode = values.get('mode', 'data-load')
    direct = mode == 'data-load' and values.get('direct-copy') is True
    for rule in option['rules']:
        test = rule['test']
        if test == 'data-load' and mode != 'data-load':
            return False
        if test == 'staged' and direct:
            return False
        if test == 'bucket' and not values.get('bucket-path'):
            return False
        if test == 'local' and not values.get('local-path'):
            return False
        if test == 'recreate' and (values.get('table-handling') != 'drop-on-target-and-recreate' or values.get('fetch-id')):
            return False
        if test == 'empty-target' and (values.get('table-handling') in {'truncate-if-exists', 'drop-on-target-and-recreate'} or values.get('fetch-id') or values.get('continuation-token') or mode == 'export-only'):
            return False
        if test == 'dialect' and dialect != 'unknown' and dialect != rule['value']:
            return False
    return True


def normalize_options(command: str, options: dict, *, source_kind: str | None = None) -> tuple[dict, list[str]]:
    definition = next((item for item in wizard_catalog() if item['id'] == command), None)
    if definition is None:
        raise ValueError('Unknown molt command.')
    known = {option['name']: option for option in definition['options']}
    if options.keys() - known.keys():
        raise ValueError('Unknown option for the selected command.')
    for name, value in options.items():
        if known[name]['kind'] == 'bool':
            if not isinstance(value, bool):
                raise ValueError(f'--{name} must be true or false.')
        elif not isinstance(value, str):
            raise ValueError(f'--{name} must be text.')
        accepted = {choice['value'] for choice in known[name]['choices']}
        if name == 'logging':
            accepted.add('disabled')
        if known[name]['choices'] and value not in accepted:
            raise ValueError(f'Choose a valid value for --{name}.')
    dialect = source_dialect(options.get('source') or os.environ.get('MOLT_SOURCE', ''))
    if source_kind is not None:
        if source_kind not in {'postgres', 'oracle', 'mysql'}:
            raise ValueError('Choose PostgreSQL, Oracle, or MySQL as the source database.')
        compatible = dialect == source_kind or (source_kind == 'postgres' and dialect == 'cockroachdb')
        if dialect != 'unknown' and not compatible:
            raise ValueError('The source connection does not match the selected source database.')
        dialect = source_kind
    result = dict(options)
    removed = []
    # Repeat so dependent values disappear too (for example bucket + its role).
    while True:
        invalid = [name for name in result if not applies(known[name], result, dialect)]
        if not invalid:
            return result, removed
        for name in invalid:
            removed.append(name)
            del result[name]

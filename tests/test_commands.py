import pytest

from molt_ui.core.commands import build_command
from molt_ui.core.catalog import COMMANDS


def test_fetch_keeps_credentials_in_child_environment_and_arguments_literal():
    arguments, env = build_command('fetch', {
        'source': 'postgres://user:password@source/db', 'target': 'postgres://target/db',
        'direct-copy': True, 'table-filter': 'users; echo test', 'table-concurrency': '2',
    })
    assert arguments == ['fetch', '--direct-copy=true', '--table-filter=users; echo test', '--table-concurrency=2', '--log-file=stdout']
    assert env['MOLT_SOURCE'] == 'postgres://user:password@source/db'
    assert not any('password' in arg for arg in arguments)


@pytest.mark.parametrize('options', [
    {'unknown': 'value'}, {'direct-copy': 'true'}, {'table-concurrency': 'two'},
])
def test_invalid_options_are_rejected(options, monkeypatch):
    monkeypatch.setenv('MOLT_SOURCE', 'source')
    monkeypatch.setenv('MOLT_TARGET', 'target')
    with pytest.raises(ValueError):
        build_command('fetch', options)


def test_connections_are_required_unless_in_environment(monkeypatch):
    monkeypatch.delenv('MOLT_SOURCE', raising=False)
    monkeypatch.delenv('MOLT_TARGET', raising=False)
    with pytest.raises(ValueError, match='source'):
        build_command('fetch', {})
    monkeypatch.setenv('MOLT_SOURCE', 'source')
    monkeypatch.setenv('MOLT_TARGET', 'target')
    assert build_command('verify', {'rows': False})[0] == ['verify', '--rows=false', '--log-file=stdout']


def test_help_does_not_require_connections():
    assert build_command('fetch', {}, help_only=True) == (['fetch', '--help'], {})
    with pytest.raises(ValueError):
        build_command('arbitrary', {}, help_only=True)


def test_conversion_defaults_to_printing_without_database_evaluation():
    args, env = build_command('convert-postgres', {'schema': '/tmp/schema.sql'})
    assert args == ['convert', 'postgres', '--schema=/tmp/schema.sql', '--out=-', '--url=']
    assert env == {}
    with pytest.raises(ValueError, match='schema'):
        build_command('convert-mysql', {})


def test_catalog_has_unique_flags_and_boolean_copy_option():
    for command in COMMANDS:
        names = [option['name'] for option in command['options']]
        assert len(names) == len(set(names))
    fetch = COMMANDS[0]
    assert next(option for option in fetch['options'] if option['name'] == 'use-copy')['kind'] == 'bool'

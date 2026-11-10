import pytest
from pydantic import ValidationError

from molt_ui.core.models import CommandResult, LogEntry, OutputEvent, TableProgress
from molt_ui.core.wizard import wizard_catalog
from molt_ui.frontends.models import CommandDefinition, StartCommand


def test_frontend_catalog_models_preserve_existing_command_metadata():
    for definition in wizard_catalog():
        model = CommandDefinition.model_validate(definition)
        assert model.model_dump(exclude_unset=True) == definition
        assert model.options[0].name == definition['options'][0]['name']


def test_request_model_rejects_unknown_fields_and_untyped_options():
    with pytest.raises(ValidationError):
        StartCommand(command='fetch', arbitrary='unexpected')
    with pytest.raises(ValidationError):
        StartCommand(command='fetch', options={'table-concurrency': 4})
    request = StartCommand(command='fetch', options={'direct-copy': False, 'logging': 'disabled'})
    assert request.options['direct-copy'] is False


def test_shared_models_preserve_output_and_are_immutable():
    entry = LogEntry(stream='stdout', data={'level': 'info', 'num_rows': 200})
    result = CommandResult(stdout='output', stderr='', returncode=0, logs=(entry,))
    assert CommandResult.model_validate_json(result.model_dump_json()) == result
    event = OutputEvent(sequence=1, stream='stdout', text='output', data=entry.data)
    assert event.model_dump()['data']['num_rows'] == 200
    with pytest.raises(ValidationError):
        event.sequence = 2
    with pytest.raises(ValidationError):
        OutputEvent(sequence='1', stream='stdout', text='output', data=None)


def test_table_progress_remains_mutable_for_incremental_aggregation():
    table = TableProgress(name='public.actor', exported=200, phase='exported')
    table.warnings += 1
    state = table.snapshot('succeeded')
    assert state['exported'] == 200
    assert state['warnings'] == 1
    assert state['status'] == 'warning'

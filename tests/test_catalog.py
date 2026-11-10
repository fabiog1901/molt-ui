"""Validate the resource contract and regeneration without needing a molt binary."""

import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from molt_ui import catalog_update as generator
from molt_ui.core.models import CommandCatalog, CommandResult
from molt_ui.frontends.models import CommandDefinition

HELP = '''Flags:
      --logging string       Logging level (default "info")
      --rows                 Compare row counts (default true)
      --concurrency int      Worker count
      --use-copy bool        Use COPY (default false)
      --filter string        A table filter
                             continued description
  -h, --help                 help for command
'''


def test_catalog_contains_cli_facts_without_presentation_or_runtime_policy(command_catalog):
    raw = json.loads(command_catalog.model_dump_json(exclude_unset=True))
    assert raw["schema_version"] == 1
    assert {"fetch", "verify", "convert-postgres"} <= {spec.id for spec in command_catalog.commands}
    for command in raw["commands"]:
        assert set(command) == {"id", "arguments", "options"}
        for option in command["options"]:
            assert set(option) - {"environment_variable"} == {"name", "kind", "description", "default"}


@pytest.mark.parametrize("change", ["version", "duplicate-command", "duplicate-option", "unknown-field"])
def test_catalog_rejects_invalid_resources(command_catalog, change):
    raw = json.loads(command_catalog.model_dump_json(exclude_unset=True))
    if change == "version":
        raw["schema_version"] = 2
    elif change == "duplicate-command":
        raw["commands"].append(raw["commands"][0])
    elif change == "duplicate-option":
        options = raw["commands"][0]["options"]
        options.append(options[0])
    else:
        raw["commands"][0]["options"][0]["stage"] = "connections"
    with pytest.raises(ValidationError):
        CommandCatalog.model_validate_json(json.dumps(raw))


def test_help_parser_preserves_types_defaults_and_continuations():
    options = {option.name: option for option in generator.parse_help(HELP)}
    assert options["logging"].default == "info"
    assert options["rows"].default is True
    assert options["concurrency"].kind == "int"
    assert options["concurrency"].default == "0"
    assert options["use-copy"].kind == "bool"
    assert options["use-copy"].default is False
    assert options["filter"].description == "A table filter continued description"
    assert "help" not in options


def test_generator_builds_valid_catalog_from_any_working_directory(tmp_path, monkeypatch):
    process = Mock()
    def run(arguments):
        text = (
            "Available Commands:\n  convert   Conversion\n  future   New command\n\nFlags:\n"
            if arguments == ["--help"] else
            "Available Commands:\n  postgres   PostgreSQL\n\nFlags:\n"
            if arguments == ["convert", "--help"] else HELP
        )
        return CommandResult(stdout=text, stderr="", returncode=0)
    process.run.side_effect = run
    monkeypatch.chdir(tmp_path)
    generated = generator.generate_catalog(process)
    assert {spec.id for spec in CommandCatalog.model_validate_json(generated.model_dump_json()).commands} == {"convert-postgres", "future"}
    assert process.run.call_args_list[2].args == (["convert", "postgres", "--help"],)


@pytest.mark.parametrize("result", [
    CommandResult(stdout="", stderr="failed", returncode=1),
    CommandResult(stdout="unexpected help format", stderr="", returncode=0),
])
def test_generator_reports_unusable_help(result):
    process = Mock()
    process.run.return_value = result
    with pytest.raises((RuntimeError, ValueError)):
        generator.generate_catalog(process)


def test_execution_defaults_and_presentation_defaults_are_separate(command_catalog):
    verify = next(spec for spec in command_catalog.commands if spec.id == "verify")
    core_options = {option.name: option for option in verify.options}
    display_options = {option.name: option for option in CommandDefinition.from_spec(verify).options}
    assert core_options["concurrency"].default == "0"
    assert display_options["concurrency"].default_label == "Automatic (CPU count)"
    assert "allowed_values" not in core_options["logging"].model_dump()
    assert "disabled" not in {choice.value for choice in display_options["logging"].choices}


def test_parser_records_environment_variables_as_cli_facts():
    option, = generator.parse_help('''Flags:
      --source string       Connection. May also be supplied via the MOLT_SOURCE environment variable; the flag takes precedence.
''')
    assert option.environment_variable == "MOLT_SOURCE"


def test_catalog_rejects_defaults_that_cannot_be_displayed():
    from molt_ui.core.models import OptionSpec

    with pytest.raises(ValidationError, match="does not match"):
        OptionSpec(name="new-switch", kind="bool", description="Switch", default="true")


def test_generator_discovers_commands_that_also_have_subcommands():
    process = Mock()
    responses = {
        ("--help",): "Available Commands:\n  future  New command\n\nFlags:\n",
        ("future", "--help"): "Usage:\n  molt future [flags]\n  molt future [command]\n\nAvailable Commands:\n  child  Child command\n\n" + HELP,
        ("future", "child", "--help"): "Usage:\n  molt future child [flags]\n\n" + HELP,
    }
    process.run.side_effect = lambda args: CommandResult(stdout=responses[tuple(args)], stderr="", returncode=0)
    assert [spec.arguments for spec in generator.generate_catalog(process).commands] == [
        ("future",), ("future", "child"),
    ]

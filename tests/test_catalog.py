"""Validate the resource contract and regeneration without needing a molt binary."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from molt_ui.core.catalog import catalog_path, load_catalog
from molt_ui.core.models import CommandCatalog, CommandResult
from molt_ui.core.options import command_definitions
from molt_ui.frontends.models import CommandDefinition

SCRIPT = Path(__file__).parents[1] / "resources/scripts/update_command_catalog.py"
spec = importlib.util.spec_from_file_location("update_command_catalog", SCRIPT)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

HELP = '''Flags:
      --logging string       Logging level (default "info")
      --rows                 Compare row counts (default true)
      --concurrency int      Worker count
      --use-copy bool        Use COPY (default false)
      --filter string        A table filter
                             continued description
  -h, --help                 help for command
'''


def test_resource_contains_cli_facts_without_presentation_or_runtime_policy():
    raw = json.loads(catalog_path().read_text())
    assert raw["schema_version"] == 1
    assert len(load_catalog().commands) == 5
    for command in raw["commands"]:
        assert set(command) == {"id", "arguments", "options"}
        for option in command["options"]:
            assert set(option) == {"name", "kind", "description", "default"}


@pytest.mark.parametrize("change", ["version", "duplicate-command", "duplicate-option", "unknown-field"])
def test_catalog_rejects_invalid_resources(change):
    raw = json.loads(catalog_path().read_text())
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


def test_generator_writes_valid_json_from_any_working_directory(tmp_path, monkeypatch):
    process = Mock()
    process.run.return_value = CommandResult(stdout=HELP, stderr="", returncode=0)
    factory = Mock(return_value=process)
    monkeypatch.setattr(generator, "MoltProcess", factory)
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "resources/catalog.json"
    generator.main(["--executable", "/test/molt", "--output", str(output)])
    assert len(CommandCatalog.model_validate_json(output.read_text()).commands) == 5
    factory.assert_called_once_with("/test/molt")
    assert process.run.call_args_list[2].args == (["convert", "postgres", "--help"],)
    assert generator.DEFAULT_OUTPUT == SCRIPT.parents[1] / "command_catalog.json"


@pytest.mark.parametrize("result", [
    CommandResult(stdout="", stderr="failed", returncode=1),
    CommandResult(stdout="unexpected help format", stderr="", returncode=0),
])
def test_generator_preserves_existing_catalog_when_help_fails(tmp_path, monkeypatch, result):
    output = tmp_path / "catalog.json"
    output.write_text("existing catalog")
    process = Mock()
    process.run.return_value = result
    monkeypatch.setattr(generator, "MoltProcess", Mock(return_value=process))
    with pytest.raises((RuntimeError, ValueError)):
        generator.main(["--output", str(output)])
    assert output.read_text() == "existing catalog"


def test_execution_defaults_and_presentation_defaults_are_separate():
    verify = next(spec for spec in command_definitions(environment={}) if spec.id == "verify")
    core_options = {option.name: option for option in verify.options}
    display_options = {option.name: option for option in CommandDefinition.from_spec(verify).options}
    assert core_options["concurrency"].default == "0"
    assert display_options["concurrency"].default_label == "Automatic (CPU count)"
    assert "disabled" in core_options["logging"].allowed_values
    assert "disabled" not in {choice.value for choice in display_options["logging"].choices}

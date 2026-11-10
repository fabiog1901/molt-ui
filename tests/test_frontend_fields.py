import pytest

from molt_ui.core.commands import build_command
from molt_ui.frontends.models import CommandDefinition


def frontend_catalog(command_catalog):
    return [CommandDefinition.from_spec(spec).model_dump(exclude_unset=True)
            for spec in command_catalog.commands]


def test_wizard_exposes_real_defaults_and_required_fields(command_catalog, monkeypatch):

    monkeypatch.delenv("MOLT_SOURCE", raising=False)
    monkeypatch.delenv("MOLT_TARGET", raising=False)
    catalog = {
        command["id"]: {option["name"]: option for option in command["options"]}
        for command in frontend_catalog(command_catalog)
    }
    fetch = catalog["fetch"]
    assert fetch["mode"]["default"] == "data-load"
    assert fetch["compression"]["default"] == "gzip"
    assert fetch["table-handling"]["default"] == "none"
    assert fetch["table-concurrency"]["default"] == "4"
    assert fetch["allow-tls-mode-disable"]["default"] is False
    assert fetch["use-stats-based-sharding"]["default_by_source"]["postgres"] is True
    assert fetch["source"]["required"] is True
    assert fetch["target"]["required"] is True
    assert fetch["source-cdb"]["required"] is False
    assert catalog["verify"]["rows"]["default"] is True
    assert catalog["convert-postgres"]["schema"]["required"] is True
    monkeypatch.setenv("MOLT_SOURCE", "postgres://example/db")
    fetch = next(command for command in frontend_catalog(command_catalog) if command["id"] == "fetch")
    source = next(option for option in fetch["options"] if option["name"] == "source")
    assert source["required"] is False
    assert source["from_environment"] is True
    assert (
        source["default"] == ""
    )  # Do not expose inherited credentials in catalog metadata.


def test_logging_metrics_and_telemetry_have_dedicated_wizard_tabs(command_catalog):

    for command in frontend_catalog(command_catalog):
        options = {option["name"]: option for option in command["options"]}
        if command["id"] in {"fetch", "verify"}:
            for name in ("logging", "log-file", "use-console-writer"):
                assert options[name]["stage"] == "logging"
            for name in (
                "metrics-listen-addr",
                "metrics-scrape-interval",
                "opt-out-telemetry",
            ):
                assert options[name]["stage"] == "metrics"
        if "pprof-listen-addr" in options:
            assert options["pprof-listen-addr"]["stage"] == "metrics"


@pytest.mark.parametrize(
    "level", ["trace", "debug", "info", "warn", "error", "fatal", "panic"]
)
def test_logging_dropdown_levels_are_valid_and_preserved_in_argv(command_catalog, level):

    command = next(item for item in frontend_catalog(command_catalog) if item["id"] == "verify")
    option = next(item for item in command["options"] if item["name"] == "logging")
    assert option["default"] == "info"
    assert level in {choice["value"] for choice in option["choices"]}
    arguments, _ = build_command(
        "verify",
        {
            "source": "postgres://source/db",
            "target": "postgres://target/db",
            "logging": level,
        },
        catalog=command_catalog,
    )
    assert "--logging=" + level in arguments


def test_disabling_logging_uses_the_flag_without_appearing_in_the_level_choices(command_catalog):

    options = next(command for command in frontend_catalog(command_catalog) if command["id"] == "fetch")[
        "options"
    ]
    logging = next(option for option in options if option["name"] == "logging")
    assert all(choice["value"] == choice["label"] for choice in logging["choices"])
    assert "disabled" not in {choice["value"] for choice in logging["choices"]}
    assert "" not in {choice["value"] for choice in logging["choices"]}
    arguments, _ = build_command(
        "fetch",
        {
            "source": "postgres://source/db",
            "target": "postgres://target/db",
            "logging": "disabled",
        },
        catalog=command_catalog,
    )
    assert "--logging=disabled" in arguments



@pytest.mark.parametrize("command", ["fetch", "verify"])
def test_log_file_preserves_cli_default_unless_explicitly_overridden(command_catalog, command):

    options = {"source": "postgres://source/db", "target": "postgres://target/db"}
    args, _ = build_command(command, options, catalog=command_catalog)
    assert not any(argument.startswith("--log-file=") for argument in args)
    definition = next(item for item in frontend_catalog(command_catalog) if item["id"] == command)
    log_file = next(
        option for option in definition["options"] if option["name"] == "log-file"
    )
    assert log_file["default"] == ""
    assert command + "-{datetime}.log" in log_file["default_label"]
    args, _ = build_command(command, {**options, "log-file": "stdout"}, catalog=command_catalog)
    assert "--log-file=stdout" in args
    args, _ = build_command(command, {**options, "log-file": "/tmp/custom.log"}, catalog=command_catalog)
    assert "--log-file=/tmp/custom.log" in args


def test_unknown_command_and_new_flags_have_generic_controls():
    from molt_ui.core.models import CommandSpec, OptionSpec

    specification = CommandSpec(id="future", arguments=("future",), options=(
        OptionSpec(name="new-limit", kind="int", description="Limit", default="42"),
        OptionSpec(name="new-switch", kind="bool", description="Switch", default=True),
        OptionSpec(name="mode", kind="string", description="Unrelated mode", default="future-default"),
    ))
    form = CommandDefinition.from_spec(specification, environment={})
    fields = {option.name: option for option in form.options}
    assert fields["new-limit"].stage == "advanced"
    assert fields["new-limit"].default == "42"
    assert fields["new-switch"].kind == "bool"
    assert fields["mode"].choices == []
    assert form.arguments == ["future"]


@pytest.mark.parametrize("change, message", [
    ("missing-field", "no longer contains --source"),
    ("changed-type", "configured control requires string"),
    ("new-default", "new default 'future-mode'"),
])
def test_modal_reports_incompatible_catalog_drift(command_catalog, change, message):
    from molt_ui.core.errors import MoltError
    from molt_ui.core.models import OptionSpec

    specification = next(spec for spec in command_catalog.commands if spec.id == "fetch")
    fields = list(specification.options)
    if change == "missing-field":
        fields = [field for field in fields if field.name != "source"]
    else:
        index = next(index for index, field in enumerate(fields) if field.name == "mode")
        fields[index] = OptionSpec(
            name="mode", description="Changed mode",
            kind="bool" if change == "changed-type" else "string",
            default=False if change == "changed-type" else "future-mode",
        )
    with pytest.raises(MoltError, match=message):
        CommandDefinition.from_spec(specification.model_copy(update={"options": tuple(fields)}))


def test_conversion_modal_uses_actual_catalog_defaults(command_catalog):
    specification = next(spec for spec in command_catalog.commands if spec.id == "convert-postgres")
    fields = {option.name: option for option in CommandDefinition.from_spec(specification).options}
    for option in specification.options:
        assert fields[option.name].default == option.default

import pytest

from molt_ui.core.commands import build_command
from molt_ui.core.catalog import COMMANDS


def test_fetch_keeps_credentials_in_child_environment_and_arguments_literal():
    arguments, env = build_command(
        "fetch",
        {
            "source": "postgres://user:password@source/db",
            "target": "postgres://target/db",
            "direct-copy": True,
            "table-filter": "users; echo test",
            "table-concurrency": "2",
        },
    )
    assert arguments == [
        "fetch",
        "--direct-copy=true",
        "--table-filter=users; echo test",
        "--table-concurrency=2",
    ]
    assert env["MOLT_SOURCE"] == "postgres://user:password@source/db"
    assert not any("password" in arg for arg in arguments)


@pytest.mark.parametrize(
    "options",
    [
        {"unknown": "value"},
        {"direct-copy": "true"},
        {"table-concurrency": "two"},
    ],
)
def test_invalid_options_are_rejected(options, monkeypatch):
    monkeypatch.setenv("MOLT_SOURCE", "source")
    monkeypatch.setenv("MOLT_TARGET", "target")
    with pytest.raises(ValueError):
        build_command("fetch", options)


def test_connections_are_required_unless_in_environment(monkeypatch):
    monkeypatch.delenv("MOLT_SOURCE", raising=False)
    monkeypatch.delenv("MOLT_TARGET", raising=False)
    with pytest.raises(ValueError, match="source"):
        build_command("fetch", {})
    monkeypatch.setenv("MOLT_SOURCE", "source")
    monkeypatch.setenv("MOLT_TARGET", "target")
    assert build_command("verify", {"rows": False})[0] == ["verify", "--rows=false"]


def test_help_does_not_require_connections():
    assert build_command("fetch", {}, help_only=True) == (["fetch", "--help"], {})
    with pytest.raises(ValueError):
        build_command("arbitrary", {}, help_only=True)


def test_conversion_defaults_to_printing_without_database_evaluation():
    args, env = build_command("convert-postgres", {"schema": "/tmp/schema.sql"})
    assert args == [
        "convert",
        "postgres",
        "--schema=/tmp/schema.sql",
        "--out=-",
        "--url=",
    ]
    assert env == {}
    with pytest.raises(ValueError, match="schema"):
        build_command("convert-mysql", {})


def test_catalog_has_unique_flags_and_boolean_copy_option():
    for command in COMMANDS:
        names = [option["name"] for option in command["options"]]
        assert len(names) == len(set(names))
    fetch = COMMANDS[0]
    assert (
        next(option for option in fetch["options"] if option["name"] == "use-copy")[
            "kind"
        ]
        == "bool"
    )


def test_staged_transfer_and_dialect_specific_options_are_pruned():
    from molt_ui.core.wizard import normalize_options

    options, omitted = normalize_options(
        "fetch",
        {
            "source": "mysql://source/db",
            "target": "postgres://target/db",
            "mode": "export-only",
            "direct-copy": True,
            "bucket-path": "s3://bucket",
            "source-cdb": "oracle://cdb",
            "pglogical-replication-slot-name": "slot",
            "require-empty-target": True,
        },
    )
    assert "direct-copy" not in options
    assert options["bucket-path"] == "s3://bucket"
    assert set(omitted) == {
        "direct-copy",
        "source-cdb",
        "pglogical-replication-slot-name",
        "require-empty-target",
    }


def test_recreate_options_only_survive_when_recreating_tables():
    from molt_ui.core.wizard import normalize_options

    options = {
        "table-handling": "none",
        "dropped-constraints-file": "/tmp/constraints.sql",
    }
    assert "dropped-constraints-file" not in normalize_options("fetch", options)[0]
    options["table-handling"] = "drop-on-target-and-recreate"
    assert "dropped-constraints-file" in normalize_options("fetch", options)[0]


def test_connection_type_and_enum_validation_happen_before_preview():
    from molt_ui.core.wizard import normalize_options

    with pytest.raises(ValueError):
        normalize_options("fetch", {"source": True})
    with pytest.raises(ValueError):
        normalize_options("fetch", {"mode": "invalid"})


def test_wizard_exposes_real_defaults_and_required_fields(monkeypatch):
    from molt_ui.core.wizard import wizard_catalog

    monkeypatch.delenv("MOLT_SOURCE", raising=False)
    monkeypatch.delenv("MOLT_TARGET", raising=False)
    catalog = {
        command["id"]: {option["name"]: option for option in command["options"]}
        for command in wizard_catalog()
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
    assert catalog["convert-postgres"]["out"]["default"] == "-"
    assert catalog["convert-postgres"]["url"]["default"] == ""
    monkeypatch.setenv("MOLT_SOURCE", "postgres://example/db")
    fetch = next(command for command in wizard_catalog() if command["id"] == "fetch")
    source = next(option for option in fetch["options"] if option["name"] == "source")
    assert source["required"] is False
    assert source["from_environment"] is True
    assert (
        source["default"] == ""
    )  # Do not expose inherited credentials in catalog metadata.


def test_explicit_source_selection_filters_options_without_a_uri():
    from molt_ui.core.wizard import normalize_options

    options, removed = normalize_options(
        "fetch",
        {
            "oracle-application-users": "app",
            "pglogical-replication-slot-name": "slot",
            "source-cdb": "user=app password=example",
        },
        source_kind="oracle",
    )
    assert options["oracle-application-users"] == "app"
    assert options["source-cdb"] == "user=app password=example"
    assert removed == ["pglogical-replication-slot-name"]
    options, removed = normalize_options(
        "fetch", {"oracle-application-users": "app"}, source_kind="mysql"
    )
    assert options == {}
    assert removed == ["oracle-application-users"]
    with pytest.raises(ValueError, match="does not match"):
        normalize_options(
            "fetch", {"source": "mysql://example/db"}, source_kind="postgres"
        )
    with pytest.raises(ValueError, match="Choose PostgreSQL"):
        normalize_options("fetch", {}, source_kind="invalid")


def test_logging_metrics_and_telemetry_have_dedicated_wizard_tabs():
    from molt_ui.core.wizard import wizard_catalog

    for command in wizard_catalog():
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
def test_logging_dropdown_levels_are_valid_and_preserved_in_argv(level):
    from molt_ui.core.wizard import wizard_catalog

    command = next(item for item in wizard_catalog() if item["id"] == "verify")
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
    )
    assert "--logging=" + level in arguments


def test_logging_dropdown_rejects_unknown_levels():
    from molt_ui.core.wizard import normalize_options

    with pytest.raises(ValueError, match="valid value for --logging"):
        normalize_options("fetch", {"logging": "verbose"})


def test_disabling_logging_uses_the_flag_without_appearing_in_the_level_choices():
    from molt_ui.core.wizard import wizard_catalog, normalize_options

    options = next(command for command in wizard_catalog() if command["id"] == "fetch")[
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
    )
    assert "--logging=disabled" in arguments
    with pytest.raises(ValueError):
        normalize_options("fetch", {"logging": ""})


@pytest.mark.parametrize("command", ["fetch", "verify"])
def test_log_file_preserves_cli_default_unless_explicitly_overridden(command):
    from molt_ui.core.wizard import wizard_catalog

    options = {"source": "postgres://source/db", "target": "postgres://target/db"}
    args, _ = build_command(command, options)
    assert not any(argument.startswith("--log-file=") for argument in args)
    definition = next(item for item in wizard_catalog() if item["id"] == command)
    log_file = next(
        option for option in definition["options"] if option["name"] == "log-file"
    )
    assert log_file["default"] == ""
    assert command + "-{datetime}.log" in log_file["default_label"]
    args, _ = build_command(command, {**options, "log-file": "stdout"})
    assert "--log-file=stdout" in args
    args, _ = build_command(command, {**options, "log-file": "/tmp/custom.log"})
    assert "--log-file=/tmp/custom.log" in args

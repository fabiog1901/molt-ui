import shlex

import pytest

from molt_ui.core.commands import build_command, build_plan
from molt_ui.core.models import CommandCatalog, CommandSpec, OptionSpec


def test_credentials_and_literal_arguments_are_preserved(command_catalog):
    options = {
        "source": "postgres://user:password@source/db",
        "target": "postgres://target/db",
        "direct-copy": True,
        "table-filter": "users; echo test",
        "table-concurrency": "2",
    }
    plan = build_plan("/path with spaces/molt", "fetch", options, environment={}, catalog=command_catalog)
    assert plan.argv == (
        "/path with spaces/molt", "fetch", "--direct-copy=true",
        "--table-filter=users; echo test", "--table-concurrency=2",
    )
    assert plan.environment["MOLT_SOURCE"] == options["source"]
    assert plan.options == options
    assert shlex.split(plan.invocation)[-2] == "--table-filter=users; echo test"


@pytest.mark.parametrize("options", [
    {"table-concurrency": "two"},
    {"mode": "new-mode"},
    {"logging": "new-level"},
    {"direct-copy": True, "bucket-path": "s3://bucket", "local-path": "/tmp/staging"},
    {"source": "mysql://source/db", "oracle-application-users": "app"},
])
def test_command_semantics_are_forwarded_to_molt_without_pruning(command_catalog, options):
    plan = build_plan("molt", "fetch", options, environment={}, catalog=command_catalog)
    assert plan.options == options
    assert plan.omitted == ()
    for name, value in options.items():
        if name != "source":
            text = str(value).lower() if isinstance(value, bool) else value
            assert f"--{name}={text}" in plan.argv


def test_missing_required_parameters_are_left_to_molt(command_catalog):
    assert build_command("fetch", {}, environment={}, catalog=command_catalog) == (["fetch"], {})
    assert build_command("convert-mysql", {}, environment={}, catalog=command_catalog) == (["convert", "mysql"], {})


def test_inherited_environment_and_explicit_overrides_are_recorded(command_catalog):
    plan = build_plan("molt", "fetch", {"source": "explicit"}, environment={
        "MOLT_SOURCE": "inherited", "MOLT_TARGET": "target", "UNRELATED": "ignored",
    }, catalog=command_catalog)
    assert plan.environment == {"MOLT_SOURCE": "explicit", "MOLT_TARGET": "target"}
    assert build_command("verify", {"rows": False}, environment={}, catalog=command_catalog)[0] == ["verify", "--rows=false"]


def test_help_ignores_configuration_and_does_not_require_connections(command_catalog):
    assert build_command("fetch", {"unknown": "ignored"}, help_only=True, catalog=command_catalog) == (["fetch", "--help"], {})


def test_unknown_catalog_entries_produce_a_drift_error(command_catalog):
    with pytest.raises(ValueError, match="catalog"):
        build_command("fetch", {"new-option": "value"}, catalog=command_catalog)
    with pytest.raises(ValueError, match="Unknown molt command"):
        build_command("missing-command", {}, catalog=command_catalog)


@pytest.mark.parametrize("options", [{"source": "invalid\x00text"}, {"mode": 123}])
def test_values_that_cannot_use_our_argv_contract_are_rejected(command_catalog, options):
    with pytest.raises(ValueError):
        build_command("fetch", options, catalog=command_catalog)


def test_conversion_uses_only_explicit_flags_and_preserves_empty_values(command_catalog):
    assert build_command("convert-postgres", {"schema": "/tmp/schema.sql"}, catalog=command_catalog) == (
        ["convert", "postgres", "--schema=/tmp/schema.sql"], {},
    )
    assert build_command("convert-postgres", {"out": "-", "url": ""}, catalog=command_catalog)[0] == [
        "convert", "postgres", "--out=-", "--url=",
    ]


def test_new_command_and_environment_flag_need_no_builder_configuration():
    definition = CommandSpec(id="future", arguments=("future", "run"), options=(
        OptionSpec(name="token", kind="string", description="Token", default="", environment_variable="MOLT_TOKEN"),
        OptionSpec(name="future-switch", kind="bool", description="Switch", default=False),
    ))
    catalog = CommandCatalog(schema_version=1, commands=(definition,))
    plan = build_plan(
        "molt", "future", {"token": "exact", "future-switch": False},
        environment={}, catalog=catalog,
    )
    assert plan.argv == ("molt", "future", "run", "--future-switch=false")
    assert plan.environment == {"MOLT_TOKEN": "exact"}


def test_catalog_has_unique_flags_and_boolean_copy_option(command_catalog):
    for command in command_catalog.commands:
        assert len({option.name for option in command.options}) == len(command.options)
    fetch = next(spec for spec in command_catalog.commands if spec.id == "fetch")
    assert next(option for option in fetch.options if option.name == "use-copy").kind == "bool"

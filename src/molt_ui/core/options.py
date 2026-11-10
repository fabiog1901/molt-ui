"""UI-independent defaults, accepted values, requirements, and option rules."""

from collections.abc import Mapping
import os

from .catalog import command_spec, load_catalog
from .models import ApplicabilityRule, CommandSpec, OptionSpec

CONNECTION_ENV = {
    "source": "MOLT_SOURCE",
    "target": "MOLT_TARGET",
    "source-cdb": "MOLT_SOURCE_CDB",
}
ALLOWED_VALUES = {
    "logging": ("trace", "debug", "info", "warn", "error", "fatal", "panic", "", "disabled"),
    "mode": ("data-load", "export-only", "import-only"),
    "table-handling": ("none", "drop-on-target-and-recreate", "truncate-if-exists"),
    "compression": ("gzip", "none"),
    "format": ("original", "target", "crdb"),
}
STAGING = {
    "bucket-path", "local-path", "local-path-crdb-access-addr", "local-path-listen-addr",
    "compression", "cleanup", "flush-rows", "flush-size", "assume-role", "import-assume-role",
    "import-batch-size", "import-region", "use-implicit-auth", "use-copy",
}


def source_dialect(source: str) -> str:
    scheme = source.partition(":")[0].lower()
    return {
        "postgres": "postgres", "postgresql": "postgres", "mysql": "mysql",
        "oracle": "oracle", "cockroach": "cockroachdb", "cockroachdb": "cockroachdb",
    }.get(scheme, "unknown")


def option_rules(command: str, name: str) -> tuple[ApplicabilityRule, ...]:
    tests = []
    if command == "fetch":
        if name == "direct-copy":
            tests.append("data-load")
        if name in STAGING:
            tests.append("staged")
        if name in {"assume-role", "import-assume-role", "import-region", "use-implicit-auth"}:
            tests.append("bucket")
        if name in {"local-path-crdb-access-addr", "local-path-listen-addr"}:
            tests.append("local")
        if name in {"dropped-constraints-file", "dropped-indexes-file"}:
            tests.append("recreate")
        if name == "require-empty-target":
            tests.append("empty-target")
    rules = [ApplicabilityRule(test=test) for test in tests]
    if name.startswith("oracle-") or name in {"source-cdb", "source-oracle-wallet-location"}:
        rules.append(ApplicabilityRule(test="dialect", value="oracle"))
    if name.startswith("pglogical-") or name in {"flatten-partitioned-tables", "use-stats-based-sharding"}:
        rules.append(ApplicabilityRule(test="dialect", value="postgres"))
    return tuple(rules)


def resolve_command(specification: CommandSpec, environment: Mapping[str, str]) -> CommandSpec:
    options = []
    for option in specification.options:
        name = option.name
        env_name = CONNECTION_ENV.get(name)
        default = option.default
        if specification.id.startswith("convert-"):
            if name == "out":
                default = "-"
            elif name == "url":
                default = ""
        required = name == "schema" or (
            name in {"source", "target"}
            and specification.id in {"fetch", "verify"}
            and not environment.get(CONNECTION_ENV[name])
        )
        options.append(option.model_copy(update={
            "default": default,
            "allowed_values": ALLOWED_VALUES.get(name, ()),
            "environment_variable": env_name,
            "from_environment": bool(env_name and environment.get(env_name)),
            "required": required,
            "default_by_source": {"postgres": True} if name == "use-stats-based-sharding" else {},
            "rules": option_rules(specification.id, name),
        }))
    return specification.model_copy(update={
        "options": tuple(options),
        "default_source_dialect": source_dialect(environment.get("MOLT_SOURCE", "")),
    })


def command_definitions(*, environment: Mapping[str, str] | None = None) -> tuple[CommandSpec, ...]:
    environment = os.environ if environment is None else environment
    return tuple(resolve_command(spec, environment) for spec in load_catalog().commands)


def applies(option: OptionSpec, values: dict, dialect: str) -> bool:
    mode = values.get("mode", "data-load")
    direct = mode == "data-load" and values.get("direct-copy") is True
    for rule in option.rules:
        test = rule.test
        if test == "data-load" and mode != "data-load":
            return False
        if test == "staged" and direct:
            return False
        if test == "bucket" and not values.get("bucket-path"):
            return False
        if test == "local" and not values.get("local-path"):
            return False
        if test == "recreate" and (
            values.get("table-handling") != "drop-on-target-and-recreate" or values.get("fetch-id")
        ):
            return False
        if test == "empty-target" and (
            values.get("table-handling") in {"truncate-if-exists", "drop-on-target-and-recreate"}
            or values.get("fetch-id") or values.get("continuation-token") or mode == "export-only"
        ):
            return False
        if test == "dialect" and dialect != "unknown" and dialect != rule.value:
            return False
    return True


def normalize_options(
    command: str,
    options: dict,
    *,
    source_kind: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict, list[str]]:
    environment = os.environ if environment is None else environment
    definition = resolve_command(command_spec(command), environment)
    known = {option.name: option for option in definition.options}
    if options.keys() - known.keys():
        raise ValueError("Unknown option for the selected command.")
    for name, value in options.items():
        if known[name].kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"--{name} must be true or false.")
        elif not isinstance(value, str):
            raise ValueError(f"--{name} must be text.")
        if known[name].allowed_values and value not in known[name].allowed_values:
            raise ValueError(f"Choose a valid value for --{name}.")
    dialect = source_dialect(options.get("source") or environment.get("MOLT_SOURCE", ""))
    if source_kind is not None:
        if source_kind not in {"postgres", "oracle", "mysql"}:
            raise ValueError("Choose PostgreSQL, Oracle, or MySQL as the source database.")
        if dialect not in {"unknown", source_kind} and not (
            source_kind == "postgres" and dialect == "cockroachdb"
        ):
            raise ValueError("The source connection does not match the selected source database.")
        dialect = source_kind
    result, removed = dict(options), []
    while True:
        invalid = [name for name in result if not applies(known[name], result, dialect)]
        if not invalid:
            return result, removed
        for name in invalid:
            removed.append(name)
            del result[name]

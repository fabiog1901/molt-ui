"""Validated request and command-field models shared by the frontends.

These describe frontend inputs and display metadata. Process output and shared
application state belong in core.models, so the core never imports a frontend.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class FrontendModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartCommand(FrontendModel):
    command: str
    options: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    help_only: bool = False
    source_kind: str | None = None


class OptionChoice(FrontendModel):
    value: str
    label: str


class ApplicabilityRule(FrontendModel):
    test: Literal[
        "data-load", "staged", "bucket", "local", "recreate", "empty-target", "dialect"
    ]
    value: str | None = None


class CommandOption(FrontendModel):
    name: str
    kind: Literal["string", "int", "bool"]
    description: str
    advanced: bool
    secret: bool
    default: StrictStr | StrictBool
    required: bool
    environment_variable: str | None = None
    from_environment: bool = False
    default_label: str = ""
    default_by_source: dict[str, StrictStr | StrictBool] = Field(default_factory=dict)
    stage: Literal[
        "operation", "connections", "common", "advanced", "logging", "metrics"
    ]
    rules: list[ApplicabilityRule] = Field(default_factory=list)
    label: str
    choices: list[OptionChoice] = Field(default_factory=list)
    brief: str


class CommandDefinition(FrontendModel):
    id: str
    label: str
    arguments: list[str]
    options: list[CommandOption]
    default_source_dialect: str = "unknown"

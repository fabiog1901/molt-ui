"""Resolve runtime configuration independently of frontend and service modules."""

from collections.abc import Mapping
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

LOCAL_EXECUTABLE = Path(__file__).resolve().parents[2] / "molt" / "molt"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    executable: str
    database: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "Settings":
        environment = os.environ if environment is None else environment
        executable = environment.get("MOLT_EXECUTABLE")
        if executable is None:
            executable = str(LOCAL_EXECUTABLE) if LOCAL_EXECUTABLE.is_file() else "molt"
        return cls(
            executable=executable,
            database=environment.get(
                "MOLT_DATABASE", str(Path.cwd() / ".data" / "molt-ui.sqlite3")
            ),
        )

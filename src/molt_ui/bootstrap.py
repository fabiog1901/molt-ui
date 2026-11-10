"""Construct the application service and its concrete adapters in one place."""

import os

from .config import Settings
from .core.service import MoltService
from .molt_process import MoltProcess
from .repo import Repo


def create_service(settings: Settings | None = None) -> MoltService:
    environment = dict(os.environ)
    settings = (
        settings if settings is not None else Settings.from_environment(environment)
    )
    return MoltService(
        MoltProcess(settings.executable, environment=environment),
        Repo(settings.database),
        environment=environment,
    )

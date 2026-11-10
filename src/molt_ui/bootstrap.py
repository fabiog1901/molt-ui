"""Construct the application service and its concrete adapters in one place."""

import logging
import os

from .catalog_update import refresh_catalog
from .config import Settings
from .core.errors import MoltError
from .core.service import MoltService
from .molt_process import MoltProcess
from .repo import Repo

logger = logging.getLogger(__name__)


def create_service(settings: Settings | None = None) -> MoltService:
    environment = dict(os.environ)
    settings = (
        settings if settings is not None else Settings.from_environment(environment)
    )
    process = MoltProcess(settings.executable, environment=environment)
    repo = Repo(settings.database)
    try:
        catalog = refresh_catalog(process, repo)
    except MoltError as exc:
        logger.warning("%s", exc)
        catalog = None
    return MoltService(
        process,
        repo,
        catalog=catalog,
        environment=environment,
    )

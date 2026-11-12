"""Application errors shared by adapters and the service."""


class MoltError(RuntimeError):
    """A molt operation could not be performed."""


class RunConflict(MoltError):
    """A run's whole-second timestamp is already present in history."""

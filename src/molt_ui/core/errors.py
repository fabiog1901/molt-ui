"""Application errors shared by adapters and the service."""


class MoltError(RuntimeError):
    """A molt operation could not be performed."""

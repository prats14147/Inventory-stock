"""backend/app/services/errors.py"""


class NotFoundError(Exception):
    """Raised when a requested entity (product, store, etc.) doesn't exist."""


class InvalidRequestError(Exception):
    """Raised when request parameters are semantically invalid (e.g. bad date range)."""

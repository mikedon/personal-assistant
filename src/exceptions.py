"""Custom exceptions for the personal assistant application."""


class AccountNotFoundError(ValueError):
    """Raised when an account_id is not found in configuration."""

    pass

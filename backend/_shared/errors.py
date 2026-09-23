"""
Errors that services raise to send a specific HTTP status to the client.

Business logic raises these without knowing about HTTP; the @api_handler
wrapper in http.py turns them into {"error": str, "details": {}} responses.
"""


class AppError(Exception):
    """Base class. Subclasses set the status code."""

    status = 500

    def __init__(self, message: str, details: dict | None = None) -> None:
        """Store a short message for the client and optional field-level details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(AppError):
    """400: the request is malformed or a field is invalid."""

    status = 400


class Unauthorized(AppError):
    """401: no valid token (missing, invalid or expired) or bad credentials."""

    status = 401


class Forbidden(AppError):
    """403: logged in, but not allowed to do this."""

    status = 403


class NotFound(AppError):
    """404: the route or record does not exist."""

    status = 404


class Conflict(AppError):
    """409: the request clashes with the current state (duplicate, stale version, archived...)."""

    status = 409

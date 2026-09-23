"""
Helpers for reading Lambda Function URL events and building HTTP responses.

Every service handler is wrapped with @api_handler, which:
- turns AppError subclasses into {"error": str, "details": {}} with the right status,
- turns anything unexpected into a generic 500 (details go to the log only),
- writes one structured JSON log line per request.
"""

import base64
import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Any, Callable

from _shared.errors import AppError, ValidationError

logger = logging.getLogger(__name__)


def _to_json(value: Any) -> Any:
    """Convert values json.dumps cannot handle (dates, decimals) into plain types."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def json_response(status: int, data: Any) -> dict:
    """Build a Lambda response with a JSON body."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data, default=_to_json),
    }


def error_response(status: int, message: str, details: dict | None = None) -> dict:
    """Build an error response in the standard {"error", "details"} shape."""
    return json_response(status, {"error": message, "details": details or {}})


def no_content() -> dict:
    """Build an empty 204 response (used for deletes)."""
    return {"statusCode": 204, "headers": {}, "body": ""}


def get_method(event: dict) -> str:
    """Return the HTTP method, e.g. "GET"."""
    return event.get("requestContext", {}).get("http", {}).get("method", "GET").upper()


def parse_path(event: dict, service: str) -> str:
    """
    Return the request path relative to the service, e.g. "/login".

    In the cloud, CloudFront forwards the full path ("/api/auth/login"), while
    the local proxy strips the prefix ("/login"). Both become "/login" here.
    """
    path = event.get("rawPath") or "/"
    prefix = f"/api/{service}"
    if path == prefix or path.startswith(prefix + "/"):
        path = path[len(prefix):]
    return "/" + path.strip("/")


def get_header(event: dict, name: str) -> str:
    """Return a request header by name (case-insensitive), or "" if missing."""
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value or ""
    return ""


def get_query_params(event: dict) -> dict[str, str]:
    """Return the query string parameters as a dict."""
    return event.get("queryStringParameters") or {}


def parse_json_body(event: dict) -> dict:
    """
    Parse the request body as a JSON object.

    Raises:
        ValidationError: if the body is not valid JSON or is not an object.
    """
    body = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        data = json.loads(body) if body.strip() else {}
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Request body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    return data


def _log_request(event: dict, context: Any, status: int, started: float) -> None:
    """Write one JSON log line describing the request (never headers or body)."""
    http = event.get("requestContext", {}).get("http", {})
    logger.info(json.dumps({
        "request_id": getattr(context, "aws_request_id", None),
        "user_id": event.get("user_id"),  # set by auth.require_user when a token is checked
        "method": http.get("method"),
        "path": event.get("rawPath"),
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }))


def api_handler(func: Callable[[dict, Any], dict]) -> Callable[[dict, Any], dict]:
    """Decorator for Lambda handlers: maps errors to responses and logs each request."""

    @wraps(func)
    def wrapper(event: dict, context: Any = None) -> dict:
        started = time.perf_counter()
        try:
            response = func(event, context)
        except AppError as exc:
            response = error_response(exc.status, exc.message, exc.details)
        except Exception:  # pylint: disable=broad-except
            # Full stack trace to the log only; the client gets a generic message.
            logger.exception("Unhandled error")
            response = error_response(500, "Internal server error")
        _log_request(event, context, response["statusCode"], started)
        return response

    return wrapper

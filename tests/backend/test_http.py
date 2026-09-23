"""
Unit tests for backend/_shared/http.py: path parsing, routing, JSON bodies,
responses and the @api_handler error mapping.
"""

import base64
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from _shared import http
from _shared.errors import Conflict, NotFound, ValidationError


def event_for(path: str | None) -> dict:
    """A minimal event with only rawPath set."""
    return {"rawPath": path} if path is not None else {}


# ---------- parse_path ----------

@pytest.mark.parametrize(("raw_path", "expected"), [
    ("/api/auth/login", "/login"),     # cloud: CloudFront forwards the full path
    ("/login", "/login"),              # local proxy: prefix already stripped
    ("/api/auth", "/"),                # service root
    ("/api/auth/", "/"),
    ("/api/auth/login/", "/login"),    # trailing slash is ignored
    ("/", "/"),
    ("", "/"),
    (None, "/"),                       # no rawPath at all
])
def test_parse_path(raw_path, expected):
    """The /api/<service> prefix is removed when present, and slashes are normalized."""
    assert http.parse_path(event_for(raw_path), "auth") == expected


def test_parse_path_keeps_similar_service_prefix():
    """/api/authx is not the auth service, so its path is left alone (and will not match a route)."""
    assert http.parse_path(event_for("/api/authx/login"), "auth") == "/api/authx/login"


def test_parse_path_nested_ids():
    """Deeper incident paths keep their ids."""
    assert http.parse_path(event_for("/api/incidents/42/notes/7"), "incidents") == "/42/notes/7"


# ---------- match_route ----------

def list_view() -> str:
    """Stand-in route handler."""
    return "list"


def detail_view() -> str:
    """Stand-in route handler."""
    return "detail"


def note_view() -> str:
    """Stand-in route handler."""
    return "note"


def options_view() -> str:
    """Stand-in route handler."""
    return "options"


ROUTES = [
    ("GET", "/", list_view),
    ("GET", "/options", options_view),
    ("GET", "/{id}", detail_view),
    ("PUT", "/{id}/notes/{note_id}", note_view),
]


def test_match_route_root():
    """"/" matches the root route with no params."""
    assert http.match_route(ROUTES, "GET", "/") == (list_view, {})


def test_match_route_placeholder_becomes_int():
    """{id} placeholders match digits and are converted to int."""
    assert http.match_route(ROUTES, "GET", "/42") == (detail_view, {"id": 42})


def test_match_route_several_placeholders():
    """Several placeholders in one pattern are all captured."""
    assert http.match_route(ROUTES, "PUT", "/42/notes/7") == (note_view, {"id": 42, "note_id": 7})


def test_match_route_fixed_segment_before_placeholder():
    """A literal segment ("options") is matched by the literal route listed first."""
    assert http.match_route(ROUTES, "GET", "/options") == (options_view, {})


@pytest.mark.parametrize(("method", "path"), [
    ("GET", "/abc"),            # placeholders accept digits only
    ("GET", "/-1"),
    ("GET", "/4.2"),
    ("POST", "/42"),            # right path, wrong method
    ("GET", "/42/extra"),       # too many segments
    ("PUT", "/42/notes"),       # too few segments
    ("GET", "/api/authx/login"),
])
def test_match_route_no_match_raises_not_found(method, path):
    """Anything that does not match raises NotFound (404)."""
    with pytest.raises(NotFound):
        http.match_route(ROUTES, method, path)


def test_match_route_non_ascii_digit_is_not_found():
    """A superscript digit passes str.isdigit() and then crashes int()."""
    with pytest.raises(NotFound):
        http.match_route(ROUTES, "GET", "/²")


# ---------- parse_json_body ----------

def test_parse_json_body_object():
    """A JSON object is returned as a dict."""
    assert http.parse_json_body({"body": '{"title": "x"}'}) == {"title": "x"}


@pytest.mark.parametrize("body", [None, "", "   "])
def test_parse_json_body_empty_is_empty_dict(body):
    """No body (or only whitespace) is treated as {} so validation reports missing fields."""
    assert http.parse_json_body({"body": body}) == {}


def test_parse_json_body_base64():
    """Function URLs may base64-encode the body."""
    encoded = base64.b64encode(json.dumps({"a": 1}).encode()).decode()
    assert http.parse_json_body({"body": encoded, "isBase64Encoded": True}) == {"a": 1}


@pytest.mark.parametrize(("event", "message"), [
    ({"body": "{not json"}, "Request body must be valid JSON"),
    ({"body": "not base64!!", "isBase64Encoded": True}, "Request body must be valid JSON"),
    ({"body": base64.b64encode(b"\xff\xfe").decode(), "isBase64Encoded": True}, "Request body must be valid JSON"),
    ({"body": "[1, 2]"}, "Request body must be a JSON object"),
    ({"body": '"text"'}, "Request body must be a JSON object"),
    ({"body": "null"}, "Request body must be a JSON object"),
])
def test_parse_json_body_errors(event, message):
    """Invalid JSON and non-object JSON become a 400."""
    with pytest.raises(ValidationError) as caught:
        http.parse_json_body(event)
    assert caught.value.message == message


# ---------- small readers ----------

def test_get_method_defaults_to_get_and_uppercases():
    """Method is uppercased; a missing requestContext means GET."""
    assert http.get_method({"requestContext": {"http": {"method": "post"}}}) == "POST"
    assert http.get_method({}) == "GET"


def test_get_header_is_case_insensitive():
    """Header names are matched case-insensitively; missing -> ""."""
    event = {"headers": {"Authorization": "Bearer x"}}
    assert http.get_header(event, "authorization") == "Bearer x"
    assert http.get_header(event, "x-missing") == ""
    assert http.get_header({"headers": None}, "authorization") == ""


def test_get_query_params_none_is_empty_dict():
    """Function URLs send null when there is no query string."""
    assert http.get_query_params({"queryStringParameters": None}) == {}


# ---------- responses ----------

def test_json_response_serializes_dates_and_decimals():
    """Dates become ISO strings and Decimals become floats."""
    response = http.json_response(200, {
        "at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc), "day": date(2026, 1, 2), "hours": Decimal("1.25"),
    })
    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {"at": "2026-01-02T03:04:00+00:00", "day": "2026-01-02", "hours": 1.25}


def test_json_response_unknown_type_raises():
    """Unexpected types are not silently stringified."""
    with pytest.raises(TypeError):
        http.json_response(200, {"x": object()})


def test_error_response_shape():
    """Errors always have "error" and "details"."""
    response = http.error_response(409, "Conflict here")
    assert json.loads(response["body"]) == {"error": "Conflict here", "details": {}}


# ---------- api_handler ----------

def test_api_handler_maps_app_errors_to_status():
    """AppError subclasses become their status with the standard body."""
    @http.api_handler
    def handler(event, context=None):
        raise Conflict("Stale", {"version": "old"})

    response = handler({"rawPath": "/x"})
    assert response["statusCode"] == 409
    assert json.loads(response["body"]) == {"error": "Stale", "details": {"version": "old"}}


def test_api_handler_hides_unexpected_errors(caplog):
    """Unexpected exceptions become a generic 500; the real message goes to the log only."""
    @http.api_handler
    def handler(event, context=None):
        raise RuntimeError("database password is hunter2")

    response = handler({"rawPath": "/x"})
    assert response["statusCode"] == 500
    assert json.loads(response["body"]) == {"error": "Internal server error", "details": {}}
    assert "hunter2" not in response["body"]


def test_api_handler_logs_one_line_without_body(caplog):
    """One JSON log line per request with method/path/status, and never the body or headers."""
    @http.api_handler
    def handler(event, context=None):
        return http.json_response(200, {})

    event = {
        "rawPath": "/api/auth/login", "requestContext": {"http": {"method": "POST"}},
        "headers": {"authorization": "Bearer secret-token"}, "body": '{"password": "p4ss"}',
    }
    with caplog.at_level("INFO", logger="_shared.http"):
        handler(event)
    lines = [json.loads(record.getMessage()) for record in caplog.records if record.name == "_shared.http"]
    assert len(lines) == 1
    assert lines[0]["method"] == "POST" and lines[0]["path"] == "/api/auth/login" and lines[0]["status"] == 200
    assert "secret-token" not in caplog.text and "p4ss" not in caplog.text

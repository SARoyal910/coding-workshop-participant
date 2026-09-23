"""
Auth service routing. Paths are relative to /api/auth:

    POST /register -> 201 {token, user}  @acme.inc only, always role=employee
    POST /login    -> 200 {token, user}
    GET  /me       -> 200 {user}         requires a Bearer token
    POST /refresh  -> 200 {token, user}  requires a still-valid Bearer token
    GET  /health   -> 200 or 503         checks the database
"""

import logging
from typing import Any

import service
from _shared.auth import require_user
from _shared.errors import NotFound
from _shared.http import api_handler, get_method, json_response, parse_json_body, parse_path

logging.getLogger().setLevel(logging.INFO)

SERVICE = "auth"


def register(event: dict) -> dict:
    """POST /register"""
    return json_response(201, service.register(parse_json_body(event)))


def login(event: dict) -> dict:
    """POST /login"""
    return json_response(200, service.login(parse_json_body(event)))


def me(event: dict) -> dict:
    """GET /me"""
    caller = require_user(event)
    return json_response(200, {"user": service.current_user(caller["id"])})


def refresh(event: dict) -> dict:
    """POST /refresh"""
    caller = require_user(event)
    return json_response(200, service.refresh(caller["id"]))


def health(event: dict) -> dict:
    """GET /health"""
    if service.is_healthy():
        return json_response(200, {"status": "ok"})
    return json_response(503, {"status": "unavailable"})


ROUTES = {
    ("POST", "/register"): register,
    ("POST", "/login"): login,
    ("GET", "/me"): me,
    ("POST", "/refresh"): refresh,
    ("GET", "/health"): health,
}


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: find the route for this method and path and run it."""
    method = get_method(event)
    path = parse_path(event, SERVICE)
    route = ROUTES.get((method, path))
    if route is None:
        raise NotFound(f"No route for {method} {path}")
    return route(event)

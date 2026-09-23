"""
Dashboard service routing. Paths are relative to /api/dashboard:

    GET / -> 200 role-specific metrics   requires a Bearer token
"""

import logging
from typing import Any

import service
from _shared.auth import require_user
from _shared.http import api_handler, get_method, json_response, match_route, parse_path

logging.getLogger().setLevel(logging.INFO)

SERVICE = "dashboard"


def get_dashboard(event: dict, user: dict) -> dict:
    """GET /"""
    return json_response(200, service.get_dashboard(user))


ROUTES = [
    ("GET", "/", get_dashboard),
]


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: check the token, find the route and run it."""
    route, _ = match_route(ROUTES, get_method(event), parse_path(event, SERVICE))
    return route(event, require_user(event))

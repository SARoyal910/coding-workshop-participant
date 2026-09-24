"""
Dashboard service routing. Paths are relative to /api/dashboard:

    GET /              -> 200 role-specific metrics   requires a Bearer token
    GET /missed-shifts -> 200 {engineer, total, items} admin: everyone or ?engineer_id=; engineer: their own
"""

import logging
from typing import Any

import service
from _shared.auth import require_user
from _shared.http import api_handler, get_method, get_query_params, json_response, match_route, parse_path

logging.getLogger().setLevel(logging.INFO)

SERVICE = "dashboard"


def get_dashboard(event: dict, user: dict) -> dict:
    """GET /"""
    return json_response(200, service.get_dashboard(user))


def missed_shifts(event: dict, user: dict) -> dict:
    """GET /missed-shifts"""
    return json_response(200, service.missed_shifts(user, get_query_params(event)))


ROUTES = [
    ("GET", "/", get_dashboard),
    ("GET", "/missed-shifts", missed_shifts),
]


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: check the token, find the route and run it."""
    route, _ = match_route(ROUTES, get_method(event), parse_path(event, SERVICE))
    return route(event, require_user(event))

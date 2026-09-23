"""
Engineers service routing. Paths are relative to /api/engineers, and every
route needs a Bearer token.

    GET /                    -> 200 {items, total, page, page_size}  admin or engineer; profiles + workload stats
    POST /                   -> 201 engineer   admin creates an engineer account
    PUT /{id}                -> 200 engineer   admin edits name, specialty, shift, phone
    PUT /{id}/availability   -> 200 engineer   admin, or the engineer themselves
"""

import logging
from typing import Any

import service
from _shared.auth import require_user
from _shared.http import (
    api_handler,
    get_method,
    get_query_params,
    json_response,
    match_route,
    parse_json_body,
    parse_path,
)

logging.getLogger().setLevel(logging.INFO)

SERVICE = "engineers"
ADMIN = ("admin",)
STAFF = ("admin", "engineer")


def list_engineers(event: dict, params: dict) -> dict:
    """GET /"""
    require_user(event, roles=STAFF)
    return json_response(200, service.list_engineers(get_query_params(event)))


def create_engineer(event: dict, params: dict) -> dict:
    """POST /"""
    require_user(event, roles=ADMIN)
    return json_response(201, service.create_engineer(parse_json_body(event)))


def update_engineer(event: dict, params: dict) -> dict:
    """PUT /{id}"""
    require_user(event, roles=ADMIN)
    return json_response(200, service.update_engineer(params["id"], parse_json_body(event)))


def set_availability(event: dict, params: dict) -> dict:
    """PUT /{id}/availability"""
    user = require_user(event, roles=STAFF)
    return json_response(200, service.set_availability(user, params["id"], parse_json_body(event)))


ROUTES = [
    ("GET", "/", list_engineers),
    ("POST", "/", create_engineer),
    ("PUT", "/{id}", update_engineer),
    ("PUT", "/{id}/availability", set_availability),
]


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: find the route and run it (each route checks the caller's role)."""
    route, params = match_route(ROUTES, get_method(event), parse_path(event, SERVICE))
    return route(event, params)

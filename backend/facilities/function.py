"""
Facilities service routing. Paths are relative to /api/facilities, and every
route needs an admin's Bearer token.

    GET    /buildings                  -> 200 {items, total, page, page_size}  buildings with floors and seats
    POST   /buildings                  -> 201 building
    PUT    /buildings/{id}             -> 200 building
    DELETE /buildings/{id}             -> 204  (409 if it has incidents; also deletes its floors and seats)
    POST   /buildings/{id}/floors      -> 201 floor
    PUT    /floors/{id}                -> 200 floor
    DELETE /floors/{id}                -> 204  (409 if it has incidents; also deletes its seats)
    POST   /floors/{id}/seats          -> 201 seat
    PUT    /seats/{id}                 -> 200 seat
    DELETE /seats/{id}                 -> 204  (409 if it has incidents)
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
    no_content,
    parse_json_body,
    parse_path,
)

logging.getLogger().setLevel(logging.INFO)

SERVICE = "facilities"


def list_buildings(event: dict, params: dict) -> dict:
    """GET /buildings"""
    return json_response(200, service.list_buildings(get_query_params(event)))


def create_building(event: dict, params: dict) -> dict:
    """POST /buildings"""
    return json_response(201, service.create_building(parse_json_body(event)))


def update_building(event: dict, params: dict) -> dict:
    """PUT /buildings/{id}"""
    return json_response(200, service.update_building(params["id"], parse_json_body(event)))


def delete_building(event: dict, params: dict) -> dict:
    """DELETE /buildings/{id}"""
    service.delete_building(params["id"])
    return no_content()


def create_floor(event: dict, params: dict) -> dict:
    """POST /buildings/{id}/floors"""
    return json_response(201, service.create_floor(params["id"], parse_json_body(event)))


def update_floor(event: dict, params: dict) -> dict:
    """PUT /floors/{id}"""
    return json_response(200, service.update_floor(params["id"], parse_json_body(event)))


def delete_floor(event: dict, params: dict) -> dict:
    """DELETE /floors/{id}"""
    service.delete_floor(params["id"])
    return no_content()


def create_seat(event: dict, params: dict) -> dict:
    """POST /floors/{id}/seats"""
    return json_response(201, service.create_seat(params["id"], parse_json_body(event)))


def update_seat(event: dict, params: dict) -> dict:
    """PUT /seats/{id}"""
    return json_response(200, service.update_seat(params["id"], parse_json_body(event)))


def delete_seat(event: dict, params: dict) -> dict:
    """DELETE /seats/{id}"""
    service.delete_seat(params["id"])
    return no_content()


ROUTES = [
    ("GET", "/buildings", list_buildings),
    ("POST", "/buildings", create_building),
    ("PUT", "/buildings/{id}", update_building),
    ("DELETE", "/buildings/{id}", delete_building),
    ("POST", "/buildings/{id}/floors", create_floor),
    ("PUT", "/floors/{id}", update_floor),
    ("DELETE", "/floors/{id}", delete_floor),
    ("POST", "/floors/{id}/seats", create_seat),
    ("PUT", "/seats/{id}", update_seat),
    ("DELETE", "/seats/{id}", delete_seat),
]


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: find the route, check the caller is an admin, and run it."""
    route, params = match_route(ROUTES, get_method(event), parse_path(event, SERVICE))
    require_user(event, roles=("admin",))
    return route(event, params)

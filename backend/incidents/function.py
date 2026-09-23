"""
Incidents service routing. Paths are relative to /api/incidents, and every
route needs a Bearer token.

    GET  /                       -> 200 {items, total, page, page_size}
                                    ?page= &page_size= &status= &priority= &category=
                                    &building_id= &q= &archived=true &scope=mine|pool
    POST /                       -> 201 incident          report a new incident
    GET  /options                -> 200 form options      issue types, priorities, locations
    GET  /{id}                   -> 200 incident          with engineers, notes, events, allowed_actions
    PUT  /{id}                   -> 200 incident          edit title/description (needs version)
    POST /{id}/status            -> 200 incident          workflow transition (needs version)
    POST /{id}/notes             -> 201 note
    PUT  /{id}/notes/{note_id}   -> 200 note              author only
"""

import logging
from typing import Any

import service
from _shared.auth import require_user
from _shared.http import api_handler, get_method, get_query_params, json_response, match_route, parse_json_body, parse_path

logging.getLogger().setLevel(logging.INFO)

SERVICE = "incidents"


def list_incidents(event: dict, user: dict, params: dict) -> dict:
    """GET /"""
    return json_response(200, service.list_incidents(user, get_query_params(event)))


def create_incident(event: dict, user: dict, params: dict) -> dict:
    """POST /"""
    return json_response(201, service.create_incident(user, parse_json_body(event)))


def form_options(event: dict, user: dict, params: dict) -> dict:
    """GET /options"""
    return json_response(200, service.form_options())


def get_incident(event: dict, user: dict, params: dict) -> dict:
    """GET /{id}"""
    return json_response(200, service.get_incident(user, params["id"]))


def update_incident(event: dict, user: dict, params: dict) -> dict:
    """PUT /{id}"""
    return json_response(200, service.update_incident(user, params["id"], parse_json_body(event)))


def change_status(event: dict, user: dict, params: dict) -> dict:
    """POST /{id}/status"""
    return json_response(200, service.change_status(user, params["id"], parse_json_body(event)))


def add_note(event: dict, user: dict, params: dict) -> dict:
    """POST /{id}/notes"""
    return json_response(201, service.add_note(user, params["id"], parse_json_body(event)))


def edit_note(event: dict, user: dict, params: dict) -> dict:
    """PUT /{id}/notes/{note_id}"""
    return json_response(200, service.edit_note(user, params["id"], params["note_id"], parse_json_body(event)))


ROUTES = [
    ("GET", "/", list_incidents),
    ("POST", "/", create_incident),
    ("GET", "/options", form_options),
    ("GET", "/{id}", get_incident),
    ("PUT", "/{id}", update_incident),
    ("POST", "/{id}/status", change_status),
    ("POST", "/{id}/notes", add_note),
    ("PUT", "/{id}/notes/{note_id}", edit_note),
]


@api_handler
def handler(event: dict, context: Any = None) -> dict:
    """Lambda entry point: check the token, find the route and run it."""
    route, params = match_route(ROUTES, get_method(event), parse_path(event, SERVICE))
    user = require_user(event)
    return route(event, user, params)

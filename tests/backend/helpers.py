"""
Small helpers shared by the backend tests: build Lambda events, make tokens,
decode responses.
"""

import json
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_DIR / "backend"

# A dummy signing key for tests. The real JWT_SECRET is never used.
TEST_JWT_SECRET = "test-only-secret-not-used-anywhere-else"  # nosec B105

def make_event(method: str, path: str, body: dict | str | None = None, token: str | None = None,
               query: dict | None = None) -> dict:
    """
    Build a Lambda Function URL event like the one CloudFront forwards.

    Args:
        method: HTTP method, e.g. "POST".
        path: Full path including the /api/<service> prefix.
        body: A dict (sent as JSON) or a raw string (sent as is).
        token: If given, sent as "Authorization: Bearer <token>".
        query: Query string parameters.
    """
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "headers": headers,
        "queryStringParameters": query,
        "body": json.dumps(body) if isinstance(body, dict) else body,
        "isBase64Encoded": False,
    }


# Accounts that unit tests have created tokens for, so the faked
# _shared.auth.lookup_account (see conftest.py) can answer like the users table.
ACCOUNTS: dict[int, dict] = {}


def token_for(user: dict) -> str:
    """Create a valid token for a user dict with id, role, name and email, and register the account."""
    from _shared.auth import create_token  # imported late so JWT_SECRET is already patched

    ACCOUNTS[user["id"]] = {"role": user["role"], "name": user["name"], "email": user["email"]}
    return create_token(user)


def response_json(response: dict) -> dict:
    """Decode a handler response body."""
    return json.loads(response["body"]) if response["body"] else {}

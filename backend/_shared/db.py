"""
PostgreSQL connection management.

One connection is kept at module level so warm Lambda invocations reuse it,
and it is dropped on connection errors so the next call reconnects. The first
time a container connects, it creates any missing tables and seeds demo data
if the users table is empty.

Only repository.py files should import this module.
"""

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from _shared.schema import SCHEMA_SQL
from _shared.seed import seed_if_empty

CONNECT_TIMEOUT_SECONDS = 10

# Reused across invocations within the same Lambda container.
_connection: psycopg.Connection | None = None


def _connect() -> psycopg.Connection:
    """Open a new connection using only the POSTGRES_* environment variables."""
    is_local = os.getenv("IS_LOCAL", "false") == "true"
    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_NAME", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASS", ""),
        sslmode=os.getenv("POSTGRES_SSLMODE", "disable" if is_local else "require"),
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        autocommit=True,
        row_factory=dict_row,
    )
    # Stop any single query from hanging a Lambda invocation.
    conn.execute("SET statement_timeout = '10s'")
    return conn


def get_connection() -> psycopg.Connection:
    """
    Return the shared connection, opening (and preparing) it if needed.

    Returns:
        An open psycopg connection that returns rows as dicts.
    """
    global _connection
    if _connection is None or _connection.closed:
        conn = _connect()
        conn.execute(SCHEMA_SQL)
        seed_if_empty(conn)
        _connection = conn
    return _connection


def _reset_on_connection_error(exc: Exception) -> None:
    """Forget the shared connection after a network/server error so the next call reconnects."""
    global _connection
    if isinstance(exc, psycopg.OperationalError):
        _connection = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """
    Run several statements as one unit: all are committed, or none are.

    Usage:
        with db.transaction() as conn:
            conn.execute(...)
            conn.execute(...)
    """
    conn = get_connection()
    try:
        with conn.transaction():
            yield conn
    except Exception as exc:
        _reset_on_connection_error(exc)
        raise


def _run(sql: str, params: tuple | dict | None) -> psycopg.Cursor:
    """Execute one statement on the shared connection."""
    try:
        return get_connection().execute(sql, params)
    except Exception as exc:
        _reset_on_connection_error(exc)
        raise


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    """Run a query and return every row as a dict."""
    return _run(sql, params).fetchall()


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    """Run a query and return the first row as a dict, or None if there are no rows."""
    return _run(sql, params).fetchone()


def execute(sql: str, params: tuple | dict | None = None) -> int:
    """Run a statement that returns no rows and return how many rows it affected."""
    return _run(sql, params).rowcount

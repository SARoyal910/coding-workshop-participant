"""
Shared pytest fixtures for the backend tests.

The backend is not a package: each service in backend/<svc>/ imports its own
modules by bare name ("import service", "import repository"), exactly as they
are laid out inside a Lambda zip. Every service has a service.py and a
repository.py, so the `load_service` fixture clears those names from the
import cache before loading a service (same idea as backend/dev_server.py).
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable, Iterator

import pytest

from helpers import ACCOUNTS, BACKEND_DIR, TEST_JWT_SECRET

# "_shared" is a package directly under backend/; make it importable everywhere.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def pytest_configure(config: pytest.Config) -> None:
    """Register the custom marker so `-m integration` works without warnings."""
    config.addinivalue_line("markers", "integration: needs PostgreSQL; runs only when RUN_INTEGRATION=1")


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Every test signs and checks tokens with a throwaway secret."""
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    return TEST_JWT_SECRET


@pytest.fixture(autouse=True)
def no_database(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Unit tests must never reach a real database, even when POSTGRES_* is set
    in the shell. Any unfaked repository call fails loudly instead of quietly
    querying whatever database the environment points at.
    """
    if request.node.get_closest_marker("integration"):
        return
    from _shared import db

    def refuse() -> None:
        raise RuntimeError("unit test tried to open a database connection; fake the repository function")

    monkeypatch.setattr(db, "_connect", refuse)
    # require_user reads the caller's current role from the users table; answer
    # from the accounts the test created tokens for instead.
    from _shared import auth

    monkeypatch.setattr(auth, "lookup_account", ACCOUNTS.get)


def _forget_service_modules() -> None:
    """Remove every service's bare-named modules (function, service, repository, rules...) from the import cache."""
    for source in BACKEND_DIR.glob("*/function.py"):
        for module_file in source.parent.glob("*.py"):
            sys.modules.pop(module_file.stem, None)


@pytest.fixture
def load_service() -> Iterator[Callable[[str], SimpleNamespace]]:
    """
    Return a loader that imports backend/<name>/function.py freshly.

    Usage:
        svc = load_service("incidents")
        svc.function.handler(event)       # the Lambda entry point
        svc.repository                    # patch this to avoid the database
        svc.modules["rules"]              # any other module of the service

    The service folder stays first on sys.path until the test ends, then its
    modules are forgotten so the next test (or service) starts clean.
    """
    loaded: list[Path] = []

    def _load(name: str) -> SimpleNamespace:
        service_dir = BACKEND_DIR / name
        _forget_service_modules()
        sys.path.insert(0, str(service_dir))
        loaded.append(service_dir)
        function = importlib.import_module("function")
        modules: dict[str, ModuleType] = {
            source.stem: sys.modules[source.stem]
            for source in service_dir.glob("*.py")
            if source.stem in sys.modules
        }
        return SimpleNamespace(
            function=function,
            service=modules["service"],
            repository=modules["repository"],
            modules=modules,
        )

    yield _load

    for service_dir in loaded:
        sys.path.remove(str(service_dir))
    _forget_service_modules()

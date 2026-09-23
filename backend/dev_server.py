"""
Local development server for the backend services.

Serves http://localhost:8000/api/<service>/<path> by calling that service's
handler(event, context) with a Lambda Function URL-style event, so services
can be run and tested without LocalStack.

Usage:
    python backend/dev_server.py
"""

import importlib.util
import json
import logging
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

BACKEND_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("DEV_SERVER_PORT", "8000"))

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
}


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (existing values win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def discover_services() -> dict[str, Path]:
    """Find every service folder: a direct child of backend/ with a function.py, not starting with _ or ."""
    return {
        folder.name: folder / "function.py"
        for folder in sorted(BACKEND_DIR.iterdir())
        if (folder / "function.py").exists() and not folder.name.startswith(("_", "."))
    }


_loaded: dict[str, ModuleType] = {}


def load_service(name: str, path: Path) -> ModuleType:
    """
    Import a service's function.py once.

    Every service has its own service.py / repository.py, imported by bare name
    (as Lambda does). To stop one service picking up another's modules, the
    service folder is put first on sys.path and its module names are cleared
    from the import cache before loading.
    """
    if name not in _loaded:
        service_dir = str(path.parent)
        for sibling in path.parent.glob("*.py"):
            sys.modules.pop(sibling.stem, None)
        sys.path.insert(0, service_dir)
        try:
            spec = importlib.util.spec_from_file_location(f"service_{name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(service_dir)
        _loaded[name] = module
    return _loaded[name]


def build_event(method: str, raw_path: str, query: str, headers: dict, body: str) -> dict:
    """Build a Lambda Function URL (payload version 2.0) event."""
    return {
        "version": "2.0",
        "rawPath": raw_path,
        "rawQueryString": query,
        "queryStringParameters": dict(parse_qsl(query)) or None,
        "headers": {key.lower(): value for key, value in headers.items()},
        "requestContext": {"http": {"method": method, "path": raw_path}},
        "body": body or None,
        "isBase64Encoded": False,
    }


class DevRequestHandler(BaseHTTPRequestHandler):
    """Routes /api/<service>/... to the matching service handler."""

    services: dict[str, Path] = {}

    def send(self, status: int, headers: dict, body: str) -> None:
        """Write a response with CORS headers added."""
        self.send_response(status)
        for key, value in {**CORS_HEADERS, **headers}.items():
            self.send_header(key, value)
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def handle_any(self) -> None:
        """Handle a request of any method."""
        url = urlsplit(self.path)
        parts = url.path.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "api" or parts[1] not in self.services:
            error = {"error": f"Unknown service. Available: {sorted(self.services)}", "details": {}}
            self.send(404, {"Content-Type": "application/json"}, json.dumps(error))
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        # The full /api/<service>/... path is passed on, like CloudFront does in the cloud.
        event = build_event(self.command, url.path, url.query, dict(self.headers), body)

        # Lambda passes a context object; the request log uses its aws_request_id.
        context = SimpleNamespace(aws_request_id=str(uuid.uuid4()))
        try:
            module = load_service(parts[1], self.services[parts[1]])
            result = module.handler(event, context)
        except Exception:  # pylint: disable=broad-except
            # e.g. an import error in the service; handler errors are already caught by @api_handler.
            logging.exception("Service %s failed to load or run", parts[1])
            result = {"statusCode": 500, "headers": {"Content-Type": "application/json"},
                      "body": json.dumps({"error": "Internal server error", "details": {}})}
        self.send(result.get("statusCode", 200), result.get("headers") or {}, result.get("body") or "")

    def do_OPTIONS(self) -> None:  # pylint: disable=invalid-name
        """Answer CORS preflight requests."""
        self.send(204, {}, "")

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_any

    def log_message(self, format: str, *args: object) -> None:  # pylint: disable=redefined-builtin
        """Silence the default access log; @api_handler already logs one JSON line per request."""


def main() -> None:
    """Load backend/.env, make _shared importable and start the server."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_env_file(BACKEND_DIR / ".env")
    # Services import "_shared.<module>"; in the cloud _shared is copied into each service.
    sys.path.insert(0, str(BACKEND_DIR))

    DevRequestHandler.services = discover_services()
    print(f"Dev server on http://localhost:{PORT}")
    for name in DevRequestHandler.services:
        print(f"  /api/{name}/...")

    # Single-threaded on purpose: like Lambda, each handler sees one request at a time.
    HTTPServer(("127.0.0.1", PORT), DevRequestHandler).serve_forever()


if __name__ == "__main__":
    main()

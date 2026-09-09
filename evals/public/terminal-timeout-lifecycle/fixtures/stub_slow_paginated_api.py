"""Synthetic slow paginated REST fixture for the timeout scenario."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VALID_TOKEN = "nex888-opaque-synthetic-secret-2d4c"
RESPONSE_BODY_MARKER = "nex888-response-body-should-not-appear"
OBSERVED: list[dict[str, object]] = []
_LOCK = threading.Lock()
_OBSERVATIONS_PATH: Path | None = None


def set_observations_path(path: Path | str | None) -> None:
    global _OBSERVATIONS_PATH
    _OBSERVATIONS_PATH = Path(path) if path else None


def _record(item: dict[str, object]) -> None:
    with _LOCK:
        OBSERVED.append(item)
        if _OBSERVATIONS_PATH is not None:
            with _OBSERVATIONS_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item) + "\n")


EVENTS = [{"event_id": index, "value": index * 7} for index in range(1, 24)]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return

    def _json(self, status: int, body: object) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        authorized = self.headers.get("Authorization", "") == f"Bearer {VALID_TOKEN}"
        if not authorized:
            _record({"path": self.path, "status": 401, "authorized": False})
            self._json(401, {"error": "unauthorized"})
            return
        if parsed.path != "/v1/events":
            _record({"path": self.path, "status": 404, "authorized": True})
            self._json(404, {"error": "not found"})
            return
        time.sleep(0.04)
        query = parse_qs(parsed.query)
        page = max(1, int(query.get("page", ["1"])[0]))
        per_page = max(1, int(query.get("per_page", ["10"])[0]))
        start = (page - 1) * per_page
        data = EVENTS[start:start + per_page]
        _record({"path": self.path, "status": 200, "authorized": True, "page": page, "rows": len(data), "total": len(EVENTS)})
        self._json(200, {"page": page, "per_page": per_page, "total": len(EVENTS), "pages": 3, "data": data})


def start_server() -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1], thread


def stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)

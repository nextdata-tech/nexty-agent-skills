"""Synthetic authenticated paginated REST fixture for the DLT scenario."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VALID_TOKEN = "nex890-opaque-synthetic-secret-9a3c"
REQUIRED_USER_AGENT = "nexty-dlt-client/1.0"
OBSERVED: list[dict[str, object]] = []
_OBSERVED_LOCK = threading.Lock()
_OBSERVATIONS_PATH: Path | None = None


def set_observations_path(path: Path | str | None) -> None:
    global _OBSERVATIONS_PATH
    _OBSERVATIONS_PATH = Path(path) if path else None


def observations() -> list[dict[str, object]]:
    with _OBSERVED_LOCK:
        return list(OBSERVED)


def _record(item: dict[str, object]) -> None:
    with _OBSERVED_LOCK:
        OBSERVED.append(item)
        if _OBSERVATIONS_PATH is not None:
            with _OBSERVATIONS_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item) + "\n")


ORDERS = [
    {"order_id": i, "status": "paid" if i % 3 else "pending", "amount": i * 10}
    for i in range(1, 24)
]
PAGE_SIZE = 10


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
        auth = self.headers.get("Authorization", "")
        agent = self.headers.get("User-Agent", "")
        record = {"path": self.path, "authorized": auth == f"Bearer {VALID_TOKEN}", "user_agent": agent}
        if auth != f"Bearer {VALID_TOKEN}":
            record["status"] = 401
            _record(record)
            self._json(401, {"error": "unauthorized"})
            return
        if agent != REQUIRED_USER_AGENT:
            record["status"] = 403
            _record(record)
            self._json(403, {"error": "client is not permitted"})
            return
        if parsed.path != "/v1/orders":
            record["status"] = 404
            _record(record)
            self._json(404, {"error": "unknown endpoint"})
            return
        query = parse_qs(parsed.query)
        requested_page_size = int(query.get("per_page", [str(PAGE_SIZE)])[0])
        if requested_page_size != PAGE_SIZE:
            record.update({"status": 400, "error": "page_size_must_be_bounded"})
            _record(record)
            self._json(400, {"error": "per_page must be 10"})
            return
        rows = ORDERS
        status_filter = query.get("status", [""])[0]
        if status_filter:
            rows = [row for row in rows if row["status"] == status_filter]
        page = max(1, int(query.get("page", ["1"])[0]))
        per_page = PAGE_SIZE
        start = (page - 1) * per_page
        pages = (len(rows) + per_page - 1) // per_page
        record.update({
            "status": 200,
            "status_filter": status_filter or None,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "rows": len(rows[start:start + per_page]),
            "total": len(rows),
        })
        _record(record)
        self._json(200, {"page": page, "per_page": per_page, "total": len(rows), "pages": pages, "data": rows[start:start + per_page]})


def start_server() -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1], thread


def stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)

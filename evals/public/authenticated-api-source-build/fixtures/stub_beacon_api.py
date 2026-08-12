"""In-process stub for the Beacon API the scenario's brief describes.

Stdlib only (``http.server``), started by the checker as a background thread
bound to ``127.0.0.1`` on an ephemeral port — never a live host. This is the
runner-side fixture: it is never copied into the agent workspace and the agent
never sees this file, only the base URL it serves on (written to
``ENDPOINT_URL`` in the workspace) and the behavior described in ``BRIEF.md``.

Auth: every request must carry ``Authorization: Bearer <TOKEN>`` matching
``VALID_TOKEN`` below (the same value handed to the agent in BRIEF.md). A
missing or wrong token gets 401 with a JSON body, no data. This is the
structural signal the deterministic checker uses to confirm the closure sends
a REAL header rather than a hardcoded/omitted one: replaying the closure's
request with the token stripped must fail, and with the token intact must
succeed.

Client header: every request must ALSO carry ``User-Agent:
nexty-test-client/1.0`` (``REQUIRED_USER_AGENT``). A request without it gets
**403** and a non-secret error body — *before* the token is looked at, so a
correctly-credentialed client still fails. This reproduces NEX-873: dlt sends
``User-Agent: dlt/1.28.2`` by default, and an upstream that filters unknown
clients rejects it while the same credentials succeed under curl. The gate is
what makes the header requirement decidable rather than advisory — a closure
that omits ``client.headers`` cannot land a single row, and one that abandons
dlt for a hand-rolled ``urllib`` loop fails ``ingestion:rest-api-resources-used``
instead. ``OBSERVED`` records what actually arrived on the wire so the checker
can assert the configured header reached the request rather than inferring it
from the source.

Endpoints:

  GET /v1/monitors?page=&per_page=   -- monitor directory (12 monitors total)
  GET /v1/checks?page=&per_page=     -- check history (37 checks total)

Both paginate: default per_page is 10, so an unconfigured single fetch lands
a strict subset with no error, exactly like the platform's own worked example
(api-source.md) warns a real upstream can do.

Traps mirrored from the brief, deliberately different in shape from the
existing worldbank-live fixture so this scenario exercises a distinct set of
payload gotchas:

  * ``result`` on a check row is a TRI-STATE string -- "up", "down", or
    "unknown" (a probe that timed out inconclusively) -- never a bool. A
    closure that treats it as {"up": True}.get(result, False) silently folds
    "unknown" into "down", corrupting the uptime ratio question (1).
  * Every check row nests its verdict under a sub-object:
    {"result": {"status": "up", "latency_ms": 812}} -- the scalar the
    transform needs is one level down, mirroring the api-source.md nested-field
    guidance and the platform's general flattening requirement.
  * monitor_id on 4 of the 37 check rows (ids 9101-9104) references a monitor
    that does NOT appear in /v1/monitors -- Beacon's own history of deleted
    monitors, which the brief explicitly calls out under "things I already
    know will bite". A naive inner join silently drops these 4 rows with no
    error; the brief asks that this be visible rather than silent.
  * One monitor (id 1006, "legacy-webhook-relay") has zero check rows at all
    -- configured, never polled. It must remain enumerable as a monitor with
    no checks, not simply absent from a check-grouped ranking.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VALID_TOKEN = "bcn_live_9f3ac2e7d84b41f0a6c5d2e19b7f0033"

# When set, every observation is ALSO appended here as one JSON line. OBSERVED
# lives in whichever process imported this module, and the supervisor E2E's
# verifier is a separate process: it re-serves the published definition and then
# has to answer "did the closure the supervisor materialized reach this fixture,
# carrying the required header?". In-memory state cannot answer that across a
# process boundary, and a checker that infers it from landed rows is inferring —
# the rows would look identical if the header requirement had quietly stopped
# being enforced.
OBSERVATIONS_ENV = "NXD_STUB_OBSERVATIONS"

# The client header Beacon requires of every caller. Non-secret by construction:
# it is published in BRIEF.md, carries no entropy, and is safe in a traceback.
REQUIRED_USER_AGENT = "nexty-test-client/1.0"

# Every inbound request, in arrival order: (path, user_agent, authorized).
# Appended under _OBSERVED_LOCK because ThreadingHTTPServer serves each request
# on its own thread. Read it via `observations()`, never directly.
OBSERVED: list[tuple[str, str, bool]] = []
_OBSERVED_LOCK = threading.Lock()


def observations() -> list[tuple[str, str, bool]]:
    """A snapshot copy of OBSERVED — safe to iterate while the server runs."""
    with _OBSERVED_LOCK:
        return list(OBSERVED)


def reset_observations() -> None:
    with _OBSERVED_LOCK:
        OBSERVED.clear()
    path = _observations_path()
    if path is not None:
        # Truncate rather than unlink: the verifier may already hold the path,
        # and a caller resetting before a re-serve wants an empty log, not a
        # missing one it cannot distinguish from "the stub never started".
        path.write_text("", encoding="utf-8")


def _observations_path() -> Path | None:
    raw = os.environ.get(OBSERVATIONS_ENV, "").strip()
    return Path(raw) if raw else None


def _record(path_and_query: str, user_agent: str, authorized: bool) -> None:
    with _OBSERVED_LOCK:
        OBSERVED.append((path_and_query, user_agent, authorized))
    log = _observations_path()
    if log is None:
        return
    line = json.dumps({"path": path_and_query, "user_agent": user_agent,
                       "authorized": authorized})
    # Append under the same lock the in-memory list uses: ThreadingHTTPServer
    # serves each request on its own thread, and two interleaved writes would
    # produce a line the verifier cannot parse.
    with _OBSERVED_LOCK, log.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def logged_observations(path: Path) -> list[dict]:
    """Read a file-backed observation log written by another process."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

TEAMS = {
    1001: "payments",
    1002: "payments",
    1003: "checkout",
    1004: "checkout",
    1005: "platform",
    1006: "platform",  # legacy-webhook-relay: never polled
    1007: "growth",
    1008: "growth",
    1009: "growth",
    1010: "platform",
    1011: "checkout",
    1012: "payments",
}

MONITOR_NAMES = {
    1001: "checkout-api",
    1002: "payments-webhook",
    1003: "cart-service",
    1004: "checkout-frontend",
    1005: "internal-status-page",
    1006: "legacy-webhook-relay",
    1007: "signup-flow",
    1008: "referral-api",
    1009: "growth-dashboard",
    1010: "admin-console",
    1011: "cart-abandonment-worker",
    1012: "payments-reconciler",
}


def _build_monitors() -> list[dict]:
    return [
        {
            "id": mid,
            "name": name,
            "team": TEAMS[mid],
            "target_url": f"https://example-app.internal/{name}",
        }
        for mid, name in MONITOR_NAMES.items()
    ]


def _build_checks() -> list[dict]:
    """37 rows: mostly "up", a deliberate mix of "down"/"unknown", 4 orphaned
    monitor_ids (9101-9104, never present in /v1/monitors), and monitor 1006
    (legacy-webhook-relay) never appears here at all."""
    rows: list[dict] = []
    check_id = 1
    # Real monitors: 3 checks each x 11 monitors (excludes 1006) = 33 rows.
    pattern = ["up", "up", "down"]  # varies by monitor via rotation below
    for idx, mid in enumerate(m for m in MONITOR_NAMES if m != 1006):
        for j in range(3):
            result = pattern[(idx + j) % 3]
            # Every 5th real-monitor row comes back "unknown" (probe timeout),
            # never a clean up/down -- the tri-state trap.
            if check_id % 5 == 0:
                result = "unknown"
            rows.append({
                "check_id": check_id,
                "monitor_id": mid,
                "checked_at": f"2026-07-{10 + (check_id % 15):02d}T0{check_id % 9}:00:00Z",
                "result": {"status": result, "latency_ms": 100 + (check_id * 7) % 900},
            })
            check_id += 1
    # 4 orphaned rows: monitor_id not in /v1/monitors at all.
    for orphan_mid in (9101, 9102, 9103, 9104):
        rows.append({
            "check_id": check_id,
            "monitor_id": orphan_mid,
            "checked_at": "2026-06-01T00:00:00Z",
            "result": {"status": "down", "latency_ms": None},
        })
        check_id += 1
    assert len(rows) == 37, len(rows)
    return rows


MONITORS = _build_monitors()
CHECKS = _build_checks()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # silence default stderr logging
        return

    def _json_error(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._json_error(401, {"error": "unauthorized",
                               "detail": "missing or invalid bearer token"})

    def _forbidden(self) -> None:
        # Deliberately says "client is not permitted" rather than naming the
        # header: a real filtering upstream does not explain itself, and an
        # error body that reads as a permissions problem is exactly what sends
        # an author after the credential instead of the User-Agent. The body
        # carries no secret, so it is safe in a traceback.
        self._json_error(403, {"error": "forbidden",
                               "detail": "client is not permitted to access this API"})

    def _paginate(self, items: list[dict], qs: dict) -> dict:
        page = int(qs.get("page", ["1"])[0])
        per_page = int(qs.get("per_page", ["10"])[0])
        start = (page - 1) * per_page
        end = start + per_page
        total = len(items)
        pages = (total + per_page - 1) // per_page or 1
        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "data": items[start:end],
        }

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        user_agent = self.headers.get("User-Agent", "")
        auth = self.headers.get("Authorization", "")
        authorized = auth == f"Bearer {VALID_TOKEN}"
        _record(self.path, user_agent, authorized)
        # The header gate runs BEFORE the credential check, so a correctly
        # authenticated client is still refused. That ordering is the point:
        # it is what makes the 403 unattributable to the token and forces the
        # author to compare headers rather than re-check the credential.
        if user_agent != REQUIRED_USER_AGENT:
            self._forbidden()
            return
        if not authorized:
            self._unauthorized()
            return
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/v1/monitors":
            payload = self._paginate(MONITORS, qs)
        elif parsed.path == "/v1/checks":
            payload = self._paginate(CHECKS, qs)
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server() -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    """Bind an ephemeral port on 127.0.0.1 and serve in a background thread."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port, thread


def stop_server(httpd: ThreadingHTTPServer, thread: threading.Thread) -> None:
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=10)

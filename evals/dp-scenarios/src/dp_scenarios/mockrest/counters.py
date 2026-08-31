"""Thread-safe request accounting for the data-port oracle.

Every data request is recorded before behavior evaluation, including rejected
requests.  The snapshot retains aggregate totals and an ordered event list so
call ceilings can be checked against what the server actually received rather
than against a client's narration.  Pagination-enabled route requests are
tracked separately as ``pages`` so a grader can verify pagination without
guessing from unrelated route traffic.  Control-port maintenance calls are
kept out of this oracle so a grader can inspect it without changing the source
call count.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import threading
from typing import Any, Mapping


@dataclass(frozen=True)
class RequestEvent:
    """One data-port request as observed by the server."""

    sequence: int
    route: str
    method: str
    identity: str | None


def caller_identity(headers: Mapping[str, str]) -> str | None:
    """Extract an explicit caller label without treating credentials as identity."""

    for candidate in ("X-Caller-Id", "X-Caller", "X-Client-Id"):
        for key, value in headers.items():
            if key.lower() == candidate.lower() and str(value).strip():
                return str(value)
    return None


class RequestCounters:
    """Counts requests by route, method, and optional caller identity."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[RequestEvent] = []
        self._route_counts: Counter[str] = Counter()
        self._method_counts: Counter[tuple[str, str]] = Counter()
        self._buckets: dict[str, dict[str, Any]] = {}
        self._pages = 0

    def record(
        self,
        route: str,
        method: str,
        headers: Mapping[str, str] | None = None,
        *,
        identity: str | None = None,
        paginated: bool = False,
    ) -> int:
        """Record a request and return its one-based count for this route."""

        if not route or not method:
            raise ValueError("route and method are required for request counting")
        with self._lock:
            if identity is None and headers is not None:
                identity = caller_identity(headers)
            method_name = method.upper()
            event = RequestEvent(len(self._events) + 1, route, method_name, identity)
            self._events.append(event)
            self._route_counts[route] += 1
            self._method_counts[(route, method_name)] += 1
            bucket = self._buckets.setdefault(
                route,
                {"count": 0, "methods": Counter(), "identities": Counter()},
            )
            bucket["count"] += 1
            bucket["methods"][method_name] += 1
            bucket["identities"][identity if identity is not None else "anonymous"] += 1
            if paginated:
                self._pages += 1
            return int(bucket["count"])

    def reset(self) -> None:
        """Clear all events; only the control port calls this between runs."""

        with self._lock:
            self._events.clear()
            self._route_counts.clear()
            self._method_counts.clear()
            self._buckets.clear()
            self._pages = 0

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable point-in-time oracle snapshot."""

        with self._lock:
            grouped = {
                route: {
                    "count": int(bucket["count"]),
                    "methods": dict(bucket["methods"]),
                    "identities": dict(bucket["identities"]),
                }
                for route, bucket in self._buckets.items()
            }
            events = list(self._events)
            total = len(events)
            pages = self._pages
        return {"total": total, "pages": pages, "routes": grouped, "events": [asdict(event) for event in events]}

    as_dict = snapshot

    def count(self, route: str | None = None, method: str | None = None) -> int:
        """Count events optionally restricted to a route and method."""

        with self._lock:
            if route is not None and method is not None:
                return self._method_counts[(route, method.upper())]
            if route is not None:
                return self._route_counts[route]
            if method is not None:
                method_name = method.upper()
                return sum(
                    count
                    for (event_route, event_method), count in self._method_counts.items()
                    if event_method == method_name
                )
            return len(self._events)

    def route_count(self, route: str) -> int:
        """Return the one-based request number for route-level behaviors."""

        with self._lock:
            return self._route_counts[route]

    @property
    def events(self) -> tuple[RequestEvent, ...]:
        """Expose an immutable copy for local assertions."""

        with self._lock:
            return tuple(self._events)


CounterStore = RequestCounters

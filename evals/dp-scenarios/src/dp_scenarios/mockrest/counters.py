"""Thread-safe request accounting for the data-port oracle.

Every data request is recorded before behavior evaluation, including rejected
requests.  The snapshot retains aggregate totals and an ordered event list so
call ceilings can be checked against what the server actually received rather
than against a client's narration.  Successful responses from
pagination-enabled routes are tracked separately as ``pages`` so a grader can
verify pagination without guessing from unrelated route traffic or counting
rejected retries.  Control-port maintenance calls are kept out of this oracle
so a grader can inspect it without changing the source call count.
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
            return int(bucket["count"])

    def record_page(self) -> None:
        """Record one successfully rendered paginated response."""

        with self._lock:
            self._pages += 1

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

    @classmethod
    def _decode_snapshot(
        cls, snapshot: Mapping[str, Any]
    ) -> tuple[list[RequestEvent], Counter[str], Counter[tuple[str, str]], dict[str, dict[str, Any]], int]:
        """Validate and decode a persisted counter snapshot without mutating state."""

        if not isinstance(snapshot, Mapping) or set(snapshot) != {"total", "pages", "routes", "events"}:
            raise ValueError("counter snapshot has an invalid shape")
        total = snapshot["total"]
        pages = snapshot["pages"]
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or isinstance(pages, bool)
            or not isinstance(pages, int)
            or pages < 0
        ):
            raise ValueError("counter snapshot has invalid totals")
        raw_events = snapshot["events"]
        if not isinstance(raw_events, list) or len(raw_events) != total:
            raise ValueError("counter snapshot events do not match total")

        events: list[RequestEvent] = []
        route_counts: Counter[str] = Counter()
        method_counts: Counter[tuple[str, str]] = Counter()
        buckets: dict[str, dict[str, Any]] = {}
        for expected_sequence, raw_event in enumerate(raw_events, start=1):
            if not isinstance(raw_event, Mapping) or set(raw_event) != {
                "sequence", "route", "method", "identity"
            }:
                raise ValueError("counter snapshot contains a malformed event")
            sequence = raw_event["sequence"]
            route = raw_event["route"]
            method = raw_event["method"]
            identity = raw_event["identity"]
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != expected_sequence
                or not isinstance(route, str)
                or not route
                or not isinstance(method, str)
                or not method
                or method != method.upper()
                or (identity is not None and (not isinstance(identity, str) or not identity))
            ):
                raise ValueError("counter snapshot contains an invalid event")
            event = RequestEvent(sequence, route, method, identity)
            events.append(event)
            route_counts[route] += 1
            method_counts[(route, method)] += 1
            bucket = buckets.setdefault(
                route,
                {"count": 0, "methods": Counter(), "identities": Counter()},
            )
            bucket["count"] += 1
            bucket["methods"][method] += 1
            bucket["identities"][identity if identity is not None else "anonymous"] += 1

        raw_routes = snapshot["routes"]
        if not isinstance(raw_routes, Mapping) or set(raw_routes) != set(buckets):
            raise ValueError("counter snapshot routes do not match events")
        expected_routes = {
            route: {
                "count": int(bucket["count"]),
                "methods": dict(bucket["methods"]),
                "identities": dict(bucket["identities"]),
            }
            for route, bucket in buckets.items()
        }
        if dict(raw_routes) != expected_routes:
            raise ValueError("counter snapshot route aggregates do not match events")
        return events, route_counts, method_counts, buckets, pages

    @classmethod
    def validate_snapshot(cls, snapshot: Mapping[str, Any]) -> None:
        """Validate a JSON counter snapshot without changing the live oracle."""

        cls._decode_snapshot(snapshot)

    def restore_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Restore a previously captured snapshot after strict validation."""

        decoded = self._decode_snapshot(snapshot)
        events, route_counts, method_counts, buckets, _pages = decoded
        pages = snapshot["pages"]
        with self._lock:
            self._events = events
            self._route_counts = route_counts
            self._method_counts = method_counts
            self._buckets = buckets
            self._pages = int(pages)

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

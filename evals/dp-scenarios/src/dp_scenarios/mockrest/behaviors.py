"""Pure helpers for deterministic route behavior.

The helpers keep request outcomes a function of the declared route, request
counter, and explicit state.  In particular, pagination cursors are opaque
tokens backed by a server-side map and rate/latency behavior never consults the
wall clock.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import FanoutConfig, HeaderRequirement, PaginationConfig


class BehaviorError(ValueError):
    """Raised when a request asks for an invalid deterministic behavior state."""


@dataclass(frozen=True)
class PathMatch:
    """A route template match and its decoded path parameters."""

    template: str
    parameters: dict[str, str]


def compile_path(path: str) -> re.Pattern[str]:
    """Compile ``/items/{id}`` into a full-match regular expression."""

    pieces: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path):
        pieces.append(re.escape(path[cursor : match.start()]))
        pieces.append(f"(?P<{match.group(1)}>[^/]+)")
        cursor = match.end()
    pieces.append(re.escape(path[cursor:]))
    return re.compile("^" + "".join(pieces) + "$", re.ASCII)


def match_path(pattern: re.Pattern[str], template: str, path: str) -> PathMatch | None:
    """Return route parameters if a path matches its template."""

    match = pattern.fullmatch(path)
    return None if match is None else PathMatch(template, dict(match.groupdict()))


def route_specificity(path: str) -> tuple[int, int]:
    """Prefer literal and longer routes before broad parameterized routes."""

    return (path.count("{"), -len(path))


def opaque_cursor(route: str, offset: int, state: str = "static") -> str:
    """Create a deterministic cursor bound to a route, state, and offset."""

    digest = hashlib.sha256(f"mock-rest\0{route}\0{state}\0{offset}".encode("utf-8")).digest()
    return "c_" + base64.urlsafe_b64encode(digest[:18]).decode("ascii").rstrip("=")


def cursor_offsets(
    route: str, total: int, page_size: int, state: str = "static"
) -> dict[str, int]:
    """Build the opaque token map for all valid page starts of a route."""

    if page_size < 1:
        raise BehaviorError("page size must be positive")
    return {
        opaque_cursor(route, offset, state): offset
        for offset in range(0, total, page_size)
    }


@dataclass(frozen=True)
class Page:
    """A page payload and its optional opaque continuation token."""

    records: list[Any]
    next_cursor: str | None


def paginate(
    records: Sequence[Any],
    *,
    cursor: str | None,
    config: PaginationConfig,
    route: str,
    valid_cursors: Mapping[str, int],
    state: str = "static",
) -> Page:
    """Return one stable page, rejecting cursors not issued for this route/state."""

    if cursor is None:
        offset = 0
    else:
        if cursor not in valid_cursors:
            raise BehaviorError("invalid cursor")
        offset = valid_cursors[cursor]
    page = list(records[offset : offset + config.page_size])
    next_offset = offset + len(page)
    next_token = (
        opaque_cursor(route, next_offset, state) if next_offset < len(records) else None
    )
    return Page(page, next_token)


def satisfy_header(headers: Mapping[str, str], requirement: HeaderRequirement) -> bool:
    """Check a named header without exposing configuration metadata in errors."""

    actual = next((value for key, value in headers.items() if key.lower() == requirement.name.lower()), None)
    return actual == requirement.value


def has_nonblank_user_agent(headers: Mapping[str, str]) -> bool:
    """Implement the unconditional blank-user-agent rule."""

    value = next((value for key, value in headers.items() if key.lower() == "user-agent"), "")
    return bool(value.strip())


def is_rate_limited(request_number: int, every: int | None) -> bool:
    """Return true exactly for request numbers divisible by the configured k."""

    return every is not None and request_number > 0 and request_number % every == 0


def select_item(records: Any, *, item_key: str, item_value: str) -> Any:
    """Select one item from a collection, preserving the source's value types."""

    if not isinstance(records, list):
        raise BehaviorError("item response requires a JSON collection")
    for record in records:
        if isinstance(record, Mapping) and str(record.get(item_key)) == item_value:
            return record
    return None


def select_children(records: Any, *, fanout: FanoutConfig, parent_value: str) -> list[Any]:
    """Filter child records for exactly one parent request."""

    if not isinstance(records, list):
        raise BehaviorError("fan-out response requires a JSON collection")
    return [
        record
        for record in records
        if isinstance(record, Mapping) and str(record.get(fanout.child_parent_field)) == parent_value
    ]

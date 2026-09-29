"""Runner-private v1/v2/v3 product-usage-event sources for the B8 fixture.

Three states of one hidden event stream serve the B8 (initial publication,
then late-arrival refresh) and a future B8b (short-delivery hold) package.
Only v1 and v2 are consumed by this B8 package; v3 is generated and verified
here so the shared fixture is ready for B8b without re-deriving its counts.

Every ordinary day is 100 accounts x 3 features x 2 events = 600 events,
timestamped every 144 seconds (86,400 / 600) from midnight so the day's last
event lands at 23:57:36 -- the exact instant the design's B8 fixture section
names for the last v1 event. ``event_id`` is stable across every state that
serves the same logical event, which is what makes the v1/v2 union countable
by a plain set union over ids.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition
from ..defects import Frame, _sentinel_for
from ..registry import register_dataset

FEATURES: tuple[str, ...] = ("search", "dashboard", "export")
_SECONDS_PER_EVENT = 144  # 86_400 seconds / 600 ordinary daily events

# Three disjoint groups of ten new accounts, one group exclusively tied to
# each feature. A shared pool of ten accounts touching all three features
# would raise both the per-feature and the overall weekly count by the same
# ten; the design's own numbers -- an overall weekly rise of thirty
# (100 -> 130) alongside a per-feature rise of only ten (100 -> 110) -- are
# reachable only if the accounts feeding each feature are distinct from the
# accounts feeding the other two. This is a genuine design ambiguity: "ten
# new accounts per feature" is resolved here as thirty distinct accounts.
_LATE_ACCOUNT_GROUPS: tuple[tuple[str, int, tuple[int, ...]], ...] = (
    ("search", 19, tuple(range(1001, 1011))),
    ("dashboard", 20, tuple(range(1011, 1021))),
    ("export", 21, tuple(range(1021, 1031))),
)
LATE_EVENT_DAY = date(2024, 4, 19)
LATE_EVENT_HOUR = 12  # earliest late timestamp is 2024-04-19T12:00:00Z


def _account_id(account: int) -> str:
    return f"ACC-{account:04d}"


def _actor(account: int, *, seed: int) -> dict[str, str]:
    if account == 1:
        email = _sentinel_for("actor.email", seed=seed, dataset="product_usage")
    else:
        email = f"user{account:04d}@example.invalid"
    return {
        "user_id": f"U-{account:04d}",
        "display_name": f"Account {account:04d} User",
        "email": email,
    }


def _iso(instant: datetime) -> str:
    """Format an already-UTC instant; every caller builds one with tzinfo=UTC."""

    return instant.isoformat().replace("+00:00", "Z")


def _day_events(day: date, accounts: tuple[int, ...], *, seed: int) -> list[dict[str, object]]:
    """Every account fires two events per feature, spaced every 144 seconds."""

    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    events: list[dict[str, object]] = []
    index = 0
    for account in accounts:
        for feature in FEATURES:
            for occurrence in (1, 2):
                events.append(
                    {
                        "event_id": f"evt-{day.isoformat()}-{account:04d}-{feature}-{occurrence}",
                        "account_id": _account_id(account),
                        "feature": feature,
                        "occurred_at": _iso(day_start + timedelta(seconds=index * _SECONDS_PER_EVENT)),
                        "actor": _actor(account, seed=seed),
                    }
                )
                index += 1
    return events


def _date_range(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _ordinary_events(
    start: date, end: date, *, seed: int, overrides: Mapping[date, tuple[int, ...]] = ()
) -> list[dict[str, object]]:
    overrides = dict(overrides)
    events: list[dict[str, object]] = []
    for day in _date_range(start, end):
        accounts = overrides.get(day, tuple(range(1, 101)))
        events.extend(_day_events(day, accounts, seed=seed))
    return events


def _late_events(*, seed: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for feature, day_of_month, accounts in _LATE_ACCOUNT_GROUPS:
        occurred_at = _iso(datetime(2024, 4, day_of_month, LATE_EVENT_HOUR, tzinfo=timezone.utc))
        for account in accounts:
            events.append(
                {
                    "event_id": f"evt-2024-04-{day_of_month:02d}-{account:04d}-{feature}-1",
                    "account_id": _account_id(account),
                    "feature": feature,
                    "occurred_at": occurred_at,
                    "actor": _actor(account, seed=seed),
                }
            )
    return events


def _export_status(*, as_of: str, expected_daily_count: int, reporting_date: str) -> list[dict[str, object]]:
    return [
        {
            "as_of": as_of,
            "expected_daily_count": expected_daily_count,
            "reporting_date": reporting_date,
        }
    ]


def _build_product_usage(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    del rng
    apr8 = date(2024, 4, 8)

    v1_events = _ordinary_events(
        apr8, date(2024, 4, 21), seed=seed, overrides={apr8: tuple(range(201, 301))}
    )
    v2_events = _ordinary_events(date(2024, 4, 9), date(2024, 4, 22), seed=seed) + _late_events(seed=seed)
    v3_short_day = _day_events(date(2024, 4, 23), tuple(range(301, 351)), seed=seed)
    v3_events = (
        _ordinary_events(date(2024, 4, 10), date(2024, 4, 22), seed=seed)
        + _late_events(seed=seed)
        + v3_short_day
    )

    assert len(v1_events) == 8_400  # noqa: S101 - fixture invariant, not test code
    assert len(v2_events) == 8_430  # noqa: S101
    assert len(v3_events) == 8_130  # noqa: S101

    return {
        "usage_events_v1": v1_events,
        "usage_events_v2": v2_events,
        "usage_events_v3": v3_events,
        "usage_export_status_v1": _export_status(
            as_of="2024-04-22T06:00:00Z", expected_daily_count=600, reporting_date="2024-04-21"
        ),
        "usage_export_status_v2": _export_status(
            as_of="2024-04-23T06:00:00Z", expected_daily_count=600, reporting_date="2024-04-22"
        ),
        "usage_export_status_v3": _export_status(
            as_of="2024-04-24T06:00:00Z", expected_daily_count=600, reporting_date="2024-04-23"
        ),
    }


register_dataset(
    DatasetDefinition(
        name="product_usage",
        base_instant=BASE_INSTANT,
        table_columns={},
        source_tables=(
            "usage_events_v1",
            "usage_events_v2",
            "usage_events_v3",
            "usage_export_status_v1",
            "usage_export_status_v2",
            "usage_export_status_v3",
        ),
        injectors=(),
        builder=_build_product_usage,
        description="Stateful product-usage-event source with a rolling served window.",
        plant="B8-late-arrival-refresh",
        requires_explicit_plant=True,
    )
)

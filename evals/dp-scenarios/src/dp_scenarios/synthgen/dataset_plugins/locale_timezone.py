"""UTF-8 and timezone-boundary source fixture for the C6 scenario."""

from __future__ import annotations

import random
from typing import Mapping

from ..datasets import BASE_INSTANT, DatasetDefinition
from ..defects import Frame
from ..registry import register_dataset


def _build_locale_timezone(seed: int, rng: random.Random) -> Mapping[str, Frame]:
    del rng
    timestamps = [
        ("2024-03-01T12:00:00-05:00", "2024-03-01T17:00:00+00:00"),
        ("2024-03-02T12:00:00-05:00", "2024-03-02T17:00:00+00:00"),
        ("2024-03-03T12:00:00-05:00", "2024-03-03T17:00:00+00:00"),
        ("2024-03-04T12:00:00-05:00", "2024-03-04T17:00:00+00:00"),
        ("2024-03-05T12:00:00-05:00", "2024-03-05T17:00:00+00:00"),
        ("2024-03-06T12:00:00-05:00", "2024-03-06T17:00:00+00:00"),
        ("2024-03-07T12:00:00-05:00", "2024-03-07T17:00:00+00:00"),
        ("2024-03-08T12:00:00-05:00", "2024-03-08T17:00:00+00:00"),
        ("2024-03-09T12:00:00-05:00", "2024-03-09T17:00:00+00:00"),
        # America/New_York changes from -05:00 to -04:00 on March 10.
        ("2024-03-10T01:30:00-05:00", "2024-03-10T06:30:00+00:00"),
        ("2024-03-10T03:30:00-04:00", "2024-03-10T07:30:00+00:00"),
        ("2024-03-11T12:00:00-04:00", "2024-03-11T16:00:00+00:00"),
        ("2024-03-12T12:00:00-04:00", "2024-03-12T16:00:00+00:00"),
        # This final row crosses the UTC date boundary while retaining its
        # source-local March 10 reporting day.
        ("2024-03-10T23:30:00-04:00", "2024-03-11T03:30:00+00:00"),
    ]
    events: Frame = []
    for index, (local_timestamp, utc_timestamp) in enumerate(timestamps):
        events.append(
            {
                "event_id": f"EVT-{seed}-{index + 1:02d}",
                "category": "Renovación" if index % 2 == 0 else "契約",
                "amount": f"{100 + index * 10:.2f}",
                "source_local_timestamp": local_timestamp,
                "event_utc": utc_timestamp,
                "source_timezone": "America/New_York",
            }
        )
    return {"events": events}


register_dataset(
    DatasetDefinition(
        name="locale_timezone",
        base_instant=BASE_INSTANT,
        table_columns={
            "events": (
                "event_id",
                "category",
                "amount",
                "source_local_timestamp",
                "event_utc",
                "source_timezone",
            )
        },
        injectors=(),
        builder=_build_locale_timezone,
        description=(
            "UTF-8 categories are paired with timestamps carrying explicit source "
            "timezone and UTC representations for a local-versus-UTC day-boundary "
            "exercise."
        ),
        plant="locale_timezone_boundary",
        requires_explicit_plant=True,
    )
)

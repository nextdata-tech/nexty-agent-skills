# ruff: noqa: F403, F405
from nxd_models import *

# Input model: raw clickstream events pulled from the events API.
events_model = (
    semantic_model("events_model")
    .description("Raw web clickstream events to be aggregated into sessions")
    .schema(
        {
            "event_id": (string(), "Stable source id for the event"),
            "session_id": (string(), "Session the event belongs to"),
            "user_id": (string(), "User who triggered the event"),
            "event_type": (string(), "Kind of event (page_view, click, ...)"),
            "occurred_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "Time the event occurred",
            ),
        }
    )
)

# Output model: one row per session with rollup metrics.
sessions_model = (
    semantic_model("sessions_model")
    .description("Per-session rollup of clickstream activity")
    .schema(
        {
            "session_id": (string(), "Session identifier"),
            "user_id": (string(), "User who owns the session"),
            "event_count": (number(), "Number of events in the session"),
            "started_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "First event time in the session",
            ),
            "ended_at": (
                timestamp(unit=DurationUnit.Milliseconds, timezone=None),
                "Last event time in the session",
            ),
        }
    )
)

"""Aggregate raw clickstream events into per-session rollups."""

from collections import defaultdict

import pandas as pd


def transform(events, ctx):
    by_session = defaultdict(list)
    for event in events:
        by_session[event["session_id"]].append(event)

    rows = []
    for session_id, session_events in by_session.items():
        frame = pd.DataFrame(session_events).sort_values("occurred_at")
        rows.append(
            {
                "session_id": session_id,
                "user_id": frame["user_id"].iloc[0],
                "event_count": int(len(frame)),
                "started_at": frame["occurred_at"].iloc[0],
                "ended_at": frame["occurred_at"].iloc[-1],
            }
        )
    return rows

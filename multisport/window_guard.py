#!/usr/bin/env python3
"""Expose a short pregame wait for delayed GitHub Actions schedules.

This does not choose or consume a provider read. The normal platform scheduler
remains the authority for due windows and every daily/monthly/account cap.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX_WAIT_SECONDS = 105 * 60
START_GRACE_SECONDS = 5


def iso(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp timezone required")
    return parsed


def planned_wait(data, now, max_wait_seconds=DEFAULT_MAX_WAIT_SECONDS):
    """Return seconds to the next default pregame window, or None."""
    feed = data.get("platformFeed", {}) if isinstance(data, dict) else {}
    if feed.get("refreshMode") != "PREGAME_WINDOWS" or feed.get("refreshReason") != "PREGAME_WINDOW":
        return None
    try:
        target = iso(feed.get("nextRefreshAt"))
    except (ValueError, TypeError, AttributeError):
        return None
    seconds = (target.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds()
    if seconds <= 0 or seconds > max_wait_seconds:
        return None
    return math.ceil(seconds) + START_GRACE_SECONDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="multisport/data.json")
    parser.add_argument("--max-wait-seconds", type=int, default=DEFAULT_MAX_WAIT_SECONDS)
    args = parser.parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    wait = planned_wait(data, datetime.now(timezone.utc), max(0, args.max_wait_seconds))
    print(f"should_wait={'true' if wait is not None else 'false'}")
    print(f"wait_seconds={wait or 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

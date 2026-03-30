"""Activity commands for the direct Strava CLI."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from strava_mcp.cli import output


def register(subparsers: argparse._SubParsersAction) -> None:
    list_parser = subparsers.add_parser("list", help="List recent activities")
    list_parser.add_argument(
        "--before",
        help="Return activities before this ISO 8601 date/datetime",
    )
    list_parser.add_argument(
        "--after",
        help="Return activities after this ISO 8601 date/datetime",
    )
    list_parser.add_argument("--page", type=int, default=1, help="Page number")
    list_parser.add_argument(
        "--per-page",
        type=int,
        default=30,
        help="Activities per page (1-200)",
    )
    list_parser.set_defaults(func=list_activities)

    show_parser = subparsers.add_parser("show", help="Show one activity in detail")
    show_parser.add_argument("activity_id", type=int, help="Strava activity ID")
    show_parser.set_defaults(func=show_activity)


def list_activities(args: argparse.Namespace) -> int:
    activities = args.service_factory().list_activities(
        before=_parse_iso_datetime(args.before, flag_name="--before"),
        after=_parse_iso_datetime(args.after, flag_name="--after"),
        page=args.page,
        per_page=args.per_page,
    )
    if args.json:
        return output.emit_json(activities)
    return output.emit_activities(activities)


def show_activity(args: argparse.Namespace) -> int:
    activity = args.service_factory().get_activity(activity_id=args.activity_id)
    if args.json:
        return output.emit_json(activity)
    return output.emit_activity(activity)


def _parse_iso_datetime(raw_value: str | None, *, flag_name: str) -> datetime | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid value for {flag_name}: {raw_value!r}. Use ISO 8601 date or datetime."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed

"""Activity stream commands for the direct Strava CLI."""

from __future__ import annotations

import argparse

from strava_mcp.cli import output
from strava_mcp.strava import STRAVA_STREAM_TYPES


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "streams",
        help="Fetch selected streams for one activity",
    )
    parser.add_argument("activity_id", type=int, help="Strava activity ID")
    parser.add_argument(
        "--keys",
        nargs="+",
        required=True,
        metavar="KEY",
        help=(
            "Stream keys to fetch. Repeat or comma-separate values such as "
            "`heartrate watts` or `heartrate,watts`."
        ),
    )
    parser.add_argument(
        "--resolution",
        choices=("low", "medium", "high"),
        default="medium",
        help="Requested Strava stream resolution",
    )
    parser.add_argument(
        "--series-type",
        choices=("time", "distance"),
        default="time",
        help="Requested Strava series type",
    )
    parser.set_defaults(func=get_streams)


def get_streams(args: argparse.Namespace) -> int:
    stream_keys = _normalize_stream_keys(args.keys)
    streams = args.service_factory().get_activity_streams(
        activity_id=args.activity_id,
        stream_types=stream_keys,
        resolution=args.resolution,
        series_type=args.series_type,
    )
    if args.json:
        return output.emit_json(streams)
    return output.emit_streams(args.activity_id, stream_keys, streams)


def _normalize_stream_keys(raw_keys: list[str]) -> tuple[str, ...]:
    keys = tuple(
        dict.fromkeys(
            item.strip()
            for raw_key in raw_keys
            for item in raw_key.split(",")
            if item.strip()
        )
    )
    if not keys:
        raise ValueError("At least one Strava stream key is required.")
    unsupported = sorted(set(keys) - set(STRAVA_STREAM_TYPES))
    if unsupported:
        supported = ", ".join(STRAVA_STREAM_TYPES)
        raise ValueError(
            f"Unsupported Strava stream keys: {', '.join(unsupported)}. Supported keys: {supported}"
        )
    return keys

"""Direct Strava API CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from strava_mcp.cli import activities, athlete, streams
from strava_mcp.runtime import build_service
from strava_mcp.strava import StravaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strava",
        description="Direct Strava CLI backed by the local Strava service layer",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Directory that stores Strava auth state",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    athlete.register(subparsers)
    activities.register(subparsers)
    streams.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.service_factory = lambda: build_service(args.root)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return int(args.func(args))
    except (StravaError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

"""Athlete commands for the direct Strava CLI."""

from __future__ import annotations

import argparse

from strava_mcp.cli import output


def register(subparsers: argparse._SubParsersAction) -> None:
    profile_parser = subparsers.add_parser(
        "profile",
        help="Show the authenticated athlete",
    )
    profile_parser.set_defaults(func=show_profile)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Show aggregate athlete statistics",
    )
    stats_parser.set_defaults(func=show_stats)

    zones_parser = subparsers.add_parser(
        "zones",
        help="Show configured athlete heart rate and power zones",
    )
    zones_parser.set_defaults(func=show_zones)


def show_profile(args: argparse.Namespace) -> int:
    athlete = args.service_factory().get_athlete()
    if args.json:
        return output.emit_json(athlete)
    return output.emit_athlete(athlete)


def show_stats(args: argparse.Namespace) -> int:
    stats = args.service_factory().get_athlete_stats()
    if args.json:
        return output.emit_json(stats)
    return output.emit_athlete_stats(stats)


def show_zones(args: argparse.Namespace) -> int:
    zones = args.service_factory().get_athlete_zones()
    if args.json:
        return output.emit_json(zones)
    return output.emit_athlete_zones(zones)

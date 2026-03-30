"""Output helpers for the direct Strava CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from strava_mcp.strava import (
    StravaActivityStreams,
    StravaActivitySummary,
    StravaAthlete,
    StravaAthleteStats,
    StravaAthleteZones,
    StravaDetailedActivity,
)


def emit_json(payload: Any) -> int:
    print(json.dumps(_json_ready(payload), indent=2))
    return 0


def emit_athlete(athlete: StravaAthlete) -> int:
    _print_key_values(
        "Authenticated athlete",
        [
            ("ID", athlete.id),
            ("Name", _join_words(athlete.firstname, athlete.lastname)),
            ("Username", athlete.username),
            ("Location", _join_non_empty(athlete.city, athlete.state, athlete.country)),
            ("Sex", athlete.sex),
            ("Summit", _format_bool(athlete.summit)),
            ("Created at", _format_datetime(athlete.created_at)),
            ("Updated at", _format_datetime(athlete.updated_at)),
        ],
    )
    return 0


def emit_athlete_stats(stats: StravaAthleteStats) -> int:
    _print_key_values(
        "Athlete stats",
        [
            ("Biggest ride distance", _format_distance(stats.biggest_ride_distance)),
            (
                "Biggest climb elevation gain",
                _format_elevation(stats.biggest_climb_elevation_gain),
            ),
        ],
    )
    _print_totals_section("Recent ride totals", stats.recent_ride_totals)
    _print_totals_section("Recent run totals", stats.recent_run_totals)
    _print_totals_section("Recent swim totals", stats.recent_swim_totals)
    _print_totals_section("Year-to-date ride totals", stats.ytd_ride_totals)
    _print_totals_section("Year-to-date run totals", stats.ytd_run_totals)
    _print_totals_section("Year-to-date swim totals", stats.ytd_swim_totals)
    _print_totals_section("All-time ride totals", stats.all_ride_totals)
    _print_totals_section("All-time run totals", stats.all_run_totals)
    _print_totals_section("All-time swim totals", stats.all_swim_totals)
    return 0


def emit_athlete_zones(zones: StravaAthleteZones) -> int:
    print("Athlete zones")
    if zones.heart_rate is not None:
        print("")
        print(
            f"Heart rate zones (custom: {_format_bool(zones.heart_rate.custom_zones)})"
        )
        if zones.heart_rate.zones:
            for index, zone in enumerate(zones.heart_rate.zones, start=1):
                print(
                    f"Z{index}: {_format_numeric(zone.min)} - {_format_numeric(zone.max)}"
                )
        else:
            print("No configured heart rate zones.")
    if zones.power is not None:
        print("")
        print("Power zones")
        if zones.power.zones:
            for index, zone in enumerate(zones.power.zones, start=1):
                print(
                    f"Z{index}: {_format_numeric(zone.min)} - {_format_numeric(zone.max)}"
                )
        else:
            print("No configured power zones.")
    return 0


def emit_activities(activities: list[StravaActivitySummary]) -> int:
    if not activities:
        print("No activities found.")
        return 0

    headers = ["ID", "Start", "Sport", "km", "Move", "Elev m", "Name"]
    rows = [
        [
            str(activity.id or ""),
            _format_datetime(activity.start_date_local),
            activity.sport_type or activity.type or "",
            _format_decimal(activity.distance / 1000 if activity.distance else None),
            _format_duration(activity.moving_time),
            _format_decimal(activity.total_elevation_gain),
            activity.name or "",
        ]
        for activity in activities
    ]
    _print_table(headers, rows)
    return 0


def emit_activity(activity: StravaDetailedActivity) -> int:
    _print_key_values(
        "Activity detail",
        [
            ("ID", activity.id),
            ("Name", activity.name),
            ("Sport", activity.sport_type or activity.type),
            ("Type", activity.type),
            ("Start local", _format_datetime(activity.start_date_local)),
            ("Start UTC", _format_datetime(activity.start_date)),
            ("Timezone", activity.timezone),
            ("Distance", _format_distance(activity.distance)),
            ("Moving time", _format_duration(activity.moving_time)),
            ("Elapsed time", _format_duration(activity.elapsed_time)),
            ("Elevation gain", _format_elevation(activity.total_elevation_gain)),
            ("Average speed", _format_speed(activity.average_speed)),
            ("Max speed", _format_speed(activity.max_speed)),
            ("Average watts", _format_decimal(activity.average_watts)),
            ("Weighted average watts", _format_numeric(activity.weighted_average_watts)),
            ("Average heartrate", _format_decimal(activity.average_heartrate)),
            ("Max heartrate", _format_decimal(activity.max_heartrate)),
            ("Average cadence", _format_decimal(activity.average_cadence)),
            ("Average temp", _format_numeric(activity.average_temp)),
            ("Kilojoules", _format_decimal(activity.kilojoules)),
            ("Calories", _format_decimal(activity.calories)),
            ("Private", _format_bool(activity.private)),
            ("Manual", _format_bool(activity.manual)),
            ("Trainer", _format_bool(activity.trainer)),
            ("Commute", _format_bool(activity.commute)),
            ("Description", activity.description),
        ],
    )
    return 0


def emit_streams(
    activity_id: int,
    stream_keys: tuple[str, ...],
    streams: StravaActivityStreams,
) -> int:
    print(f"Activity {activity_id}")
    print(f"Requested streams: {', '.join(stream_keys)}")
    for stream_key in stream_keys:
        stream = getattr(streams, stream_key)
        if stream is None:
            continue
        print("")
        print(stream_key)
        print(f"Points: {len(stream.data)}")
        print(f"Resolution: {stream.resolution or '<unknown>'}")
        print(f"Series type: {stream.series_type or '<unknown>'}")
        print(f"Preview: {_preview_stream_data(stream.data)}")
    return 0


def _json_ready(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, list):
        return [_json_ready(item) for item in payload]
    if isinstance(payload, tuple):
        return [_json_ready(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _json_ready(value) for key, value in payload.items()}
    return payload


def _print_key_values(title: str, rows: list[tuple[str, Any]]) -> None:
    print(title)
    for label, value in rows:
        if value is None or value == "":
            continue
        print(f"{label}: {value}")


def _print_totals_section(
    title: str,
    totals: dict[str, float | int | None] | None,
) -> None:
    if not totals:
        return
    print("")
    print(title)
    ordered_keys = (
        "count",
        "distance",
        "moving_time",
        "elapsed_time",
        "elevation_gain",
        "achievement_count",
    )
    printed_keys: set[str] = set()
    for key in ordered_keys:
        if key in totals:
            print(f"{_labelize(key)}: {_format_totals_value(key, totals[key])}")
            printed_keys.add(key)
    for key in sorted(totals):
        if key in printed_keys:
            continue
        print(f"{_labelize(key)}: {_format_totals_value(key, totals[key])}")


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _labelize(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _format_totals_value(key: str, value: float | int | None) -> str:
    if value is None:
        return "-"
    if key == "distance":
        return _format_distance(float(value))
    if key == "moving_time" or key == "elapsed_time":
        return _format_duration(int(value))
    if key == "elevation_gain":
        return _format_elevation(float(value))
    return str(value)


def _format_distance(distance_meters: float | None) -> str:
    if distance_meters is None:
        return "-"
    return f"{distance_meters / 1000:.2f} km"


def _format_elevation(elevation_meters: float | None) -> str:
    if elevation_meters is None:
        return "-"
    return f"{elevation_meters:.1f} m"


def _format_speed(speed_meters_per_second: float | None) -> str:
    if speed_meters_per_second is None:
        return "-"
    return f"{speed_meters_per_second * 3.6:.2f} km/h"


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _format_decimal(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}"


def _format_numeric(value: float | int | None) -> str:
    if value is None:
        return "-"
    return str(value)


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def _join_non_empty(*values: str | None) -> str | None:
    joined = ", ".join(value for value in values if value)
    return joined or None


def _join_words(*values: str | None) -> str | None:
    joined = " ".join(value for value in values if value)
    return joined or None


def _preview_stream_data(data: list[Any]) -> str:
    if not data:
        return "[]"
    preview = data[:5]
    suffix = "..." if len(data) > len(preview) else ""
    return f"{preview}{suffix}"

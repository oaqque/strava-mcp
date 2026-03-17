"""Unit tests for the Strava MCP server wiring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from strava_mcp.server import create_server
from strava_mcp.strava import (
    StravaActivityStreams,
    StravaActivitySummary,
    StravaApiError,
    StravaAthlete,
    StravaAthleteStats,
    StravaAthleteZones,
    StravaDetailedActivity,
)


def _sample_activity() -> StravaActivitySummary:
    return StravaActivitySummary(
        id=11,
        name="Lunch Ride",
        start_date=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
        type="Ride",
    )


class _FakeStravaService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_athlete(self) -> StravaAthlete:
        self.calls.append(("get_athlete", {}))
        return StravaAthlete(id=7, firstname="Will")

    def get_athlete_stats(self) -> StravaAthleteStats:
        self.calls.append(("get_athlete_stats", {}))
        return StravaAthleteStats(biggest_ride_distance=12345.0)

    def get_athlete_zones(self) -> StravaAthleteZones:
        self.calls.append(("get_athlete_zones", {}))
        return StravaAthleteZones(heart_rate={"custom_zones": False, "zones": []})

    def list_activities(
        self,
        *,
        before: datetime | None = None,
        after: datetime | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[StravaActivitySummary]:
        self.calls.append(
            (
                "list_activities",
                {
                    "before": before,
                    "after": after,
                    "page": page,
                    "per_page": per_page,
                },
            )
        )
        return [_sample_activity()]

    def get_activity(self, *, activity_id: int) -> StravaDetailedActivity:
        self.calls.append(("get_activity", {"activity_id": activity_id}))
        return StravaDetailedActivity(id=activity_id, name="Lunch Ride")

    def get_activity_streams(
        self,
        *,
        activity_id: int,
        stream_types: tuple[str, ...],
        resolution: str = "medium",
        series_type: str = "time",
    ) -> StravaActivityStreams:
        self.calls.append(
            (
                "get_activity_streams",
                {
                    "activity_id": activity_id,
                    "stream_types": stream_types,
                    "resolution": resolution,
                    "series_type": series_type,
                },
            )
        )
        return StravaActivityStreams(
            heartrate={
                "type": "heartrate",
                "data": [120, 125],
                "series_type": series_type,
                "resolution": resolution,
                "original_size": 2,
            }
        )


@pytest.mark.asyncio
async def test_server_exposes_expected_strava_tools():
    service = _FakeStravaService()
    server = create_server(service_factory=lambda: service)

    tools = await server.list_tools()
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "get_athlete_profile",
        "get_athlete_stats",
        "get_athlete_zones",
        "list_activities",
        "get_activity_detail",
        "get_activity_streams",
    }


@pytest.mark.asyncio
async def test_list_activities_tool_returns_structured_output():
    service = _FakeStravaService()
    server = create_server(service_factory=lambda: service)
    before = "2026-03-20T08:00:00Z"
    after = "2026-03-10T08:00:00Z"

    _, result = await server.call_tool(
        "list_activities",
        {
            "before": before,
            "after": after,
            "page": 2,
            "per_page": 5,
        },
    )

    assert result["page"] == 2
    assert result["per_page"] == 5
    assert len(result["activities"]) == 1
    assert result["activities"][0]["name"] == "Lunch Ride"
    assert service.calls == [
        (
            "list_activities",
            {
                "before": datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
                "after": datetime(2026, 3, 10, 8, 0, tzinfo=UTC),
                "page": 2,
                "per_page": 5,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_activity_streams_tool_normalizes_duplicate_stream_types():
    service = _FakeStravaService()
    server = create_server(service_factory=lambda: service)

    _, result = await server.call_tool(
        "get_activity_streams",
        {
            "activity_id": 99,
            "stream_types": ["heartrate", "heartrate"],
            "resolution": "high",
            "series_type": "distance",
        },
    )

    assert result["activity_id"] == 99
    assert result["stream_types"] == ["heartrate"]
    assert service.calls == [
        (
            "get_activity_streams",
            {
                "activity_id": 99,
                "stream_types": ("heartrate",),
                "resolution": "high",
                "series_type": "distance",
            },
        )
    ]


@pytest.mark.asyncio
async def test_tool_argument_validation_is_exposed_to_clients():
    server = create_server(service_factory=_FakeStravaService)

    with pytest.raises(ToolError, match="page"):
        await server.call_tool("list_activities", {"page": 0})

    with pytest.raises(ToolError, match="stream_types"):
        await server.call_tool(
            "get_activity_streams",
            {"activity_id": 1, "stream_types": ["not-a-stream"]},
        )


@pytest.mark.asyncio
async def test_shared_layer_errors_propagate_through_tool_execution():
    class _FailingStravaService(_FakeStravaService):
        def get_athlete_stats(self) -> StravaAthleteStats:
            raise StravaApiError(status_code=429, message="rate limited")

    server = create_server(service_factory=_FailingStravaService)

    with pytest.raises(ToolError, match="rate limited"):
        await server.call_tool("get_athlete_stats", {})

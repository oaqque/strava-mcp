"""Thin Strava MCP server built on the shared Strava service layer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from strava_mcp.strava import (
    StravaActivityStreams,
    StravaActivitySummary,
    StravaAthlete,
    StravaAthleteStats,
    StravaAthleteZones,
    StravaDetailedActivity,
    StravaService,
)
from strava_mcp.strava.contracts import StravaStreamType


class AthleteProfileResponse(BaseModel):
    athlete: StravaAthlete


class AthleteStatsResponse(BaseModel):
    athlete_stats: StravaAthleteStats


class AthleteZonesResponse(BaseModel):
    athlete_zones: StravaAthleteZones


class ActivityListResponse(BaseModel):
    activities: list[StravaActivitySummary]
    page: int
    per_page: int
    before: datetime | None = None
    after: datetime | None = None


class ActivityDetailResponse(BaseModel):
    activity: StravaDetailedActivity


class ActivityStreamsResponse(BaseModel):
    activity_id: int
    stream_types: tuple[StravaStreamType, ...]
    resolution: str
    series_type: str
    streams: StravaActivityStreams


ServiceFactory = Callable[[], StravaService]


def create_server(
    *,
    service_factory: ServiceFactory | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create the Strava MCP server."""

    resolved_service_factory = service_factory or StravaService
    server = FastMCP(
        name="strava",
        instructions=(
            "Read-only Strava athlete and activity inspection using the local "
            "Strava auth state managed by strava_mcp.strava."
        ),
        host=host,
        port=port,
        dependencies=("mcp",),
    )

    @server.tool(
        name="get_athlete_profile",
        description="Return the authenticated athlete profile.",
        structured_output=True,
    )
    def get_athlete_profile() -> AthleteProfileResponse:
        return AthleteProfileResponse(athlete=resolved_service_factory().get_athlete())

    @server.tool(
        name="get_athlete_stats",
        description="Return aggregate statistics for the authenticated athlete.",
        structured_output=True,
    )
    def get_athlete_stats() -> AthleteStatsResponse:
        return AthleteStatsResponse(
            athlete_stats=resolved_service_factory().get_athlete_stats()
        )

    @server.tool(
        name="get_athlete_zones",
        description="Return configured heart-rate and power zones for the athlete.",
        structured_output=True,
    )
    def get_athlete_zones() -> AthleteZonesResponse:
        return AthleteZonesResponse(
            athlete_zones=resolved_service_factory().get_athlete_zones()
        )

    @server.tool(
        name="list_activities",
        description="List activities for the authenticated athlete.",
        structured_output=True,
    )
    def list_activities(
        before: datetime | None = None,
        after: datetime | None = None,
        page: Annotated[int, Field(ge=1)] = 1,
        per_page: Annotated[int, Field(ge=1, le=200)] = 30,
    ) -> ActivityListResponse:
        service = resolved_service_factory()
        activities = service.list_activities(
            before=before,
            after=after,
            page=page,
            per_page=per_page,
        )
        return ActivityListResponse(
            activities=activities,
            page=page,
            per_page=per_page,
            before=before,
            after=after,
        )

    @server.tool(
        name="get_activity_detail",
        description="Return a detailed Strava activity payload by ID.",
        structured_output=True,
    )
    def get_activity_detail(
        activity_id: Annotated[int, Field(gt=0)],
    ) -> ActivityDetailResponse:
        service = resolved_service_factory()
        return ActivityDetailResponse(
            activity=service.get_activity(activity_id=activity_id)
        )

    @server.tool(
        name="get_activity_streams",
        description="Return selected streams for a Strava activity.",
        structured_output=True,
    )
    def get_activity_streams(
        activity_id: Annotated[int, Field(gt=0)],
        stream_types: Annotated[list[StravaStreamType], Field(min_length=1)],
        resolution: Literal["low", "medium", "high"] = "medium",
        series_type: Literal["time", "distance"] = "time",
    ) -> ActivityStreamsResponse:
        service = resolved_service_factory()
        normalized_stream_types = tuple(dict.fromkeys(stream_types))
        return ActivityStreamsResponse(
            activity_id=activity_id,
            stream_types=normalized_stream_types,
            resolution=resolution,
            series_type=series_type,
            streams=service.get_activity_streams(
                activity_id=activity_id,
                stream_types=normalized_stream_types,
                resolution=resolution,
                series_type=series_type,
            ),
        )

    return server

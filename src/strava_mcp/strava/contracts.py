"""Typed Strava contracts shared by downstream consumers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


STRAVA_SCOPE_ACTIVITY_READ = "activity:read"
STRAVA_SCOPE_ACTIVITY_READ_ALL = "activity:read_all"
STRAVA_SCOPE_PROFILE_READ_ALL = "profile:read_all"

DEFAULT_PERSONAL_DATA_SCOPES = (
    STRAVA_SCOPE_ACTIVITY_READ_ALL,
    STRAVA_SCOPE_PROFILE_READ_ALL,
)

StravaStreamType = Literal[
    "time",
    "distance",
    "latlng",
    "altitude",
    "velocity_smooth",
    "heartrate",
    "cadence",
    "watts",
    "temp",
    "moving",
    "grade_smooth",
]

STRAVA_STREAM_TYPES: tuple[StravaStreamType, ...] = (
    "time",
    "distance",
    "latlng",
    "altitude",
    "velocity_smooth",
    "heartrate",
    "cadence",
    "watts",
    "temp",
    "moving",
    "grade_smooth",
)


class StravaBaseModel(BaseModel):
    """Base model that accepts forward-compatible fields from Strava."""

    model_config = ConfigDict(extra="allow")


class StravaAppCredentials(BaseModel):
    """Credentials for a Strava API application."""

    client_id: int = Field(gt=0)
    client_secret: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)


class StravaTokenSet(BaseModel):
    """Persisted Strava token material."""

    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    expires_at: datetime
    token_type: str = Field(default="Bearer", min_length=1)


class StravaSessionState(BaseModel):
    """Shared local Strava session state."""

    athlete_id: int | None = Field(default=None, gt=0)
    scopes: tuple[str, ...] = Field(default_factory=tuple)
    token: StravaTokenSet
    created_at: datetime
    updated_at: datetime


class StravaAuthorizationRequest(BaseModel):
    """Authorization URL and associated callback expectations."""

    authorization_url: str
    state: str
    scopes: tuple[str, ...]
    redirect_uri: str
    approval_prompt: str


class StravaAuthorizationResponse(BaseModel):
    """Authorization-code callback payload returned to the redirect URI."""

    code: str = Field(min_length=1)
    state: str = Field(min_length=1)
    scopes: tuple[str, ...] = Field(default_factory=tuple)
    redirect_uri: str = Field(min_length=1)


class StravaResourceState(StravaBaseModel):
    """Minimal resource metadata returned in embedded Strava entities."""

    id: int | None = None
    resource_state: int | None = None


class StravaAthlete(StravaResourceState):
    """Authenticated athlete profile."""

    firstname: str | None = None
    lastname: str | None = None
    username: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    sex: str | None = None
    summit: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class StravaAthleteStats(StravaBaseModel):
    """Aggregate athlete statistics."""

    biggest_ride_distance: float | None = None
    biggest_climb_elevation_gain: float | None = None
    recent_ride_totals: dict[str, float | int | None] | None = None
    recent_run_totals: dict[str, float | int | None] | None = None
    recent_swim_totals: dict[str, float | int | None] | None = None
    ytd_ride_totals: dict[str, float | int | None] | None = None
    ytd_run_totals: dict[str, float | int | None] | None = None
    ytd_swim_totals: dict[str, float | int | None] | None = None
    all_ride_totals: dict[str, float | int | None] | None = None
    all_run_totals: dict[str, float | int | None] | None = None
    all_swim_totals: dict[str, float | int | None] | None = None


class StravaHeartRateZone(StravaBaseModel):
    """Heart rate zone definition."""

    min: int | None = None
    max: int | None = None


class StravaPowerZone(StravaBaseModel):
    """Power zone definition."""

    min: int | None = None
    max: int | None = None


class StravaHeartRateZoneRanges(StravaBaseModel):
    """Heart rate zone payload returned by the athlete zones endpoint."""

    custom_zones: bool | None = None
    zones: list[StravaHeartRateZone] = Field(default_factory=list)


class StravaPowerZoneRanges(StravaBaseModel):
    """Power zone payload returned by the athlete zones endpoint."""

    zones: list[StravaPowerZone] = Field(default_factory=list)


class StravaAthleteZones(StravaBaseModel):
    """Athlete zone payload."""

    heart_rate: StravaHeartRateZoneRanges | None = None
    power: StravaPowerZoneRanges | None = None


class StravaMap(StravaBaseModel):
    """Map payload embedded in activity responses."""

    id: str | None = None
    summary_polyline: str | None = None
    polyline: str | None = None


class StravaActivitySummary(StravaResourceState):
    """Summary activity returned from list endpoints."""

    name: str | None = None
    distance: float | None = None
    moving_time: int | None = None
    elapsed_time: int | None = None
    total_elevation_gain: float | None = None
    type: str | None = None
    sport_type: str | None = None
    workout_type: int | None = None
    start_date: datetime | None = None
    start_date_local: datetime | None = None
    timezone: str | None = None
    utc_offset: float | None = None
    average_speed: float | None = None
    max_speed: float | None = None
    average_watts: float | None = None
    weighted_average_watts: int | None = None
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    elev_high: float | None = None
    elev_low: float | None = None
    kudos_count: int | None = None
    comment_count: int | None = None
    athlete_count: int | None = None
    photo_count: int | None = None
    trainer: bool | None = None
    commute: bool | None = None
    manual: bool | None = None
    private: bool | None = None
    flagged: bool | None = None
    average_cadence: float | None = None
    average_temp: int | None = None
    has_heartrate: bool | None = None
    device_watts: bool | None = None
    kilojoules: float | None = None
    map: StravaMap | None = None
    athlete: StravaAthlete | None = None


class StravaDetailedActivity(StravaActivitySummary):
    """Detailed activity payload."""

    description: str | None = None
    calories: float | None = None
    suffer_score: int | None = None
    segment_efforts: list[dict] | None = None
    splits_metric: list[dict] | None = None
    splits_standard: list[dict] | None = None


class StravaStream(StravaBaseModel):
    """Single stream series."""

    type: str | None = None
    series_type: str | None = None
    original_size: int | None = None
    resolution: str | None = None
    data: list[int | float | bool | list[float]] = Field(default_factory=list)


class StravaActivityStreams(StravaBaseModel):
    """Selected activity streams keyed by type."""

    time: StravaStream | None = None
    distance: StravaStream | None = None
    latlng: StravaStream | None = None
    altitude: StravaStream | None = None
    velocity_smooth: StravaStream | None = None
    heartrate: StravaStream | None = None
    cadence: StravaStream | None = None
    watts: StravaStream | None = None
    temp: StravaStream | None = None
    moving: StravaStream | None = None
    grade_smooth: StravaStream | None = None

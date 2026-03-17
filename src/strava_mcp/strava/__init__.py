"""Reusable Strava auth/session and read-only API integration layer."""

from strava_mcp.strava.client import StravaApiClient, StravaService
from strava_mcp.strava.contracts import (
    DEFAULT_PERSONAL_DATA_SCOPES,
    STRAVA_SCOPE_ACTIVITY_READ,
    STRAVA_SCOPE_ACTIVITY_READ_ALL,
    STRAVA_SCOPE_PROFILE_READ_ALL,
    STRAVA_STREAM_TYPES,
    StravaActivityStreams,
    StravaActivitySummary,
    StravaAppCredentials,
    StravaAthlete,
    StravaAthleteStats,
    StravaAthleteZones,
    StravaAuthorizationRequest,
    StravaAuthorizationResponse,
    StravaDetailedActivity,
    StravaSessionState,
    StravaTokenSet,
)
from strava_mcp.strava.errors import (
    StravaApiError,
    StravaAuthError,
    StravaConfigurationError,
    StravaError,
    StravaMissingScopeError,
    StravaUnavailableStreamError,
)
from strava_mcp.strava.oauth import StravaOAuthClient
from strava_mcp.strava.storage import DEFAULT_STRAVA_ROOT, StravaAuthStorage

__all__ = [
    "DEFAULT_PERSONAL_DATA_SCOPES",
    "DEFAULT_STRAVA_ROOT",
    "STRAVA_SCOPE_ACTIVITY_READ",
    "STRAVA_SCOPE_ACTIVITY_READ_ALL",
    "STRAVA_SCOPE_PROFILE_READ_ALL",
    "STRAVA_STREAM_TYPES",
    "StravaActivityStreams",
    "StravaActivitySummary",
    "StravaApiClient",
    "StravaApiError",
    "StravaAppCredentials",
    "StravaAthlete",
    "StravaAthleteStats",
    "StravaAthleteZones",
    "StravaAuthError",
    "StravaAuthStorage",
    "StravaAuthorizationRequest",
    "StravaAuthorizationResponse",
    "StravaConfigurationError",
    "StravaDetailedActivity",
    "StravaError",
    "StravaMissingScopeError",
    "StravaOAuthClient",
    "StravaService",
    "StravaSessionState",
    "StravaTokenSet",
    "StravaUnavailableStreamError",
]

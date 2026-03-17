"""Error types for the reusable Strava integration layer."""

from __future__ import annotations


class StravaError(RuntimeError):
    """Base Strava integration error."""


class StravaConfigurationError(StravaError):
    """Raised when local configuration is missing or invalid."""


class StravaAuthError(StravaError):
    """Raised when authentication or token state is invalid."""


class StravaMissingScopeError(StravaAuthError):
    """Raised when the stored session does not include a required scope."""

    def __init__(
        self,
        *,
        required_scopes: tuple[str, ...],
        granted_scopes: tuple[str, ...],
    ) -> None:
        required = ", ".join(required_scopes)
        granted = ", ".join(granted_scopes) or "<none>"
        super().__init__(
            f"Strava session is missing required scopes ({required}); granted: {granted}"
        )
        self.required_scopes = required_scopes
        self.granted_scopes = granted_scopes


class StravaApiError(StravaError):
    """Raised when the Strava API returns an error response."""

    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(f"Strava API request failed ({status_code}): {message}")
        self.status_code = status_code
        self.message = message
        self.details = details or []


class StravaUnavailableStreamError(StravaError):
    """Raised when Strava omits one or more requested activity streams."""

    def __init__(
        self,
        *,
        activity_id: int,
        requested_streams: tuple[str, ...],
        missing_streams: tuple[str, ...],
    ) -> None:
        missing = ", ".join(missing_streams)
        requested = ", ".join(requested_streams)
        super().__init__(
            f"Strava activity {activity_id} is missing requested streams: {missing} "
            f"(requested: {requested})"
        )
        self.activity_id = activity_id
        self.requested_streams = requested_streams
        self.missing_streams = missing_streams

"""Typed Strava client and session-aware service facade."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from strava_mcp.strava.contracts import (
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
    StravaDetailedActivity,
    StravaSessionState,
)
from strava_mcp.strava.errors import (
    StravaApiError,
    StravaAuthError,
    StravaMissingScopeError,
    StravaUnavailableStreamError,
)
from strava_mcp.strava.oauth import StravaOAuthClient
from strava_mcp.strava.storage import StravaAuthStorage


_DEFAULT_API_BASE_URL = "https://www.strava.com/api/v3"
_ACTIVITY_SCOPE_ALIASES = {
    STRAVA_SCOPE_ACTIVITY_READ: frozenset(
        {STRAVA_SCOPE_ACTIVITY_READ, STRAVA_SCOPE_ACTIVITY_READ_ALL}
    ),
    STRAVA_SCOPE_ACTIVITY_READ_ALL: frozenset({STRAVA_SCOPE_ACTIVITY_READ_ALL}),
}


class StravaApiClient:
    """Low-level typed Strava API client."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_API_BASE_URL,
        urlopen: Callable[..., object] = urllib_request.urlopen,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._urlopen = urlopen
        self.timeout_seconds = timeout_seconds

    def get_athlete(self, *, access_token: str) -> StravaAthlete:
        payload = self._request_json(path="/athlete", access_token=access_token)
        return StravaAthlete.model_validate(payload)

    def get_athlete_stats(
        self, *, access_token: str, athlete_id: int
    ) -> StravaAthleteStats:
        payload = self._request_json(
            path=f"/athletes/{athlete_id}/stats",
            access_token=access_token,
        )
        return StravaAthleteStats.model_validate(payload)

    def get_athlete_zones(self, *, access_token: str) -> StravaAthleteZones:
        payload = self._request_json(path="/athlete/zones", access_token=access_token)
        return StravaAthleteZones.model_validate(payload)

    def list_activities(
        self,
        *,
        access_token: str,
        before: datetime | None = None,
        after: datetime | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[StravaActivitySummary]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= per_page <= 200:
            raise ValueError("per_page must be between 1 and 200")
        payload = self._request_json(
            path="/athlete/activities",
            access_token=access_token,
            query={
                "before": _timestamp_or_none(before),
                "after": _timestamp_or_none(after),
                "page": page,
                "per_page": per_page,
            },
        )
        if not isinstance(payload, list):
            raise StravaAuthError("Strava activity list response was not a JSON array")
        return [StravaActivitySummary.model_validate(item) for item in payload]

    def get_activity(
        self, *, access_token: str, activity_id: int
    ) -> StravaDetailedActivity:
        payload = self._request_json(
            path=f"/activities/{activity_id}",
            access_token=access_token,
        )
        return StravaDetailedActivity.model_validate(payload)

    def get_activity_streams(
        self,
        *,
        access_token: str,
        activity_id: int,
        stream_types: Iterable[str],
        resolution: str = "medium",
        series_type: str = "time",
    ) -> StravaActivityStreams:
        normalized_stream_types = tuple(
            dict.fromkeys(stream_type for stream_type in stream_types if stream_type)
        )
        if not normalized_stream_types:
            raise ValueError("At least one activity stream type is required")
        unsupported = sorted(set(normalized_stream_types) - set(STRAVA_STREAM_TYPES))
        if unsupported:
            unsupported_text = ", ".join(unsupported)
            raise ValueError(f"Unsupported Strava stream types: {unsupported_text}")
        payload = self._request_json(
            path=f"/activities/{activity_id}/streams",
            access_token=access_token,
            query={
                "keys": ",".join(normalized_stream_types),
                "key_by_type": "true",
                "resolution": resolution,
                "series_type": series_type,
            },
        )
        streams = StravaActivityStreams.model_validate(payload)
        missing_streams = tuple(
            stream_type
            for stream_type in normalized_stream_types
            if getattr(streams, stream_type) is None
        )
        if missing_streams:
            raise StravaUnavailableStreamError(
                activity_id=activity_id,
                requested_streams=normalized_stream_types,
                missing_streams=missing_streams,
            )
        return streams

    def _request_json(
        self,
        *,
        path: str,
        access_token: str,
        query: dict[str, object] | None = None,
    ) -> dict | list:
        encoded_query = urllib_parse.urlencode(
            {key: value for key, value in (query or {}).items() if value is not None}
        )
        url = f"{self.base_url}{path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        request = urllib_request.Request(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except urllib_error.HTTPError as exc:
            raise _strava_api_error_from_http(exc) from exc
        except urllib_error.URLError as exc:
            raise StravaApiError(status_code=0, message=str(exc.reason)) from exc
        if not isinstance(payload, (dict, list)):
            raise StravaApiError(
                status_code=0,
                message="Strava API response was not JSON object or array",
            )
        return payload


class StravaService:
    """Session-aware Strava service facade for downstream consumers."""

    def __init__(
        self,
        *,
        storage: StravaAuthStorage | None = None,
        oauth_client: StravaOAuthClient | None = None,
        api_client: StravaApiClient | None = None,
        refresh_buffer: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage or StravaAuthStorage()
        self.oauth_client = oauth_client or StravaOAuthClient()
        self.api_client = api_client or StravaApiClient()
        self.refresh_buffer = refresh_buffer
        self._clock = clock or (lambda: datetime.now(UTC))

    def load_app_credentials(self) -> StravaAppCredentials:
        return self.storage.load_app_credentials()

    def save_app_credentials(self, credentials: StravaAppCredentials) -> None:
        self.storage.save_app_credentials(credentials)

    def load_session(self, *, required: bool = True) -> StravaSessionState | None:
        return self.storage.load_session(required=required)

    def prepare_authorization(
        self,
        *,
        scopes: Iterable[str],
        approval_prompt: str = "auto",
        state: str | None = None,
    ) -> StravaAuthorizationRequest:
        credentials = self.storage.load_app_credentials()
        return self.oauth_client.prepare_authorization(
            app_credentials=credentials,
            scopes=scopes,
            approval_prompt=approval_prompt,
            state=state,
        )

    def complete_authorization(
        self,
        *,
        authorization_request: StravaAuthorizationRequest,
        callback_url: str,
    ) -> StravaSessionState:
        credentials = self.storage.load_app_credentials()
        session = self.oauth_client.complete_authorization(
            app_credentials=credentials,
            authorization_request=authorization_request,
            callback_url=callback_url,
        )
        self.storage.save_session(session)
        return session

    def get_athlete(self) -> StravaAthlete:
        session = self._ensure_session(required_scopes=())
        athlete = self.api_client.get_athlete(access_token=session.token.access_token)
        if session.athlete_id == athlete.id or athlete.id is None:
            return athlete

        def persist_athlete_id(current: StravaSessionState | None) -> StravaAthlete:
            if current is None:
                return athlete
            updated = current.model_copy(
                update={"athlete_id": athlete.id, "updated_at": self._clock()}
            )
            self.storage.save_session(updated)
            return athlete

        return self.storage.update_session(persist_athlete_id)

    def get_athlete_stats(self) -> StravaAthleteStats:
        session = self._ensure_session(required_scopes=())
        athlete_id = session.athlete_id or self.get_athlete().id
        if athlete_id is None:
            raise StravaAuthError(
                "Unable to resolve athlete ID from the current session"
            )
        return self.api_client.get_athlete_stats(
            access_token=session.token.access_token,
            athlete_id=athlete_id,
        )

    def get_athlete_zones(self) -> StravaAthleteZones:
        session = self._ensure_session(required_scopes=(STRAVA_SCOPE_PROFILE_READ_ALL,))
        return self.api_client.get_athlete_zones(
            access_token=session.token.access_token
        )

    def list_activities(
        self,
        *,
        before: datetime | None = None,
        after: datetime | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[StravaActivitySummary]:
        session = self._ensure_session(required_scopes=(STRAVA_SCOPE_ACTIVITY_READ,))
        return self.api_client.list_activities(
            access_token=session.token.access_token,
            before=before,
            after=after,
            page=page,
            per_page=per_page,
        )

    def get_activity(self, *, activity_id: int) -> StravaDetailedActivity:
        session = self._ensure_session(required_scopes=(STRAVA_SCOPE_ACTIVITY_READ,))
        return self.api_client.get_activity(
            access_token=session.token.access_token,
            activity_id=activity_id,
        )

    def get_activity_streams(
        self,
        *,
        activity_id: int,
        stream_types: Iterable[str],
        resolution: str = "medium",
        series_type: str = "time",
    ) -> StravaActivityStreams:
        session = self._ensure_session(required_scopes=(STRAVA_SCOPE_ACTIVITY_READ,))
        return self.api_client.get_activity_streams(
            access_token=session.token.access_token,
            activity_id=activity_id,
            stream_types=stream_types,
            resolution=resolution,
            series_type=series_type,
        )

    def _ensure_session(
        self, *, required_scopes: tuple[str, ...]
    ) -> StravaSessionState:
        credentials = self.storage.load_app_credentials(required=False)

        def ensure(current: StravaSessionState | None) -> StravaSessionState:
            if current is None:
                raise StravaAuthError(
                    "Strava session not found. Run authorization before calling the API."
                )
            _validate_scopes(current.scopes, required_scopes)
            if not self._session_needs_refresh(current):
                return current
            if credentials is None:
                raise StravaAuthError(
                    "Strava session has expired and no app credentials are available to "
                    "refresh it"
                )
            refreshed = self.oauth_client.refresh_session(
                app_credentials=credentials,
                session=current,
            ).model_copy(update={"updated_at": self._clock()})
            self.storage.save_session(refreshed)
            return refreshed

        return self.storage.update_session(ensure)

    def _session_needs_refresh(self, session: StravaSessionState) -> bool:
        refresh_after = session.token.expires_at - self.refresh_buffer
        return self._clock() >= refresh_after


def _validate_scopes(
    granted_scopes: tuple[str, ...], required_scopes: tuple[str, ...]
) -> None:
    granted_scope_set = set(granted_scopes)
    missing_scopes = []
    for required_scope in required_scopes:
        allowed_scopes = _ACTIVITY_SCOPE_ALIASES.get(
            required_scope, frozenset({required_scope})
        )
        if granted_scope_set.isdisjoint(allowed_scopes):
            missing_scopes.append(required_scope)
    if missing_scopes:
        raise StravaMissingScopeError(
            required_scopes=tuple(missing_scopes),
            granted_scopes=granted_scopes,
        )


def _timestamp_or_none(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def _strava_api_error_from_http(exc: urllib_error.HTTPError) -> StravaApiError:
    raw_body = exc.read().decode("utf-8", errors="replace").strip()
    message = raw_body or exc.reason or "unknown error"
    details: list[dict] = []
    if raw_body:
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = str(payload.get("message") or message)
            if isinstance(payload.get("errors"), list):
                details = [item for item in payload["errors"] if isinstance(item, dict)]
    return StravaApiError(status_code=exc.code, message=message, details=details)

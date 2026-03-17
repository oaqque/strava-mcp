"""OAuth helpers for the reusable Strava integration layer."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from strava_mcp.strava.contracts import (
    StravaAppCredentials,
    StravaAuthorizationRequest,
    StravaAuthorizationResponse,
    StravaSessionState,
    StravaTokenSet,
)
from strava_mcp.strava.errors import StravaApiError, StravaAuthError


_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"


class StravaOAuthClient:
    """OAuth helper for authorization-code login and token refresh."""

    def __init__(
        self,
        *,
        authorize_url: str = _AUTHORIZE_URL,
        token_url: str = _TOKEN_URL,
        urlopen: Callable[..., object] = urllib_request.urlopen,
        clock: Callable[[], datetime] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.authorize_url = authorize_url
        self.token_url = token_url
        self._urlopen = urlopen
        self._clock = clock or (lambda: datetime.now(UTC))
        self.timeout_seconds = timeout_seconds

    def prepare_authorization(
        self,
        *,
        app_credentials: StravaAppCredentials,
        scopes: Iterable[str],
        approval_prompt: str = "auto",
        state: str | None = None,
    ) -> StravaAuthorizationRequest:
        normalized_scopes = tuple(
            dict.fromkeys(scope.strip() for scope in scopes if scope)
        )
        if not normalized_scopes:
            raise StravaAuthError("At least one Strava scope is required")
        resolved_state = state or secrets.token_urlsafe(24)
        query = urllib_parse.urlencode(
            {
                "client_id": str(app_credentials.client_id),
                "redirect_uri": app_credentials.redirect_uri,
                "response_type": "code",
                "approval_prompt": approval_prompt,
                "scope": ",".join(normalized_scopes),
                "state": resolved_state,
            }
        )
        return StravaAuthorizationRequest(
            authorization_url=f"{self.authorize_url}?{query}",
            state=resolved_state,
            scopes=normalized_scopes,
            redirect_uri=app_credentials.redirect_uri,
            approval_prompt=approval_prompt,
        )

    def complete_authorization(
        self,
        *,
        app_credentials: StravaAppCredentials,
        authorization_request: StravaAuthorizationRequest,
        callback_url: str,
    ) -> StravaSessionState:
        authorization_response = self.parse_authorization_response(
            authorization_request=authorization_request,
            callback_url=callback_url,
        )
        return self.exchange_authorization_code(
            app_credentials=app_credentials,
            code=authorization_response.code,
            scopes=authorization_response.scopes,
        )

    def parse_authorization_response(
        self,
        *,
        authorization_request: StravaAuthorizationRequest,
        callback_url: str,
    ) -> StravaAuthorizationResponse:
        parsed_callback = urllib_parse.urlparse(callback_url)
        parsed_redirect = urllib_parse.urlparse(authorization_request.redirect_uri)
        if not parsed_callback.scheme or not parsed_callback.netloc:
            raise StravaAuthError(
                "Strava authorization completion requires a full callback URL"
            )
        if _normalized_redirect_uri(parsed_callback) != _normalized_redirect_uri(
            parsed_redirect
        ):
            raise StravaAuthError(
                "Strava authorization callback URL did not match the configured redirect URI"
            )

        query = urllib_parse.parse_qs(parsed_callback.query)
        error = _first_query_value(query, "error")
        if isinstance(error, str) and error:
            raise StravaAuthError(f"Strava authorization failed: {error}")

        state = _first_query_value(query, "state")
        if state != authorization_request.state:
            raise StravaAuthError(
                "Strava authorization callback returned an unexpected state"
            )

        code = _first_query_value(query, "code")
        if not isinstance(code, str) or not code:
            raise StravaAuthError(
                "Strava authorization callback did not include a code"
            )

        scopes = _parse_scopes(_first_query_value(query, "scope"))
        if not scopes:
            scopes = authorization_request.scopes

        return StravaAuthorizationResponse(
            code=code,
            state=state,
            scopes=scopes,
            redirect_uri=_normalized_redirect_uri(parsed_callback),
        )

    def exchange_authorization_code(
        self,
        *,
        app_credentials: StravaAppCredentials,
        code: str,
        scopes: Iterable[str],
    ) -> StravaSessionState:
        payload = self._post_form(
            {
                "client_id": str(app_credentials.client_id),
                "client_secret": app_credentials.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            }
        )
        return self._token_payload_to_session(
            payload=payload, scopes=tuple(scopes), created=True
        )

    def refresh_session(
        self,
        *,
        app_credentials: StravaAppCredentials,
        session: StravaSessionState,
    ) -> StravaSessionState:
        payload = self._post_form(
            {
                "client_id": str(app_credentials.client_id),
                "client_secret": app_credentials.client_secret,
                "refresh_token": session.token.refresh_token,
                "grant_type": "refresh_token",
            }
        )
        refreshed = self._token_payload_to_session(
            payload=payload,
            scopes=session.scopes,
            created=False,
        )
        return refreshed.model_copy(update={"created_at": session.created_at})

    def _post_form(self, form_data: dict[str, str]) -> dict:
        request = urllib_request.Request(
            self.token_url,
            data=urllib_parse.urlencode(form_data).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except urllib_error.HTTPError as exc:
            raise _strava_api_error_from_http(exc) from exc
        except urllib_error.URLError as exc:
            raise StravaAuthError(f"Strava OAuth request failed: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise StravaAuthError("Strava OAuth response was not a JSON object")
        return payload

    def _token_payload_to_session(
        self,
        *,
        payload: dict,
        scopes: tuple[str, ...],
        created: bool,
    ) -> StravaSessionState:
        try:
            access_token = str(payload["access_token"])
            refresh_token = str(payload["refresh_token"])
            expires_at = int(payload["expires_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StravaAuthError(
                "Strava OAuth response is missing required token fields"
            ) from exc
        athlete_payload = payload.get("athlete")
        athlete_id = (
            athlete_payload.get("id") if isinstance(athlete_payload, dict) else None
        )
        now = self._clock()
        token = StravaTokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
            token_type=str(payload.get("token_type", "Bearer")),
        )
        return StravaSessionState(
            athlete_id=int(athlete_id) if athlete_id else None,
            scopes=tuple(dict.fromkeys(scopes)),
            token=token,
            created_at=now,
            updated_at=now,
        )


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _parse_scopes(raw_scopes: str | None) -> tuple[str, ...]:
    if not raw_scopes:
        return ()
    return tuple(dict.fromkeys(raw_scopes.replace(",", " ").split()))


def _normalized_redirect_uri(parsed_uri: urllib_parse.ParseResult) -> str:
    return urllib_parse.urlunparse(
        (
            parsed_uri.scheme,
            parsed_uri.netloc,
            parsed_uri.path or "/",
            "",
            "",
            "",
        )
    )


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

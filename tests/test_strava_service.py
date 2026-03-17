"""Unit tests for the reusable Strava service layer."""

from __future__ import annotations

import json
import multiprocessing
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from strava_mcp.strava import (
    STRAVA_SCOPE_ACTIVITY_READ_ALL,
    STRAVA_SCOPE_PROFILE_READ_ALL,
    StravaActivityStreams,
    StravaApiClient,
    StravaAppCredentials,
    StravaAthlete,
    StravaAuthError,
    StravaMissingScopeError,
    StravaOAuthClient,
    StravaService,
    StravaUnavailableStreamError,
)
from strava_mcp.strava.contracts import (
    STRAVA_SCOPE_ACTIVITY_READ,
    StravaSessionState,
    StravaTokenSet,
)
from strava_mcp.strava.storage import StravaAuthStorage


class _JsonResponse:
    def __init__(self, payload: dict | list) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _RecordingApiClient:
    def __init__(self) -> None:
        self.access_tokens: list[str] = []

    def get_athlete(self, *, access_token: str) -> StravaAthlete:
        self.access_tokens.append(access_token)
        return StravaAthlete(id=42, firstname="Test")


def _build_session(
    *,
    access_token: str = "access-token",
    refresh_token: str = "refresh-token",
    expires_at: datetime | None = None,
    scopes: tuple[str, ...] = (
        STRAVA_SCOPE_ACTIVITY_READ_ALL,
        STRAVA_SCOPE_PROFILE_READ_ALL,
    ),
    athlete_id: int = 7,
) -> StravaSessionState:
    now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    return StravaSessionState(
        athlete_id=athlete_id,
        scopes=scopes,
        token=StravaTokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at or now + timedelta(hours=1),
        ),
        created_at=now,
        updated_at=now,
    )


def _lock_worker(
    root: str, label: str, started_queue: multiprocessing.Queue[str]
) -> None:
    storage = StravaAuthStorage(Path(root))
    log_path = Path(root) / "lock-order.log"

    def mutate(_current: StravaSessionState | None) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{label}-start\n")
        started_queue.put(label)
        time.sleep(0.2)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{label}-end\n")
        return None

    storage.update_session(mutate, timeout_seconds=5.0)


def test_storage_uses_env_app_credentials_when_file_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("STRAVA_CLIENT_ID", "12345")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "top-secret")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "http://127.0.0.1:8765/exchange_token")

    storage = StravaAuthStorage(tmp_path / "vault" / "strava")

    credentials = storage.load_app_credentials()

    assert credentials.client_id == 12345
    assert credentials.client_secret == "top-secret"
    assert credentials.redirect_uri == "http://127.0.0.1:8765/exchange_token"


def test_complete_authorization_parses_callback_url_and_exchanges_code():
    credentials = StravaAppCredentials(
        client_id=12345,
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8765/exchange_token",
    )
    now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://www.strava.com/api/v3/oauth/token"
        body = request.data.decode("utf-8")
        assert "grant_type=authorization_code" in body
        assert "code=test-code" in body
        return _JsonResponse(
            {
                "token_type": "Bearer",
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": int((now + timedelta(hours=6)).timestamp()),
                "athlete": {"id": 99},
            }
        )

    oauth_client = StravaOAuthClient(urlopen=fake_urlopen, clock=lambda: now)
    auth_request = oauth_client.prepare_authorization(
        app_credentials=credentials,
        scopes=(STRAVA_SCOPE_ACTIVITY_READ_ALL, STRAVA_SCOPE_PROFILE_READ_ALL),
    )

    session = oauth_client.complete_authorization(
        app_credentials=credentials,
        authorization_request=auth_request,
        callback_url=(
            "http://127.0.0.1:8765/exchange_token"
            "?code=test-code&scope=activity:read_all,profile:read_all"
            f"&state={auth_request.state}"
        ),
    )

    assert session.athlete_id == 99
    assert session.token.access_token == "new-access"
    assert session.scopes == (
        STRAVA_SCOPE_ACTIVITY_READ_ALL,
        STRAVA_SCOPE_PROFILE_READ_ALL,
    )


def test_complete_authorization_rejects_mismatched_redirect_uri():
    credentials = StravaAppCredentials(
        client_id=12345,
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8765/exchange_token",
    )
    oauth_client = StravaOAuthClient()
    auth_request = oauth_client.prepare_authorization(
        app_credentials=credentials,
        scopes=(STRAVA_SCOPE_ACTIVITY_READ_ALL,),
        state="expected-state",
    )

    with pytest.raises(StravaAuthError, match="configured redirect URI"):
        oauth_client.complete_authorization(
            app_credentials=credentials,
            authorization_request=auth_request,
            callback_url=(
                "http://127.0.0.1:8765/other_path"
                "?code=test-code&scope=activity:read_all&state=expected-state"
            ),
        )


def test_service_refreshes_expired_session_and_persists_new_tokens(tmp_path):
    now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    storage = StravaAuthStorage(tmp_path / "vault" / "strava")
    storage.save_app_credentials(
        StravaAppCredentials(
            client_id=12345,
            client_secret="secret",
            redirect_uri="http://127.0.0.1:8765/exchange_token",
        )
    )
    storage.save_session(
        _build_session(
            access_token="expired-access",
            refresh_token="expired-refresh",
            expires_at=now + timedelta(minutes=1),
        )
    )

    def fake_urlopen(request, timeout):
        body = request.data.decode("utf-8")
        assert "grant_type=refresh_token" in body
        assert "refresh_token=expired-refresh" in body
        return _JsonResponse(
            {
                "token_type": "Bearer",
                "access_token": "fresh-access",
                "refresh_token": "fresh-refresh",
                "expires_at": int((now + timedelta(hours=6)).timestamp()),
                "athlete": {"id": 42},
            }
        )

    api_client = _RecordingApiClient()
    service = StravaService(
        storage=storage,
        oauth_client=StravaOAuthClient(urlopen=fake_urlopen, clock=lambda: now),
        api_client=api_client,
        clock=lambda: now,
        refresh_buffer=timedelta(minutes=5),
    )

    athlete = service.get_athlete()
    persisted_session = storage.load_session()

    assert athlete.id == 42
    assert api_client.access_tokens == ["fresh-access"]
    assert persisted_session.token.access_token == "fresh-access"
    assert persisted_session.token.refresh_token == "fresh-refresh"


def test_service_raises_missing_scope_for_zones(tmp_path):
    storage = StravaAuthStorage(tmp_path / "vault" / "strava")
    storage.save_app_credentials(
        StravaAppCredentials(
            client_id=12345,
            client_secret="secret",
            redirect_uri="http://127.0.0.1:8765/exchange_token",
        )
    )
    storage.save_session(_build_session(scopes=(STRAVA_SCOPE_ACTIVITY_READ_ALL,)))
    service = StravaService(storage=storage)

    with pytest.raises(StravaMissingScopeError, match="profile:read_all"):
        service.get_athlete_zones()


def test_api_client_list_activities_encodes_expected_query_params():
    observed: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        return _JsonResponse([{"id": 1, "name": "Morning Ride"}])

    client = StravaApiClient(urlopen=fake_urlopen)
    before = datetime(2026, 3, 20, 8, 0, tzinfo=UTC)
    after = datetime(2026, 3, 10, 8, 0, tzinfo=UTC)

    activities = client.list_activities(
        access_token="session-access",
        before=before,
        after=after,
        page=2,
        per_page=50,
    )

    assert len(activities) == 1
    assert observed["authorization"] == "Bearer session-access"
    assert "page=2" in str(observed["url"])
    assert "per_page=50" in str(observed["url"])
    assert f"before={int(before.timestamp())}" in str(observed["url"])
    assert f"after={int(after.timestamp())}" in str(observed["url"])


def test_api_client_parses_athlete_zones_with_boolean_custom_zones():
    def fake_urlopen(request, timeout):
        assert request.get_header("Authorization") == "Bearer session-access"
        return _JsonResponse(
            {
                "heart_rate": {
                    "custom_zones": False,
                    "zones": [
                        {"min": 0, "max": 129},
                        {"min": 129, "max": 160},
                    ],
                }
            }
        )

    client = StravaApiClient(urlopen=fake_urlopen)

    zones = client.get_athlete_zones(access_token="session-access")

    assert zones.heart_rate is not None
    assert zones.heart_rate.custom_zones is False
    assert [zone.min for zone in zones.heart_rate.zones] == [0, 129]
    assert [zone.max for zone in zones.heart_rate.zones] == [129, 160]


def test_api_client_raises_for_missing_requested_streams():
    def fake_urlopen(request, timeout):
        return _JsonResponse(
            {
                "heartrate": {
                    "type": "heartrate",
                    "data": [120, 121],
                    "series_type": "time",
                    "resolution": "medium",
                    "original_size": 2,
                }
            }
        )

    client = StravaApiClient(urlopen=fake_urlopen)

    with pytest.raises(StravaUnavailableStreamError, match="watts"):
        client.get_activity_streams(
            access_token="session-access",
            activity_id=123,
            stream_types=("heartrate", "watts"),
        )


def test_session_updates_are_serialized_by_lock(tmp_path):
    root = tmp_path / "vault" / "strava"
    started_queue: multiprocessing.Queue[str] = multiprocessing.Queue()
    first_process = multiprocessing.Process(
        target=_lock_worker,
        args=(str(root), "one", started_queue),
    )
    second_process = multiprocessing.Process(
        target=_lock_worker,
        args=(str(root), "two", started_queue),
    )

    first_process.start()
    assert started_queue.get(timeout=3.0) == "one"

    second_process.start()
    assert started_queue.get(timeout=3.0) == "two"

    first_process.join(timeout=5.0)
    second_process.join(timeout=5.0)

    assert first_process.exitcode == 0
    assert second_process.exitcode == 0
    log_lines = (root / "lock-order.log").read_text(encoding="utf-8").splitlines()
    assert log_lines == ["one-start", "one-end", "two-start", "two-end"]


def test_stream_response_model_remains_typed():
    streams = StravaActivityStreams.model_validate(
        {
            "latlng": {
                "type": "latlng",
                "series_type": "distance",
                "resolution": "medium",
                "original_size": 1,
                "data": [[151.2, -33.8]],
            }
        }
    )

    assert streams.latlng is not None
    assert streams.latlng.data == [[151.2, -33.8]]
    assert STRAVA_SCOPE_ACTIVITY_READ == "activity:read"

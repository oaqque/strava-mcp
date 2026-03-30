"""Unit tests for the Strava MCP auth CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from strava_mcp import main as strava_main
from strava_mcp.strava import (
    StravaAppCredentials,
    StravaAuthorizationRequest,
    StravaSessionState,
    StravaTokenSet,
)


class _FakeStorage:
    def __init__(self) -> None:
        self.app_path = Path("vault/strava/app.json")
        self.session_path = Path("vault/strava/session.json")
        self.credentials: StravaAppCredentials | None = StravaAppCredentials(
            client_id=12345,
            client_secret="top-secret",
            redirect_uri="http://127.0.0.1:8765/exchange_token",
        )

    def load_app_credentials(
        self, *, required: bool = True
    ) -> StravaAppCredentials | None:
        if self.credentials is None and required:
            raise RuntimeError("credentials missing")
        return self.credentials


class _FakeStravaService:
    def __init__(self) -> None:
        now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
        self.storage = _FakeStorage()
        self.prepare_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.saved_credentials: list[StravaAppCredentials] = []
        self.session = StravaSessionState(
            athlete_id=42,
            scopes=("activity:read_all", "profile:read_all"),
            token=StravaTokenSet(
                access_token="access-token",
                refresh_token="refresh-token",
                expires_at=now + timedelta(hours=6),
            ),
            created_at=now,
            updated_at=now,
        )

    def prepare_authorization(
        self,
        *,
        scopes: tuple[str, ...],
        approval_prompt: str = "auto",
        state: str | None = None,
    ) -> StravaAuthorizationRequest:
        self.prepare_calls.append(
            {
                "scopes": scopes,
                "approval_prompt": approval_prompt,
                "state": state,
            }
        )
        return StravaAuthorizationRequest(
            authorization_url="https://www.strava.com/oauth/authorize?state=test-state",
            state=state or "test-state",
            scopes=scopes,
            redirect_uri="http://127.0.0.1:8765/exchange_token",
            approval_prompt=approval_prompt,
        )

    def complete_authorization(
        self,
        *,
        authorization_request: StravaAuthorizationRequest,
        callback_url: str,
    ) -> StravaSessionState:
        self.complete_calls.append(
            {
                "authorization_request": authorization_request,
                "callback_url": callback_url,
            }
        )
        return self.session

    def save_app_credentials(self, credentials: StravaAppCredentials) -> None:
        self.saved_credentials.append(credentials)
        self.storage.credentials = credentials


def test_authorize_start_prints_follow_up_complete_command(monkeypatch, capsys):
    service = _FakeStravaService()
    monkeypatch.setattr(strava_main, "_build_service", lambda args: service)
    monkeypatch.setattr(strava_main.webbrowser, "open", lambda url: True)

    exit_code = strava_main.main(["authorize", "start", "--launch-browser"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "https://www.strava.com/oauth/authorize?state=test-state" in captured.out
    assert "uv run strava-mcp authorize complete --state test-state" in captured.out
    assert service.prepare_calls == [
        {
            "scopes": ("activity:read_all", "profile:read_all"),
            "approval_prompt": "auto",
            "state": None,
        }
    ]


def test_authorize_complete_accepts_callback_url_and_persists_session(
    monkeypatch, capsys
):
    service = _FakeStravaService()
    monkeypatch.setattr(strava_main, "_build_service", lambda args: service)

    exit_code = strava_main.main(
        [
            "authorize",
            "complete",
            "--state",
            "test-state",
            "--callback-url",
            (
                "http://127.0.0.1:8765/exchange_token"
                "?code=test-code&scope=activity:read_all,profile:read_all"
                "&state=test-state"
            ),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Saved shared Strava session to vault/strava/session.json." in captured.out
    assert "Authorized athlete ID: 42" in captured.out
    assert service.prepare_calls == [
        {
            "scopes": ("activity:read_all", "profile:read_all"),
            "approval_prompt": "auto",
            "state": "test-state",
        }
    ]
    assert service.complete_calls[0]["callback_url"].startswith(
        "http://127.0.0.1:8765/exchange_token?code=test-code"
    )


def test_authorize_start_bootstraps_app_credentials_when_missing(monkeypatch, capsys):
    service = _FakeStravaService()
    service.storage.credentials = None
    monkeypatch.setattr(strava_main, "_build_service", lambda args: service)
    monkeypatch.setattr(strava_main.IntPrompt, "ask", lambda prompt: 67890)
    monkeypatch.setattr(
        strava_main.Prompt,
        "ask",
        lambda prompt, default=None, password=False: (
            "new-secret" if prompt == "Strava Client Secret" else ""
        ),
    )

    exit_code = strava_main.main(["authorize", "start"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Strava app credentials not found at vault/strava/app.json." in captured.out
    assert "Saved Strava app credentials to vault/strava/app.json." in captured.out
    assert service.saved_credentials == [
        StravaAppCredentials(
            client_id=67890,
            client_secret="new-secret",
            redirect_uri="http://127.0.0.1:8765/exchange_token",
        )
    ]
    assert service.prepare_calls == [
        {
            "scopes": ("activity:read_all", "profile:read_all"),
            "approval_prompt": "auto",
            "state": None,
        }
    ]


def test_authorize_start_reprompts_until_redirect_uri_is_a_full_url(
    monkeypatch, capsys
):
    service = _FakeStravaService()
    service.storage.credentials = None
    responses = iter(
        [
            "new-secret",
            "127.0.0.1",
            "http://127.0.0.1:8765/exchange_token",
        ]
    )
    monkeypatch.setattr(strava_main, "_build_service", lambda args: service)
    monkeypatch.setattr(strava_main.IntPrompt, "ask", lambda prompt: 67890)
    monkeypatch.setattr(
        strava_main.Prompt,
        "ask",
        lambda prompt, default=None, password=False: next(responses),
    )

    exit_code = strava_main.main(["authorize", "start"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Redirect URI must be a full http:// or https:// URL" in captured.out
    assert service.saved_credentials == [
        StravaAppCredentials(
            client_id=67890,
            client_secret="new-secret",
            redirect_uri="http://127.0.0.1:8765/exchange_token",
        )
    ]


def test_resolve_storage_root_prefers_cli_arg_over_env(monkeypatch):
    monkeypatch.setenv("STRAVA_MCP_ROOT", "/tmp/from-env")

    resolved = strava_main._resolve_storage_root(Path("/tmp/from-cli"))

    assert resolved == Path("/tmp/from-cli")


def test_resolve_storage_root_uses_env_when_cli_arg_absent(monkeypatch):
    monkeypatch.setenv("STRAVA_MCP_ROOT", "/tmp/from-env")

    resolved = strava_main._resolve_storage_root(None)

    assert resolved == Path("/tmp/from-env")

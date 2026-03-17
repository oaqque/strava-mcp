"""Shared local Strava auth storage with locking and atomic writes."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeVar

from strava_mcp.strava.contracts import StravaAppCredentials, StravaSessionState
from strava_mcp.strava.errors import (
    StravaAuthError,
    StravaConfigurationError,
)


DEFAULT_STRAVA_ROOT = Path("vault/strava")
_APP_FILE_NAME = "app.json"
_SESSION_FILE_NAME = "session.json"
_LOCK_FILE_NAME = ".session.lock"

T = TypeVar("T")


def _write_json_file_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _load_json_object(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise StravaConfigurationError(f"Invalid JSON at {path}") from exc
    if not isinstance(payload, dict):
        raise StravaConfigurationError(f"Expected JSON object at {path}")
    return payload


@contextlib.contextmanager
def _exclusive_file_lock(
    path: Path, *, timeout_seconds: float = 15.0
) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    with path.open("a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise StravaAuthError(
                        f"Timed out waiting for Strava session lock: {path}"
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _app_credentials_from_env() -> StravaAppCredentials | None:
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    redirect_uri = os.getenv("STRAVA_REDIRECT_URI")
    if not client_id and not client_secret and not redirect_uri:
        return None
    if not client_id or not client_secret or not redirect_uri:
        raise StravaConfigurationError(
            "STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, and STRAVA_REDIRECT_URI "
            "must all be set together"
        )
    try:
        numeric_client_id = int(client_id)
    except ValueError as exc:
        raise StravaConfigurationError("STRAVA_CLIENT_ID must be an integer") from exc
    return StravaAppCredentials(
        client_id=numeric_client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


class StravaAuthStorage:
    """Filesystem-backed Strava auth storage under ``vault/strava``."""

    def __init__(self, root: Path = DEFAULT_STRAVA_ROOT) -> None:
        self.root = root

    @property
    def app_path(self) -> Path:
        return self.root / _APP_FILE_NAME

    @property
    def session_path(self) -> Path:
        return self.root / _SESSION_FILE_NAME

    @property
    def session_lock_path(self) -> Path:
        return self.root / _LOCK_FILE_NAME

    def load_app_credentials(
        self, *, required: bool = True
    ) -> StravaAppCredentials | None:
        payload = _load_json_object(self.app_path)
        if payload is not None:
            return StravaAppCredentials.model_validate(payload)
        env_credentials = _app_credentials_from_env()
        if env_credentials is not None:
            return env_credentials
        if required:
            raise StravaConfigurationError(
                "Strava app credentials not found. Expected vault/strava/app.json "
                "or STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET/STRAVA_REDIRECT_URI."
            )
        return None

    def save_app_credentials(self, credentials: StravaAppCredentials) -> None:
        _write_json_file_atomic(self.app_path, credentials.model_dump(mode="json"))

    def load_session(self, *, required: bool = True) -> StravaSessionState | None:
        payload = _load_json_object(self.session_path)
        if payload is None:
            if required:
                raise StravaAuthError(
                    "Strava session not found. Authenticate before calling the API."
                )
            return None
        return StravaSessionState.model_validate(payload)

    def save_session(self, session: StravaSessionState) -> None:
        _write_json_file_atomic(self.session_path, session.model_dump(mode="json"))

    def clear_session(self) -> None:
        self.session_path.unlink(missing_ok=True)

    def update_session(
        self,
        mutator: Callable[[StravaSessionState | None], T],
        *,
        timeout_seconds: float = 15.0,
    ) -> T:
        with _exclusive_file_lock(
            self.session_lock_path, timeout_seconds=timeout_seconds
        ):
            current = self.load_session(required=False)
            return mutator(current)

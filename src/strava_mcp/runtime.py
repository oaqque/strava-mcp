"""Shared runtime helpers for Strava CLI entrypoints."""

from __future__ import annotations

import os
from pathlib import Path

from strava_mcp.strava import DEFAULT_STRAVA_ROOT, StravaAuthStorage, StravaService


def resolve_storage_root(cli_root: Path | None) -> Path:
    if cli_root is not None:
        return cli_root.expanduser()
    env_root = os.getenv("STRAVA_MCP_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    return DEFAULT_STRAVA_ROOT


def build_service(cli_root: Path | None) -> StravaService:
    return StravaService(storage=StravaAuthStorage(resolve_storage_root(cli_root)))

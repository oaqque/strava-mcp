"""Unit tests for the direct Strava API CLI."""

from __future__ import annotations

from datetime import UTC, datetime

from strava_mcp.cli import main as strava_cli
from strava_mcp.strava import (
    StravaActivitySummary,
    StravaAthlete,
)


class _FakeDirectService:
    def __init__(self) -> None:
        now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
        self.activities_calls: list[dict[str, object]] = []

        self.athlete = StravaAthlete(
            id=42,
            firstname="William",
            lastname="Ye",
            city="Sydney",
            country="Australia",
            summit=True,
            created_at=now,
            updated_at=now,
        )
        self.activities = [
            StravaActivitySummary(
                id=101,
                name="Morning Run",
                sport_type="Run",
                distance=5030.0,
                moving_time=1500,
                total_elevation_gain=42.0,
                start_date_local=now,
                start_date=now,
            )
        ]

    def get_athlete(self) -> StravaAthlete:
        return self.athlete

    def list_activities(
        self,
        *,
        before=None,
        after=None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[StravaActivitySummary]:
        self.activities_calls.append(
            {
                "before": before,
                "after": after,
                "page": page,
                "per_page": per_page,
            }
        )
        return self.activities


def test_profile_outputs_human_readable_summary(monkeypatch, capsys):
    service = _FakeDirectService()
    monkeypatch.setattr(strava_cli, "build_service", lambda root: service)

    exit_code = strava_cli.main(["profile"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Authenticated athlete" in captured.out
    assert "William Ye" in captured.out


def test_list_outputs_activity_table(monkeypatch, capsys):
    service = _FakeDirectService()
    monkeypatch.setattr(strava_cli, "build_service", lambda root: service)

    exit_code = strava_cli.main(["list", "--per-page", "5"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Morning Run" in captured.out
    assert service.activities_calls == [
        {
            "before": None,
            "after": None,
            "page": 1,
            "per_page": 5,
        }
    ]

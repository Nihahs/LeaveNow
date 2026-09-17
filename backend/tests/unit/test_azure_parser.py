import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.providers import TrafficProviderError, parse_azure_route_response


def test_parses_route_path_fixture() -> None:
    fixture = Path("tests/fixtures/azure_route_response.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    depart_at = datetime(2026, 9, 16, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

    result = parse_azure_route_response(payload, depart_at)

    assert result.duration_seconds == 1740
    assert result.distance_meters == 7050
    assert result.congestion == "Heavy"
    assert len(result.legs) == 5
    assert result.legs[3].duration_seconds == 510


def test_falls_back_to_duration_without_traffic_field() -> None:
    payload = {
        "features": [
            {
                "geometry": {"type": "LineString"},
                "properties": {
                    "durationInSeconds": 300,
                    "legs": [{"distanceInMeters": 1000, "durationInSeconds": 300}],
                },
            }
        ]
    }

    result = parse_azure_route_response(payload, datetime.now(ZoneInfo("Asia/Kolkata")))

    assert result.duration_seconds == 300
    assert result.distance_meters == 1000
    assert result.congestion == "Unknown"


def test_rejects_missing_legs() -> None:
    with pytest.raises(TrafficProviderError, match="leg timing"):
        parse_azure_route_response(
            {
                "features": [
                    {
                        "geometry": {"type": "LineString"},
                        "properties": {"durationInSeconds": 300},
                    }
                ]
            },
            datetime.now(ZoneInfo("Asia/Kolkata")),
        )

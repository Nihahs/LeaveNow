from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain import RouteDefinition, Waypoint
from app.providers import MockTrafficProvider


@pytest.mark.asyncio
async def test_mock_provider_generates_one_leg_per_waypoint_pair() -> None:
    route = RouteDefinition(
        id=1,
        name="Variable route",
        timezone="Asia/Kolkata",
        fingerprint="test",
        waypoints=(
            Waypoint(0, "home", "Home", 78.35, 17.43),
            Waypoint(1, "signal", "Signal 1", 78.36, 17.44, 1.0),
            Waypoint(2, "signal", "Signal 2", 78.37, 17.45, 2.0, True),
            Waypoint(3, "office", "Office", 78.38, 17.46),
        ),
    )
    provider = MockTrafficProvider()

    prediction = await provider.get_route_prediction(
        route,
        datetime(2026, 9, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    baseline = await provider.get_free_flow_baseline(route, date(2026, 9, 18))

    assert len(prediction.legs) == 3
    assert len(baseline.legs) == 3
    assert prediction.duration_seconds > baseline.duration_seconds

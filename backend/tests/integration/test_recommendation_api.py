from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import SessionLocal, initialize_database
from app.main import app
from app.repository import seed_route


@pytest.mark.asyncio
async def test_recommendation_works_in_mock_mode() -> None:
    await initialize_database()
    async with SessionLocal() as session:
        await seed_route(session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/recommendation",
            params={
                "date": date(2026, 9, 16).isoformat(),
                "windowStart": "07:00",
                "windowEnd": "11:00",
                "intervalMinutes": 5,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bestWindow"]["start"]
    assert payload["recommendedDeparture"]
    assert len(payload["series"]) == 49
    assert len(payload["series"][0]["signalDelays"]) == 4
    assert payload["stale"] is False
    assert payload["calibration"]["sampleCount"] >= 0
    assert payload["goodWindows"]
    assert payload["practicalToleranceMin"] == 1
    assert isinstance(payload["trafficIsFlat"], bool)


@pytest.mark.asyncio
async def test_route_can_be_saved_without_changing_waypoint_order() -> None:
    await initialize_database()
    async with SessionLocal() as session:
        await seed_route(session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        current = (await client.get("/api/route")).json()
        payload = {
            key: value
            for key, value in current.items()
            if key not in {"id", "timezone"}
        }
        payload["name"] = "Updated test route"
        response = await client.put("/api/route", json=payload)

    assert response.status_code == 200
    assert response.json()["name"] == "Updated test route"
    assert len(response.json()["waypoints"]) == 6


@pytest.mark.asyncio
async def test_commute_log_is_listed_with_utc_timestamps() -> None:
    await initialize_database()
    payload = {
        "departedAt": "2026-09-17T10:45:00+05:30",
        "arrivedAt": "2026-09-17T11:20:00+05:30",
        "signalWaitsSeconds": [34, 186, 0, 949],
        "note": "Test commute",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post("/api/commute-log", json=payload)
        listed = await client.get("/api/commute-log")

    assert created.status_code == 201
    assert created.json()["departedAt"].endswith("Z")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created.json()["id"]
    assert listed.json()[0]["signalWaitsSeconds"] == [34, 186, 0, 949]


@pytest.mark.asyncio
async def test_route_supports_a_configurable_number_of_signals() -> None:
    await initialize_database()
    async with SessionLocal() as session:
        await seed_route(session)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        current = (await client.get("/api/route")).json()
        home = current["waypoints"][0]
        first_signal = current["waypoints"][1]
        second_signal = current["waypoints"][2]
        office = current["waypoints"][-1]
        waypoints = [home, first_signal, second_signal, office]
        for point_index, waypoint in enumerate(waypoints):
            waypoint["pointIndex"] = point_index
        payload = {
            "name": "Two-signal commute",
            "defaultWindowStart": "08:00",
            "defaultWindowEnd": "09:00",
            "defaultIntervalMinutes": 5,
            "waypoints": waypoints,
        }

        saved = await client.put("/api/route", json=payload)
        recommendation = await client.get(
            "/api/recommendation",
            params={
                "date": date(2027, 9, 18).isoformat(),
                "windowStart": "08:00",
                "windowEnd": "09:00",
                "intervalMinutes": 5,
            },
        )

    assert saved.status_code == 200
    assert len(saved.json()["waypoints"]) == 4
    assert recommendation.status_code == 200
    assert len(recommendation.json()["series"][0]["signalDelays"]) == 2

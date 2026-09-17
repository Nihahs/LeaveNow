import asyncio
import math
from datetime import UTC, date, datetime, time
from time import monotonic
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings
from app.domain import LegPrediction, RouteDefinition, RoutePrediction


class TrafficProviderError(RuntimeError):
    pass


class TrafficProvider(Protocol):
    name: str

    async def get_route_prediction(
        self, route: RouteDefinition, depart_at: datetime
    ) -> RoutePrediction: ...

    async def get_free_flow_baseline(
        self, route: RouteDefinition, service_date: date
    ) -> RoutePrediction: ...


class MockTrafficProvider:
    name = "mock"

    async def get_route_prediction(
        self, route: RouteDefinition, depart_at: datetime
    ) -> RoutePrediction:
        local = depart_at.astimezone(ZoneInfo(route.timezone))
        minute = local.hour * 60 + local.minute
        weekday_factor = 1.0 if local.weekday() < 5 else 0.35
        morning_peak = math.exp(-((minute - 555) / 52) ** 2)
        early_bump = 0.35 * math.exp(-((minute - 485) / 35) ** 2)
        ripple = 0.08 * (1 + math.sin(minute / 13))
        traffic = weekday_factor * (morning_peak + early_bump) + ripple
        free_flow_legs = _mock_free_flow_legs(route)
        legs = tuple(
            LegPrediction(
                distance_meters=leg.distance_meters,
                duration_seconds=leg.duration_seconds
                * (
                    1
                    + traffic
                    * (
                        1.18
                        if route.waypoints[index + 1].is_wipro
                        else 0.32 + (0.14 * (index % 3))
                    )
                ),
            )
            for index, leg in enumerate(free_flow_legs)
        )
        duration = sum(leg.duration_seconds for leg in legs)
        congestion = (
            "Heavy" if traffic > 0.85 else "Moderate" if traffic > 0.4 else "Light"
        )
        return RoutePrediction(
            depart_at=depart_at,
            duration_seconds=duration,
            distance_meters=sum(leg.distance_meters for leg in legs),
            legs=legs,
            congestion=congestion,
        )

    async def get_free_flow_baseline(
        self, route: RouteDefinition, service_date: date
    ) -> RoutePrediction:
        timezone = ZoneInfo(route.timezone)
        depart_at = datetime.combine(service_date, time(3, 0), timezone)
        legs = _mock_free_flow_legs(route)
        return RoutePrediction(
            depart_at=depart_at,
            duration_seconds=sum(leg.duration_seconds for leg in legs),
            distance_meters=sum(leg.distance_meters for leg in legs),
            legs=legs,
            congestion="Free flow",
        )


def _mock_free_flow_legs(route: RouteDefinition) -> tuple[LegPrediction, ...]:
    legs: list[LegPrediction] = []
    for start, end in zip(
        route.waypoints[:-1], route.waypoints[1:], strict=True
    ):
        distance = max(
            250.0,
            _haversine_meters(
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
            ),
        )
        duration = max(75.0, distance / (32_000 / 3_600))
        legs.append(
            LegPrediction(distance_meters=distance, duration_seconds=duration)
        )
    return tuple(legs)


def _haversine_meters(
    latitude_one: float,
    longitude_one: float,
    latitude_two: float,
    longitude_two: float,
) -> float:
    earth_radius = 6_371_000
    latitude_delta = math.radians(latitude_two - latitude_one)
    longitude_delta = math.radians(longitude_two - longitude_one)
    first_latitude = math.radians(latitude_one)
    second_latitude = math.radians(latitude_two)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return earth_radius * 2 * math.atan2(
        math.sqrt(haversine), math.sqrt(1 - haversine)
    )


class AzureMapsTrafficProvider:
    name = "azure"
    endpoint = "https://atlas.microsoft.com/route/directions"

    def __init__(self, settings: Settings) -> None:
        if not settings.azure_maps_key:
            raise ValueError("AZURE_MAPS_KEY is required when MOCK_AZURE is false")
        self._key = settings.azure_maps_key
        self._semaphore = asyncio.Semaphore(settings.max_azure_concurrency)
        self._rate_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))

    async def get_route_prediction(
        self, route: RouteDefinition, depart_at: datetime
    ) -> RoutePrediction:
        body = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [point.longitude, point.latitude],
                    },
                    "properties": {
                        "pointIndex": point.point_index,
                        "pointType": "waypoint",
                    },
                }
                for point in route.waypoints
            ],
            "travelMode": "driving",
            "departAt": depart_at.isoformat(),
            "optimizeRoute": "fastestWithTraffic",
            "routeOutputOptions": ["routePath", "itinerary"],
        }
        async with self._semaphore:
            await self._wait_for_rate_slot()
            response = await self._request_with_retry(body)
        return parse_azure_route_response(response, depart_at)

    async def get_free_flow_baseline(
        self, route: RouteDefinition, service_date: date
    ) -> RoutePrediction:
        depart_at = datetime.combine(service_date, time(3, 0), ZoneInfo(route.timezone))
        return await self.get_route_prediction(route, depart_at)

    async def _wait_for_rate_slot(self) -> None:
        async with self._rate_lock:
            delay = self._next_request_at - monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = monotonic() + 0.12

    async def _request_with_retry(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = await self._client.post(
                    self.endpoint,
                    params={"api-version": "2025-01-01"},
                    headers={
                        "subscription-key": self._key,
                        "Content-Type": "application/geo+json",
                    },
                    json=body,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise TrafficProviderError("Azure Maps returned an invalid JSON object")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                if attempt == 2:
                    raise TrafficProviderError("Azure Maps route request failed") from exc
                await asyncio.sleep(0.5 * (2**attempt))
        raise TrafficProviderError("Azure Maps route request failed")


def parse_azure_route_response(
    payload: dict[str, Any], requested_depart_at: datetime
) -> RoutePrediction:
    features = payload.get("features")
    if not isinstance(features, list):
        raise TrafficProviderError("Azure response does not contain features")
    route_feature = next(
        (
            feature
            for feature in features
            if isinstance(feature, dict)
            and isinstance(feature.get("properties"), dict)
            and (
                feature.get("geometry", {}).get("type") in {"LineString", "MultiLineString"}
                or "legs" in feature["properties"]
            )
        ),
        None,
    )
    if route_feature is None:
        raise TrafficProviderError("Azure response does not contain a RoutePath feature")
    properties = route_feature["properties"]
    raw_legs = properties.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise TrafficProviderError("Azure route does not contain leg timing")

    legs = tuple(_parse_azure_leg(leg) for leg in raw_legs)
    duration = _optional_number(properties, "durationTrafficInSeconds")
    if duration is None:
        duration = _required_number(properties, "durationInSeconds")
    distance = _optional_number(properties, "distanceInMeters")
    if distance is None:
        distance = sum(leg.distance_meters for leg in legs)
    congestion = properties.get("trafficCongestion", "Unknown")
    return RoutePrediction(
        depart_at=requested_depart_at,
        duration_seconds=duration,
        distance_meters=distance,
        legs=legs,
        congestion=str(congestion),
    )


def _parse_azure_leg(payload: Any) -> LegPrediction:
    if not isinstance(payload, dict):
        raise TrafficProviderError("Azure route leg is not an object")
    departure_at = _parse_optional_datetime(payload.get("departureAt"))
    arrival_at = _parse_optional_datetime(payload.get("arrivalAt"))
    return LegPrediction(
        distance_meters=_required_number(payload, "distanceInMeters"),
        duration_seconds=_required_number(payload, "durationInSeconds"),
        departure_at=departure_at,
        arrival_at=arrival_at,
    )


def _required_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise TrafficProviderError(f"Azure response is missing numeric {key}")


def _optional_number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)

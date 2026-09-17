import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import RouteRecord, WaypointRecord
from app.domain import RouteDefinition, Waypoint
from app.schemas import RouteSchema, RouteUpdateSchema, WaypointSchema

PLACEHOLDER_WAYPOINTS = [
    ("home", "TODO Home", 78.3521, 17.4368, None, False),
    ("signal", "Signal 1", 78.3557, 17.4384, 1.0, False),
    ("signal", "Signal 2", 78.3594, 17.4402, 1.0, False),
    ("signal", "Signal 3", 78.3635, 17.4415, 1.0, False),
    ("signal", "Wipro Circle (TODO)", 78.3678, 17.4430, 2.0, True),
    ("office", "TODO Office", 78.3722, 17.4451, None, False),
]


def route_fingerprint(name: str, waypoints: list[WaypointSchema]) -> str:
    normalized = {
        "name": name,
        "waypoints": [point.model_dump() for point in waypoints],
    }
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def seed_route(session: AsyncSession) -> None:
    existing = await session.scalar(select(RouteRecord.id).limit(1))
    if existing is not None:
        return
    waypoint_schemas = [
        WaypointSchema(
            pointIndex=index,
            pointType=point_type,
            name=name,
            longitude=longitude,
            latitude=latitude,
            signalWeight=weight,
            isWipro=is_wipro,
        )
        for index, (point_type, name, longitude, latitude, weight, is_wipro) in enumerate(
            PLACEHOLDER_WAYPOINTS
        )
    ]
    route = RouteRecord(
        name="Hyderabad Office Commute (TODO coordinates)",
        timezone="Asia/Kolkata",
        fingerprint=route_fingerprint(
            "Hyderabad Office Commute (TODO coordinates)", waypoint_schemas
        ),
        updated_at=datetime.now(UTC),
    )
    route.waypoints = [
        WaypointRecord(
            point_index=point.pointIndex,
            point_type=point.pointType,
            name=point.name,
            longitude=point.longitude,
            latitude=point.latitude,
            signal_weight=point.signalWeight,
            is_wipro=point.isWipro,
        )
        for point in waypoint_schemas
    ]
    session.add(route)
    await session.commit()


async def get_route_record(session: AsyncSession) -> RouteRecord:
    route = await session.scalar(select(RouteRecord).limit(1))
    if route is None:
        await seed_route(session)
        route = await session.scalar(select(RouteRecord).limit(1))
    if route is None:
        raise RuntimeError("Route seed failed")
    return route


def to_route_schema(route: RouteRecord) -> RouteSchema:
    return RouteSchema(
        id=route.id,
        name=route.name,
        timezone=route.timezone,
        defaultWindowStart=route.default_window_start,
        defaultWindowEnd=route.default_window_end,
        defaultIntervalMinutes=route.default_interval_minutes,
        waypoints=[
            WaypointSchema(
                pointIndex=point.point_index,
                pointType=point.point_type,
                name=point.name,
                longitude=point.longitude,
                latitude=point.latitude,
                signalWeight=point.signal_weight,
                isWipro=point.is_wipro,
            )
            for point in route.waypoints
        ],
    )


def to_route_definition(route: RouteRecord) -> RouteDefinition:
    return RouteDefinition(
        id=route.id,
        name=route.name,
        timezone=route.timezone,
        fingerprint=route.fingerprint,
        waypoints=tuple(
            Waypoint(
                point_index=point.point_index,
                point_type=point.point_type,
                name=point.name,
                longitude=point.longitude,
                latitude=point.latitude,
                signal_weight=point.signal_weight,
                is_wipro=point.is_wipro,
            )
            for point in route.waypoints
        ),
    )


async def update_route_record(
    session: AsyncSession, route: RouteRecord, payload: RouteUpdateSchema
) -> RouteRecord:
    route.name = payload.name
    route.default_window_start = payload.defaultWindowStart
    route.default_window_end = payload.defaultWindowEnd
    route.default_interval_minutes = payload.defaultIntervalMinutes
    route.fingerprint = route_fingerprint(payload.name, payload.waypoints)
    route.updated_at = datetime.now(UTC)
    existing_waypoints = list(route.waypoints)
    shared_count = min(len(existing_waypoints), len(payload.waypoints))
    for record, point in zip(
        existing_waypoints[:shared_count],
        payload.waypoints[:shared_count],
        strict=True,
    ):
        record.point_index = point.pointIndex
        record.point_type = point.pointType
        record.name = point.name
        record.longitude = point.longitude
        record.latitude = point.latitude
        record.signal_weight = point.signalWeight
        record.is_wipro = point.isWipro
    for point in payload.waypoints[shared_count:]:
        route.waypoints.append(
            WaypointRecord(
                point_index=point.pointIndex,
                point_type=point.pointType,
                name=point.name,
                longitude=point.longitude,
                latitude=point.latitude,
                signal_weight=point.signalWeight,
                is_wipro=point.isWipro,
            )
        )
    for record in existing_waypoints[shared_count:]:
        route.waypoints.remove(record)
        await session.delete(record)
    await session.commit()
    await session.refresh(route)
    return route

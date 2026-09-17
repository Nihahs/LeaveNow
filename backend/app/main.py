import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import (
    CommuteLogRecord,
    RecommendationSnapshotRecord,
    SessionLocal,
    get_session,
    initialize_database,
)
from app.domain import RouteDefinition
from app.providers import AzureMapsTrafficProvider, MockTrafficProvider, TrafficProviderError
from app.recommendation import RecommendationService
from app.repository import (
    get_route_record,
    seed_route,
    to_route_definition,
    to_route_schema,
    update_route_record,
)
from app.schemas import (
    CommuteLogCreateSchema,
    CommuteLogSchema,
    RecommendationSchema,
    RouteSchema,
    RouteUpdateSchema,
)

settings = get_settings()
provider = (
    MockTrafficProvider() if settings.mock_azure else AzureMapsTrafficProvider(settings)
)
recommendation_service = RecommendationService(provider, settings)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    async with SessionLocal() as session:
        await seed_route(session)
    yield


app = FastAPI(title="LeaveNow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    await session.scalar(select(1))
    return {"status": "ok", "provider": provider.name}


@app.get("/api/route", response_model=RouteSchema)
async def get_route(session: Annotated[AsyncSession, Depends(get_session)]) -> RouteSchema:
    return to_route_schema(await get_route_record(session))


@app.put("/api/route", response_model=RouteSchema)
async def put_route(
    payload: RouteUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RouteSchema:
    route = await update_route_record(session, await get_route_record(session), payload)
    return to_route_schema(route)


@app.get("/api/recommendation", response_model=RecommendationSchema)
async def get_recommendation(
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    service_date: Annotated[date, Query(alias="date")],
    window_start: Annotated[str, Query(alias="windowStart")] = "07:00",
    window_end: Annotated[str, Query(alias="windowEnd")] = "11:00",
    interval_minutes: Annotated[int, Query(alias="intervalMinutes", ge=5, le=10)] = 5,
) -> RecommendationSchema:
    route = to_route_definition(await get_route_record(session))
    request_key = recommendation_service.request_key(
        route, service_date, window_start, window_end, interval_minutes
    )
    snapshot = await recommendation_service.get_snapshot(session, request_key)
    if snapshot is not None:
        if snapshot.stale:
            background_tasks.add_task(
                _refresh_recommendation,
                route,
                service_date,
                window_start,
                window_end,
                interval_minutes,
            )
        return snapshot
    try:
        return await recommendation_service.build(
            session, route, service_date, window_start, window_end, interval_minutes
        )
    except (ValueError, TrafficProviderError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _refresh_recommendation(
    route: RouteDefinition,
    service_date: date,
    window_start: str,
    window_end: str,
    interval_minutes: int,
) -> None:
    async with SessionLocal() as session:
        try:
            await recommendation_service.build(
                session, route, service_date, window_start, window_end, interval_minutes
            )
        except (ValueError, TrafficProviderError):
            return


@app.post("/api/commute-log", response_model=CommuteLogSchema, status_code=201)
async def create_commute_log(
    payload: CommuteLogCreateSchema,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommuteLogSchema:
    route = await get_route_record(session)
    signal_count = max(0, len(route.waypoints) - 2)
    if len(payload.signalWaitsSeconds) > signal_count:
        raise HTTPException(
            status_code=422,
            detail=f"This route has {signal_count} signal stops",
        )
    record = CommuteLogRecord(
        departed_at=payload.departedAt,
        arrived_at=payload.arrivedAt,
        signal_waits_json=json.dumps(payload.signalWaitsSeconds),
        note=payload.note,
        created_at=datetime.now(UTC),
    )
    session.add(record)
    await session.execute(delete(RecommendationSnapshotRecord))
    await session.commit()
    await session.refresh(record)
    return _commute_log_schema(record)


@app.get("/api/commute-log", response_model=list[CommuteLogSchema])
async def list_commute_logs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CommuteLogSchema]:
    records = (
        await session.scalars(
            select(CommuteLogRecord)
            .order_by(CommuteLogRecord.departed_at.desc())
            .limit(limit)
        )
    ).all()
    return [_commute_log_schema(record) for record in records]


def _commute_log_schema(record: CommuteLogRecord) -> CommuteLogSchema:
    return CommuteLogSchema(
        id=record.id,
        departedAt=_sqlite_utc(record.departed_at),
        arrivedAt=_sqlite_utc(record.arrived_at),
        signalWaitsSeconds=record.signal_waits,
        note=record.note,
        createdAt=_sqlite_utc(record.created_at),
    )


def _sqlite_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

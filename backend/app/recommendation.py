import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calibration import CalibrationSample, calibrate_score
from app.config import Settings
from app.db import (
    CommuteLogRecord,
    RecommendationSnapshotRecord,
    RouteBaselineRecord,
    SessionLocal,
    TrafficCacheRecord,
)
from app.domain import RouteDefinition, RoutePrediction
from app.providers import TrafficProvider, TrafficProviderError
from app.schemas import (
    BestWindowSchema,
    CalibrationSchema,
    RecommendationPointSchema,
    RecommendationSchema,
    SignalDelaySchema,
)
from app.scoring import score_prediction
from app.serialization import prediction_from_json, prediction_to_json


class RecommendationService:
    def __init__(self, provider: TrafficProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_azure_concurrency)
        self._cache_locks: dict[str, asyncio.Lock] = {}
        self._database_lock = asyncio.Lock()
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def request_key(
        self,
        route: RouteDefinition,
        service_date: date,
        window_start: str,
        window_end: str,
        interval_minutes: int,
    ) -> str:
        raw = (
            f"{route.fingerprint}|{service_date.isoformat()}|{window_start}|"
            f"{window_end}|{interval_minutes}|{self.provider.name}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get_snapshot(
        self, session: AsyncSession, request_key: str
    ) -> RecommendationSchema | None:
        record = await session.scalar(
            select(RecommendationSnapshotRecord).where(
                RecommendationSnapshotRecord.request_key == request_key
            )
        )
        if record is None:
            return None
        generated_at = _as_utc(record.generated_at)
        if datetime.now(UTC) - generated_at > timedelta(hours=self.settings.stale_max_hours):
            return None
        payload = json.loads(record.response_json)
        if "calibration" not in payload:
            return None
        payload["stale"] = bool(payload.get("stale")) or (
            datetime.now(UTC) - generated_at
            > timedelta(hours=self.settings.cache_ttl_hours)
        )
        result = RecommendationSchema.model_validate(payload)
        now = datetime.now(UTC)
        if (
            result.recommendedDeparture.astimezone(UTC) < now
            and result.series[-1].departAt.astimezone(UTC) >= now
        ):
            return None
        return result

    async def build(
        self,
        session: AsyncSession,
        route: RouteDefinition,
        service_date: date,
        window_start: str,
        window_end: str,
        interval_minutes: int,
    ) -> RecommendationSchema:
        self._ensure_async_primitives()
        candidates = _candidate_departures(
            service_date, window_start, window_end, interval_minutes, route.timezone
        )
        baseline = await self._get_baseline(session, route, service_date)
        predictions = await asyncio.gather(
            *(self._get_prediction(route, candidate) for candidate in candidates)
        )
        signal_waypoints = route.waypoints[1:-1]
        weights = tuple(float(point.signal_weight or 0.0) for point in signal_waypoints)
        calibration_samples = await self._get_calibration_samples(
            session, route, baseline, weights
        )
        series: list[RecommendationPointSchema] = []
        for candidate, (prediction, _stale_prediction) in zip(
            candidates, predictions, strict=True
        ):
            raw_score = score_prediction(prediction, baseline, weights)
            score = calibrate_score(
                raw_score, candidate, calibration_samples, weights
            )
            series.append(
                RecommendationPointSchema(
                    departAt=candidate,
                    totalMinutes=round(
                        (
                            baseline.duration_seconds
                            + score.total_delay_seconds
                        )
                        / 60,
                        1,
                    ),
                    delayMinutes=round(score.total_delay_seconds / 60, 1),
                    score=round(score.score, 1),
                    congestion=prediction.congestion,
                    signalDelays=[
                        SignalDelaySchema(
                            signalId=point.point_index,
                            name=point.name,
                            delayMinutes=round(
                                score.signal_delay_seconds[index] / 60, 1
                            ),
                            weight=weights[index],
                            isWipro=point.is_wipro,
                        )
                        for index, point in enumerate(signal_waypoints)
                    ],
                )
            )
        eligible_series = _eligible_series(series, service_date, route.timezone)
        if not eligible_series:
            raise ValueError("No future departure times remain in today's window")
        best_start, best_end, window_points = _best_window(eligible_series)
        recommended = min(window_points, key=lambda point: (point.score, point.departAt))
        generated_at = datetime.now(UTC)
        result = RecommendationSchema(
            bestWindow=BestWindowSchema(
                start=best_start,
                end=best_end,
                expectedDelayMin=round(
                    sum(point.delayMinutes for point in window_points) / len(window_points), 1
                ),
                meanScore=round(
                    sum(point.score for point in window_points) / len(window_points), 1
                ),
            ),
            recommendedDeparture=recommended.departAt,
            series=series,
            updatedAt=generated_at,
            stale=any(stale for _, stale in predictions),
            calibration=CalibrationSchema(
                applied=bool(calibration_samples),
                sampleCount=len(calibration_samples),
                confidence=round(
                    min(1.0, len(calibration_samples) / 5), 2
                ),
            ),
        )
        await self._save_snapshot(
            session,
            self.request_key(route, service_date, window_start, window_end, interval_minutes),
            result,
        )
        return result

    def _ensure_async_primitives(self) -> None:
        event_loop = asyncio.get_running_loop()
        if self._event_loop is event_loop:
            return
        self._event_loop = event_loop
        self._semaphore = asyncio.Semaphore(self.settings.max_azure_concurrency)
        self._cache_locks = {}
        self._database_lock = asyncio.Lock()

    async def _get_calibration_samples(
        self,
        session: AsyncSession,
        route: RouteDefinition,
        baseline: RoutePrediction,
        signal_weights: tuple[float, ...],
    ) -> tuple[CalibrationSample, ...]:
        logs = (
            await session.scalars(
                select(CommuteLogRecord)
                .order_by(CommuteLogRecord.departed_at.desc())
                .limit(60)
            )
        ).all()
        samples: list[CalibrationSample] = []
        timezone = ZoneInfo(route.timezone)
        for log in logs:
            departed_at = _as_utc(log.departed_at).astimezone(timezone)
            arrived_at = _as_utc(log.arrived_at).astimezone(timezone)
            bucket = _bucket_departure(
                departed_at, self.settings.cache_bucket_minutes
            )
            cached = await session.scalar(
                select(TrafficCacheRecord).where(
                    TrafficCacheRecord.route_fingerprint == route.fingerprint,
                    TrafficCacheRecord.bucket_start == bucket.strftime("%H:%M"),
                    TrafficCacheRecord.day_of_week == departed_at.weekday(),
                    TrafficCacheRecord.provider == self.provider.name,
                )
            )
            if cached is None:
                continue
            prediction = prediction_from_json(cached.prediction_json, departed_at)
            predicted_score = score_prediction(prediction, baseline, signal_weights)
            actual_duration = (arrived_at - departed_at).total_seconds()
            actual_total_delay = max(
                0.0, actual_duration - baseline.duration_seconds
            )
            waits = log.signal_waits
            signal_residuals: list[float | None] = []
            for index in range(len(signal_weights)):
                wait = waits[index] if index < len(waits) else None
                signal_residuals.append(
                    float(wait) - predicted_score.leg_delay_seconds[index]
                    if wait is not None
                    else None
                )
            samples.append(
                CalibrationSample(
                    departed_at=departed_at,
                    total_delay_residual_seconds=(
                        actual_total_delay - predicted_score.total_delay_seconds
                    ),
                    signal_delay_residual_seconds=tuple(signal_residuals),
                )
            )
        return tuple(samples)

    async def _get_baseline(
        self, session: AsyncSession, route: RouteDefinition, service_date: date
    ) -> RoutePrediction:
        record = await session.scalar(
            select(RouteBaselineRecord).where(
                RouteBaselineRecord.route_fingerprint == route.fingerprint
            )
        )
        if record is not None:
            return prediction_from_json(record.prediction_json)
        prediction = await self.provider.get_free_flow_baseline(route, service_date)
        session.add(
            RouteBaselineRecord(
                route_fingerprint=route.fingerprint,
                provider=self.provider.name,
                prediction_json=prediction_to_json(prediction),
                fetched_at=datetime.now(UTC),
            )
        )
        await session.commit()
        return prediction

    async def _get_prediction(
        self, route: RouteDefinition, depart_at: datetime
    ) -> tuple[RoutePrediction, bool]:
        bucket = _bucket_departure(depart_at, self.settings.cache_bucket_minutes)
        cache_key = (
            f"{route.fingerprint}|{bucket.strftime('%H:%M')}|"
            f"{depart_at.weekday()}|{self.provider.name}"
        )
        lock = self._cache_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            async with self._database_lock, SessionLocal() as session:
                record = await session.scalar(
                    select(TrafficCacheRecord).where(
                        TrafficCacheRecord.route_fingerprint == route.fingerprint,
                        TrafficCacheRecord.bucket_start == bucket.strftime("%H:%M"),
                        TrafficCacheRecord.day_of_week == depart_at.weekday(),
                        TrafficCacheRecord.provider == self.provider.name,
                    )
                )
            now = datetime.now(UTC)
            if record is not None and _as_utc(record.expires_at) > now:
                return prediction_from_json(record.prediction_json, depart_at), False

            try:
                async with self._semaphore:
                    prediction = await self.provider.get_route_prediction(route, bucket)
            except TrafficProviderError:
                if record is not None and now - _as_utc(record.fetched_at) <= timedelta(
                    hours=self.settings.stale_max_hours
                ):
                    return prediction_from_json(record.prediction_json, depart_at), True
                raise

            async with self._database_lock, SessionLocal() as session:
                record = await session.scalar(
                    select(TrafficCacheRecord).where(
                        TrafficCacheRecord.route_fingerprint == route.fingerprint,
                        TrafficCacheRecord.bucket_start == bucket.strftime("%H:%M"),
                        TrafficCacheRecord.day_of_week == depart_at.weekday(),
                        TrafficCacheRecord.provider == self.provider.name,
                    )
                )
                if record is None:
                    record = TrafficCacheRecord(
                        route_fingerprint=route.fingerprint,
                        bucket_start=bucket.strftime("%H:%M"),
                        day_of_week=depart_at.weekday(),
                        provider=self.provider.name,
                        prediction_json=prediction_to_json(prediction),
                        fetched_at=now,
                        expires_at=now + timedelta(hours=self.settings.cache_ttl_hours),
                    )
                    session.add(record)
                else:
                    record.prediction_json = prediction_to_json(prediction)
                    record.fetched_at = now
                    record.expires_at = now + timedelta(hours=self.settings.cache_ttl_hours)
                await session.commit()
            return prediction_from_json(prediction_to_json(prediction), depart_at), False

    async def _save_snapshot(
        self, session: AsyncSession, request_key: str, result: RecommendationSchema
    ) -> None:
        record = await session.scalar(
            select(RecommendationSnapshotRecord).where(
                RecommendationSnapshotRecord.request_key == request_key
            )
        )
        payload = result.model_dump_json()
        if record is None:
            session.add(
                RecommendationSnapshotRecord(
                    request_key=request_key,
                    response_json=payload,
                    generated_at=result.updatedAt,
                )
            )
        else:
            record.response_json = payload
            record.generated_at = result.updatedAt
        await session.commit()


def _candidate_departures(
    service_date: date,
    window_start: str,
    window_end: str,
    interval_minutes: int,
    timezone: str,
) -> list[datetime]:
    try:
        start_time = time.fromisoformat(window_start)
        end_time = time.fromisoformat(window_end)
    except ValueError as exc:
        raise ValueError("windowStart and windowEnd must use HH:MM format") from exc
    start = datetime.combine(service_date, start_time, ZoneInfo(timezone))
    end = datetime.combine(service_date, end_time, ZoneInfo(timezone))
    if end <= start:
        raise ValueError("windowEnd must be after windowStart")
    if end - start > timedelta(hours=8):
        raise ValueError("Recommendation window cannot exceed 8 hours")
    candidates: list[datetime] = []
    current = start
    while current <= end:
        candidates.append(current)
        current += timedelta(minutes=interval_minutes)
    return candidates


def _best_window(
    series: list[RecommendationPointSchema],
) -> tuple[datetime, datetime, list[RecommendationPointSchema]]:
    if not series:
        raise ValueError("At least one recommendation point is required")
    choices: list[tuple[float, datetime, datetime, list[RecommendationPointSchema]]] = []
    last_departure = series[-1].departAt
    for point in series:
        window_end = point.departAt + timedelta(minutes=10)
        if window_end > last_departure:
            continue
        points = [
            candidate
            for candidate in series
            if point.departAt <= candidate.departAt <= window_end
        ]
        if points:
            choices.append(
                (
                    sum(candidate.score for candidate in points) / len(points),
                    point.departAt,
                    window_end,
                    points,
                )
            )
    if not choices:
        point = min(series, key=lambda item: (item.score, item.departAt))
        return point.departAt, point.departAt + timedelta(minutes=10), [point]
    _, start, end, points = min(choices, key=lambda item: (item[0], item[1]))
    return start, end, points


def _eligible_series(
    series: list[RecommendationPointSchema],
    service_date: date,
    timezone: str,
    *,
    now: datetime | None = None,
) -> list[RecommendationPointSchema]:
    current = now or datetime.now(ZoneInfo(timezone))
    if service_date != current.date():
        return series
    return [point for point in series if point.departAt >= current]


def _bucket_departure(value: datetime, bucket_minutes: int) -> datetime:
    minute = value.minute - (value.minute % bucket_minutes)
    return value.replace(minute=minute, second=0, microsecond=0)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

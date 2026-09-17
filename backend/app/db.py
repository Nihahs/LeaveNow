import json
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class RouteRecord(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    default_window_start: Mapped[str] = mapped_column(String(5), default="07:00")
    default_window_end: Mapped[str] = mapped_column(String(5), default="11:00")
    default_interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    waypoints: Mapped[list["WaypointRecord"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="WaypointRecord.point_index",
        lazy="selectin",
    )


class WaypointRecord(Base):
    __tablename__ = "waypoints"
    __table_args__ = (UniqueConstraint("route_id", "point_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    point_index: Mapped[int] = mapped_column(Integer)
    point_type: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    longitude: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    signal_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_wipro: Mapped[bool] = mapped_column(Boolean, default=False)
    route: Mapped[RouteRecord] = relationship(back_populates="waypoints")


class RouteBaselineRecord(Base):
    __tablename__ = "route_baselines"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    prediction_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrafficCacheRecord(Base):
    __tablename__ = "traffic_cache"
    __table_args__ = (
        UniqueConstraint("route_fingerprint", "bucket_start", "day_of_week", "provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    route_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    bucket_start: Mapped[str] = mapped_column(String(32), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    prediction_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RecommendationSnapshotRecord(Base):
    __tablename__ = "recommendation_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    response_json: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CommuteLogRecord(Base):
    __tablename__ = "commute_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    departed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_waits_json: Mapped[str] = mapped_column(Text, default="[]")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def signal_waits(self) -> list[int | None]:
        value = json.loads(self.signal_waits_json)
        return [item if isinstance(item, int) else None for item in value]


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    database_path = settings.database_url.rsplit("///", maxsplit=1)[-1]
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

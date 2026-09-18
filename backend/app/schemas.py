from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class WaypointSchema(BaseModel):
    pointIndex: int = Field(ge=0, le=11)
    pointType: Literal["home", "signal", "office"]
    name: str = Field(min_length=1, max_length=100)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    signalWeight: float | None = Field(default=None, ge=0, le=10)
    isWipro: bool = False


class RouteSchema(BaseModel):
    id: int
    name: str
    timezone: str
    defaultWindowStart: str
    defaultWindowEnd: str
    defaultIntervalMinutes: int
    waypoints: list[WaypointSchema]


class RouteUpdateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    defaultWindowStart: str
    defaultWindowEnd: str
    defaultIntervalMinutes: int = Field(ge=5, le=10)
    waypoints: list[WaypointSchema]

    @model_validator(mode="after")
    def validate_waypoints(self) -> "RouteUpdateSchema":
        try:
            start = time.fromisoformat(self.defaultWindowStart)
            end = time.fromisoformat(self.defaultWindowEnd)
        except ValueError as exc:
            raise ValueError("Default window times must use HH:MM format") from exc
        if end <= start:
            raise ValueError("Default window end must be after its start")
        if not 2 <= len(self.waypoints) <= 12:
            raise ValueError("The route must contain home, office, and up to ten signals")
        if [point.pointIndex for point in self.waypoints] != list(
            range(len(self.waypoints))
        ):
            raise ValueError("Waypoint pointIndex values must be contiguous and ordered")
        if (
            self.waypoints[0].pointType != "home"
            or self.waypoints[-1].pointType != "office"
            or any(point.pointType != "signal" for point in self.waypoints[1:-1])
        ):
            raise ValueError("Waypoint types must be home, optional signals, then office")
        if any(point.signalWeight is None for point in self.waypoints[1:-1]):
            raise ValueError("Each signal must have a weight")
        return self


class SignalDelaySchema(BaseModel):
    signalId: int
    name: str
    delayMinutes: float
    weight: float
    isWipro: bool


class RecommendationPointSchema(BaseModel):
    departAt: datetime
    totalMinutes: float
    delayMinutes: float
    score: float
    congestion: str
    signalDelays: list[SignalDelaySchema]


class BestWindowSchema(BaseModel):
    start: datetime
    end: datetime
    expectedDelayMin: float
    meanScore: float


class GoodWindowSchema(BaseModel):
    start: datetime
    end: datetime
    expectedTotalMinutes: float
    expectedDelayMin: float


class CalibrationSchema(BaseModel):
    applied: bool
    sampleCount: int
    confidence: float


class RecommendationSchema(BaseModel):
    bestWindow: BestWindowSchema
    goodWindows: list[GoodWindowSchema]
    practicalToleranceMin: float
    trafficIsFlat: bool
    recommendedDeparture: datetime
    series: list[RecommendationPointSchema]
    updatedAt: datetime
    stale: bool
    calibration: CalibrationSchema


class CommuteLogCreateSchema(BaseModel):
    departedAt: datetime
    arrivedAt: datetime
    signalWaitsSeconds: list[int | None] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_times(self) -> "CommuteLogCreateSchema":
        if self.arrivedAt <= self.departedAt:
            raise ValueError("arrivedAt must be after departedAt")
        if any(wait is not None and wait < 0 for wait in self.signalWaitsSeconds):
            raise ValueError("Signal waits must be nonnegative")
        return self


class CommuteLogSchema(CommuteLogCreateSchema):
    id: int
    createdAt: datetime


class RecommendationQuery(BaseModel):
    date: date
    windowStart: str = "07:00"
    windowEnd: str = "11:00"
    intervalMinutes: int = Field(default=5, ge=5, le=10)

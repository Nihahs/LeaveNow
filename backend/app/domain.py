from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Waypoint:
    point_index: int
    point_type: str
    name: str
    longitude: float
    latitude: float
    signal_weight: float | None = None
    is_wipro: bool = False


@dataclass(frozen=True)
class RouteDefinition:
    id: int
    name: str
    timezone: str
    fingerprint: str
    waypoints: tuple[Waypoint, ...]


@dataclass(frozen=True)
class LegPrediction:
    distance_meters: float
    duration_seconds: float
    departure_at: datetime | None = None
    arrival_at: datetime | None = None


@dataclass(frozen=True)
class RoutePrediction:
    depart_at: datetime
    duration_seconds: float
    distance_meters: float
    legs: tuple[LegPrediction, ...]
    congestion: str


@dataclass(frozen=True)
class ScoreResult:
    total_delay_seconds: float
    leg_delay_seconds: tuple[float, ...]
    weighted_signal_delay_seconds: float
    score: float

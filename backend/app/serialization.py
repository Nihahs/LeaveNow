import json
from datetime import datetime
from typing import Any

from app.domain import LegPrediction, RoutePrediction


def prediction_to_json(prediction: RoutePrediction) -> str:
    return json.dumps(
        {
            "departAt": prediction.depart_at.isoformat(),
            "durationSeconds": prediction.duration_seconds,
            "distanceMeters": prediction.distance_meters,
            "congestion": prediction.congestion,
            "legs": [
                {
                    "distanceMeters": leg.distance_meters,
                    "durationSeconds": leg.duration_seconds,
                    "departureAt": leg.departure_at.isoformat() if leg.departure_at else None,
                    "arrivalAt": leg.arrival_at.isoformat() if leg.arrival_at else None,
                }
                for leg in prediction.legs
            ],
        }
    )


def prediction_from_json(value: str, depart_at: datetime | None = None) -> RoutePrediction:
    payload: dict[str, Any] = json.loads(value)
    return RoutePrediction(
        depart_at=depart_at or datetime.fromisoformat(payload["departAt"]),
        duration_seconds=float(payload["durationSeconds"]),
        distance_meters=float(payload["distanceMeters"]),
        congestion=str(payload["congestion"]),
        legs=tuple(
            LegPrediction(
                distance_meters=float(leg["distanceMeters"]),
                duration_seconds=float(leg["durationSeconds"]),
                departure_at=(
                    datetime.fromisoformat(leg["departureAt"]) if leg["departureAt"] else None
                ),
                arrival_at=datetime.fromisoformat(leg["arrivalAt"]) if leg["arrivalAt"] else None,
            )
            for leg in payload["legs"]
        ),
    )

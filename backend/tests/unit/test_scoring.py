from datetime import UTC, datetime

import pytest

from app.domain import LegPrediction, RoutePrediction
from app.scoring import score_prediction


def prediction(total: float, legs: list[float]) -> RoutePrediction:
    return RoutePrediction(
        depart_at=datetime(2026, 9, 16, 8, 30, tzinfo=UTC),
        duration_seconds=total,
        distance_meters=5000,
        legs=tuple(
            LegPrediction(distance_meters=1000, duration_seconds=duration)
            for duration in legs
        ),
        congestion="Moderate",
    )


def test_scoring_applies_wipro_weight_and_counts_final_leg_only_in_total() -> None:
    baseline = prediction(500, [100, 100, 100, 100, 100])
    predicted = prediction(650, [110, 120, 130, 140, 250])

    result = score_prediction(predicted, baseline, [1, 1, 1, 2])

    assert result.leg_delay_seconds == (10, 20, 30, 40, 150)
    assert result.total_delay_seconds == 150
    assert result.weighted_signal_delay_seconds == 140
    assert result.score == 290


def test_scoring_clamps_negative_delays() -> None:
    baseline = prediction(500, [100, 100, 100, 100, 100])
    predicted = prediction(480, [90, 100, 95, 100, 95])

    result = score_prediction(predicted, baseline, [1, 1, 1, 2])

    assert result.total_delay_seconds == 0
    assert result.leg_delay_seconds == (0, 0, 0, 0, 0)
    assert result.score == 0


def test_scoring_rejects_mismatched_weights() -> None:
    baseline = prediction(500, [100, 100, 100, 100, 100])
    predicted = prediction(600, [120, 120, 120, 120, 120])

    with pytest.raises(ValueError, match="weight"):
        score_prediction(predicted, baseline, [1, 1])

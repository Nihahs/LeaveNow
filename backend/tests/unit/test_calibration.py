from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.calibration import CalibrationSample, calibrate_score
from app.domain import ScoreResult


def base_score() -> ScoreResult:
    return ScoreResult(
        total_delay_seconds=300,
        leg_delay_seconds=(60, 90, 120, 180, 30),
        weighted_signal_delay_seconds=630,
        score=930,
    )


def test_no_samples_preserves_prediction() -> None:
    result = calibrate_score(
        base_score(),
        datetime(2026, 9, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        (),
        (1, 1, 1, 2),
    )

    assert result.total_delay_seconds == 300
    assert result.signal_delay_seconds == (60, 90, 120, 180)
    assert result.score == 930
    assert result.confidence == 0


def test_one_sample_applies_twenty_percent_residual_correction() -> None:
    depart_at = datetime(2026, 9, 17, 10, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    sample = CalibrationSample(
        departed_at=depart_at,
        total_delay_residual_seconds=600,
        signal_delay_residual_seconds=(40, 60, -20, 300),
    )

    result = calibrate_score(
        base_score(),
        depart_at + timedelta(days=1),
        (sample,),
        (1, 1, 1, 2),
    )

    assert result.confidence == pytest.approx(0.2)
    assert result.total_delay_seconds == pytest.approx(420)
    assert result.signal_delay_seconds == pytest.approx((68, 102, 116, 240))
    assert result.score == pytest.approx(1186)


def test_five_samples_reach_full_confidence() -> None:
    depart_at = datetime(2026, 9, 17, 10, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    samples = tuple(
        CalibrationSample(
            departed_at=depart_at - timedelta(days=index),
            total_delay_residual_seconds=100,
            signal_delay_residual_seconds=(10, 10, 10, 10),
        )
        for index in range(5)
    )

    result = calibrate_score(base_score(), depart_at, samples, (1, 1, 1, 2))

    assert result.confidence == 1
    assert result.total_delay_seconds == pytest.approx(400)

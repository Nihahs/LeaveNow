from dataclasses import dataclass
from datetime import datetime

from app.domain import ScoreResult


@dataclass(frozen=True)
class CalibrationSample:
    departed_at: datetime
    total_delay_residual_seconds: float
    signal_delay_residual_seconds: tuple[float | None, ...]


@dataclass(frozen=True)
class CalibratedScore:
    total_delay_seconds: float
    signal_delay_seconds: tuple[float, ...]
    score: float
    sample_count: int
    confidence: float


def calibrate_score(
    base_score: ScoreResult,
    depart_at: datetime,
    samples: tuple[CalibrationSample, ...],
    signal_weights: tuple[float, ...],
) -> CalibratedScore:
    if not samples:
        return CalibratedScore(
            total_delay_seconds=base_score.total_delay_seconds,
            signal_delay_seconds=base_score.leg_delay_seconds[: len(signal_weights)],
            score=base_score.score,
            sample_count=0,
            confidence=0.0,
        )

    weighted_samples = [
        (sample, _sample_weight(depart_at, sample.departed_at)) for sample in samples
    ]
    total_weight = sum(weight for _, weight in weighted_samples)
    confidence = min(1.0, len(samples) / 5)
    total_correction = (
        sum(sample.total_delay_residual_seconds * weight for sample, weight in weighted_samples)
        / total_weight
    )
    total_delay = max(
        0.0,
        base_score.total_delay_seconds + (total_correction * confidence),
    )

    calibrated_signals: list[float] = []
    for index, predicted_delay in enumerate(
        base_score.leg_delay_seconds[: len(signal_weights)]
    ):
        available: list[tuple[float, float]] = []
        for sample, weight in weighted_samples:
            residual = sample.signal_delay_residual_seconds[index]
            if residual is not None:
                available.append((residual, weight))
        if not available:
            calibrated_signals.append(predicted_delay)
            continue
        available_weight = sum(weight for _, weight in available)
        correction = (
            sum(residual * weight for residual, weight in available) / available_weight
        )
        calibrated_signals.append(max(0.0, predicted_delay + (correction * confidence)))

    weighted_signal_delay = sum(
        delay * weight
        for delay, weight in zip(calibrated_signals, signal_weights, strict=True)
    )
    return CalibratedScore(
        total_delay_seconds=total_delay,
        signal_delay_seconds=tuple(calibrated_signals),
        score=total_delay + weighted_signal_delay,
        sample_count=len(samples),
        confidence=confidence,
    )


def _sample_weight(candidate: datetime, sample: datetime) -> float:
    candidate_minutes = candidate.hour * 60 + candidate.minute
    sample_minutes = sample.hour * 60 + sample.minute
    time_distance = abs(candidate_minutes - sample_minutes)
    time_weight = max(0.1, 1 - (time_distance / 180))
    weekday_weight = 1.5 if candidate.weekday() == sample.weekday() else 1.0
    day_distance = max(0, (candidate.date() - sample.date()).days)
    recency_weight = max(0.25, 1 - (day_distance / 60))
    return time_weight * weekday_weight * recency_weight

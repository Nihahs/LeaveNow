from collections.abc import Sequence

from app.domain import RoutePrediction, ScoreResult


def score_prediction(
    predicted: RoutePrediction,
    free_flow: RoutePrediction,
    signal_weights: Sequence[float],
) -> ScoreResult:
    if len(predicted.legs) != len(free_flow.legs):
        raise ValueError("Predicted and free-flow routes must have the same number of legs")
    if len(signal_weights) != max(0, len(predicted.legs) - 1):
        raise ValueError("A weight is required for each signal-terminating leg")
    if any(weight < 0 for weight in signal_weights):
        raise ValueError("Signal weights must be nonnegative")

    leg_delays = tuple(
        max(0.0, predicted_leg.duration_seconds - baseline_leg.duration_seconds)
        for predicted_leg, baseline_leg in zip(predicted.legs, free_flow.legs, strict=True)
    )
    total_delay = max(0.0, predicted.duration_seconds - free_flow.duration_seconds)
    weighted_signal_delay = sum(
        delay * weight
        for delay, weight in zip(
            leg_delays[: len(signal_weights)], signal_weights, strict=True
        )
    )
    return ScoreResult(
        total_delay_seconds=total_delay,
        leg_delay_seconds=leg_delays,
        weighted_signal_delay_seconds=weighted_signal_delay,
        score=total_delay + weighted_signal_delay,
    )

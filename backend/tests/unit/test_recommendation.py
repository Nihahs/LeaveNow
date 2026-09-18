from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.recommendation import _best_window, _eligible_series
from app.schemas import RecommendationPointSchema


def point(start: datetime, minute: int, score: float) -> RecommendationPointSchema:
    return RecommendationPointSchema(
        departAt=start + timedelta(minutes=minute),
        totalMinutes=20,
        delayMinutes=score / 60,
        score=score,
        congestion="Light",
        signalDelays=[],
    )


def test_best_window_uses_mean_score_and_earlier_tie_break() -> None:
    start = datetime(2026, 9, 16, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    series = [
        point(start, 0, 100),
        point(start, 5, 100),
        point(start, 10, 100),
        point(start, 15, 200),
        point(start, 20, 200),
    ]

    window_start, window_end, selected = _best_window(series)

    assert window_start == start
    assert window_end == start + timedelta(minutes=10)
    assert len(selected) == 3


def test_eligible_series_excludes_departures_that_already_passed_today() -> None:
    start = datetime(2026, 9, 18, 10, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    series = [
        point(start, 0, 100),
        point(start, 5, 90),
        point(start, 10, 110),
    ]

    eligible = _eligible_series(
        series,
        start.date(),
        "Asia/Kolkata",
        now=start + timedelta(minutes=7),
    )

    assert [candidate.departAt for candidate in eligible] == [
        start + timedelta(minutes=10)
    ]

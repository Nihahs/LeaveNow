from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.recommendation import _best_window, _good_windows
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


def test_good_windows_merge_contiguous_near_equal_departures() -> None:
    start = datetime(2026, 9, 18, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    series = [
        point(start, 0, 100),
        point(start, 5, 130),
        point(start, 10, 160),
        point(start, 15, 155),
        point(start, 20, 500),
    ]
    series[0].totalMinutes = 20
    series[1].totalMinutes = 20.2
    series[2].totalMinutes = 20.4
    series[3].totalMinutes = 20.5
    series[4].totalMinutes = 23

    groups = _good_windows(
        series,
        interval_minutes=5,
        total_tolerance_minutes=1,
        score_tolerance_seconds=60,
    )

    assert len(groups) == 1
    assert groups[0][0].departAt == start
    assert groups[0][-1].departAt == start + timedelta(minutes=15)


def test_good_windows_keep_separate_plateaus_disjoint() -> None:
    start = datetime(2026, 9, 18, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    series = [
        point(start, 0, 100),
        point(start, 5, 110),
        point(start, 10, 400),
        point(start, 15, 100),
        point(start, 20, 110),
    ]
    for candidate in series:
        candidate.totalMinutes = 20 if candidate.score < 200 else 24

    groups = _good_windows(
        series,
        interval_minutes=5,
        total_tolerance_minutes=1,
        score_tolerance_seconds=60,
    )

    assert len(groups) == 2
    assert [len(group) for group in groups] == [2, 2]

from datetime import datetime, timedelta

import pytest

from nexustrader.strategy import Strategy


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))


def test_set_timer_warns_and_delegates_to_schedule_interval():
    strategy = Strategy()
    strategy._initialized = True
    strategy._scheduler = FakeScheduler()

    def callback():
        return None

    start_time = datetime(2026, 4, 30, 12, 0, 0)
    stop_time = datetime(2026, 4, 30, 12, 5, 0)

    with pytest.warns(DeprecationWarning, match="set_timer\\(\\) is deprecated"):
        strategy.set_timer(
            callback=callback,
            interval=timedelta(seconds=5),
            name="tick",
            start_time=start_time,
            stop_time=stop_time,
        )

    assert strategy._scheduler.jobs == [
        (
            callback,
            "interval",
            {
                "seconds": 5.0,
                "name": "tick",
                "start_date": start_time,
                "end_date": stop_time,
            },
        )
    ]

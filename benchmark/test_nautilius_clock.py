import time
import timeit
from nexustrader.core.nautilius_core import LiveClock


def test_nautilius_clock(clock: LiveClock = LiveClock()):
    _timestamp = clock.timestamp_ms()


def py_time_clock_1():
    _timestamp = int(time.time() * 1000)


def py_time_clock_2():
    _timestamp = time.time_ns() // 1_000_000


def benchmark_clocks():
    """Benchmark different clock implementations"""
    clock = LiveClock()

    # Test nautilus clock
    nautilus_time = timeit.timeit(
        "test_nautilius_clock(clock)",
        globals={"test_nautilius_clock": test_nautilius_clock, "clock": clock},
        number=1000000,
    )
    print(f"Nautilus clock: {nautilus_time:.6f} seconds")

    # Test Python time.time() * 1000
    py_time1 = timeit.timeit(
        "py_time_clock_1()",
        globals={"py_time_clock_1": py_time_clock_1},
        number=1000000,
    )
    print(f"Python time.time() * 1000: {py_time1:.6f} seconds")

    # Test Python time.time_ns() // 1_000_000
    py_time2 = timeit.timeit(
        "py_time_clock_2()",
        globals={"py_time_clock_2": py_time_clock_2},
        number=1000000,
    )
    print(f"Python time.time_ns() // 1_000_000: {py_time2:.6f} seconds")


if __name__ == "__main__":
    benchmark_clocks()

from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.component import LiveClock
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.core.uuid import UUID4

from nautilus_trader.core import nautilus_pyo3  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpMethod  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpResponse  # noqa

# from nautilus_trader.core.nautilus_pyo3 import MessageBus  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketClientError  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketConfig  # noqa
from nautilus_trader.core.nautilus_pyo3 import (
    hmac_signature,  # noqa
    rsa_signature,  # noqa
    ed25519_signature,  # noqa
)
from nautilus_trader.common.component import Logger, set_logging_pyo3  # noqa


def setup_nautilus_core(
    trader_id: str,
    level_stdout: str,
    level_file: str | None = None,
    component_levels: dict[str, str] | None = None,
    directory: str | None = None,
    file_name: str | None = None,
    file_format: str | None = None,
    file_rotate: tuple[int, int] | None = None,
    is_colored: bool | None = None,
    is_bypassed: bool | None = None,
    print_config: bool | None = None,
):
    """
    Setup logging for the application.
    """
    clock = LiveClock()
    msgbus = MessageBus(
        trader_id=TraderId(trader_id),
        clock=clock,
    )
    set_logging_pyo3(True)

    instance_id = nautilus_pyo3.UUID4().value
    log_guard = nautilus_pyo3.init_logging(
        trader_id=nautilus_pyo3.TraderId(trader_id),
        instance_id=nautilus_pyo3.UUID4.from_str(instance_id),
        level_stdout=nautilus_pyo3.LogLevel(level_stdout),
        level_file=nautilus_pyo3.LogLevel(level_file) if level_file else None,
        directory=directory,
        file_name=file_name,
        file_format=file_format,
        is_colored=is_colored,
        print_config=print_config,
        component_levels=component_levels,
        file_rotate=file_rotate,
        is_bypassed=is_bypassed,
    )

    return log_guard, msgbus, clock


def usage():
    import time

    print(UUID4().value)
    print(UUID4().value)
    print(UUID4().value)

    uuid_to_order_id = {}

    uuid = UUID4()

    order_id = "123456"

    uuid_to_order_id[uuid] = order_id

    print(uuid_to_order_id)

    clock = LiveClock()
    print(clock.timestamp())
    print(type(clock.timestamp_ms()))

    print(clock.utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z"))

    def handler1(msg):
        print(f"[{clock.timestamp_ns()}] Received message: {msg} - handler1")

    def handler2(msg):
        print(f"[{clock.timestamp_ns()}] Received message: {msg} - handler2")

    def handler3(msg):
        print(f"[{clock.timestamp_ns()}] Received message: {msg} - handler3")

    log_guard, msgbus = setup_logging_and_msgbus(
        trader_id="TESTER-001",
        level_stdout="DEBUG",
    )

    # msgbus.subscribe(topic="order", handler=handler1)
    # msgbus.subscribe(topic="order", handler=handler2)
    # msgbus.subscribe(topic="order", handler=handler3)

    # try:
    #     while True:
    #         msgbus.publish(topic="order", msg="hello")
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("Exiting...")

    # print("done")
    from datetime import timedelta, datetime

    count = 0

    def count_handler(msg):
        nonlocal count
        count += 1
        print(f"[{clock.utc_now()}] Count: {count} - Received message")

    clock = LiveClock()
    # clock.register_default_handler(count_handler)
    name = "TEST_TIMER 111"
    interval = timedelta(milliseconds=100)
    start_time = clock.utc_now()
    clock.set_timer(
        name=name,
        interval=interval,
        start_time=start_time,
        stop_time=None,
        callback=count_handler,
    )

    time.sleep(10000)


if __name__ == "__main__":
    usage()

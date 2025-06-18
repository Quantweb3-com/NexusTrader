from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.component import LiveClock
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.core.uuid import UUID4

from nautilus_trader.core import nautilus_pyo3  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpMethod  # noqa
from nautilus_trader.core.nautilus_pyo3 import HttpResponse  # noqa

from nautilus_trader.core.nautilus_pyo3 import WebSocketClient  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketClientError  # noqa
from nautilus_trader.core.nautilus_pyo3 import WebSocketConfig  # noqa
from nautilus_trader.core.nautilus_pyo3 import (
    hmac_signature,  # noqa
    rsa_signature,  # noqa
    ed25519_signature,  # noqa
)
from nautilus_trader.common.component import Logger, set_logging_pyo3  # noqa


def usage():
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

    msgbus = MessageBus(
        trader_id=TraderId("TESTER-001"),
        clock=clock,
    )

    msgbus.subscribe(topic="order", handler=handler1)
    msgbus.subscribe(topic="order", handler=handler2)
    msgbus.subscribe(topic="order", handler=handler3)

    msgbus.publish(topic="order", msg="hello")

    print("done")


if __name__ == "__main__":
    usage()

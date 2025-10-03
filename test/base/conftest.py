import pytest
import time
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.registry import OrderRegistry
from nautilus_trader.model.identifiers import TraderId
from nexustrader.schema import ExchangeType, BookL1
import pickle

"""
Creates one fixture for the entire test run
Most efficient but least isolated
Example: Database connection that can be reused across all tests
"""


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def market():
    return pickle.load(open("./test/test_data/market.pkl", "rb"))


@pytest.fixture
def market_id():
    return pickle.load(open("./test/test_data/market_id.pkl", "rb"))


@pytest.fixture
def task_manager(event_loop_policy):
    loop = event_loop_policy.new_event_loop()
    return TaskManager(loop, enable_signal_handlers=False)


@pytest.fixture
def message_bus():
    return MessageBus(trader_id=TraderId("TEST-001"), clock=LiveClock())


@pytest.fixture
def order_registry():
    return OrderRegistry()


@pytest.fixture
def exchange(market, market_id):
    class MockExchangeManager:
        def __init__(self):
            self.market = market
            self.market_id = market_id
            self.exchange_id = ExchangeType.BINANCE

    return MockExchangeManager()


class BookL1Mock:
    def __init__(self):
        self.call_count = 0

        self._data = {
            "BTCUSDT-PERP.BINANCE": [
                BookL1(
                    exchange=ExchangeType.BINANCE,
                    symbol="BTCUSDT-PERP",
                    bid=10000,
                    ask=10000,
                    bid_size=1,
                    ask_size=1,
                    timestamp=10000,
                ),
                BookL1(
                    exchange=ExchangeType.BINANCE,
                    symbol="BTCUSDT-PERP",
                    bid=10000,
                    ask=10000,
                    bid_size=1,
                    ask_size=1,
                    timestamp=10001,
                ),
                BookL1(
                    exchange=ExchangeType.BINANCE,
                    symbol="BTCUSDT-PERP",
                    bid=11000,
                    ask=11000,
                    bid_size=1,
                    ask_size=1,
                    timestamp=10002,
                ),
                BookL1(
                    exchange=ExchangeType.BINANCE,
                    symbol="BTCUSDT-PERP",
                    bid=9000,
                    ask=9000,
                    bid_size=1,
                    ask_size=1,
                    timestamp=10003,
                ),
            ]
        }

    def get_bookl1(self, symbol: str) -> BookL1:
        if symbol not in self._data:
            return None
        idx = self.call_count % len(self._data[symbol])
        print(f"Current index: {idx}, Total calls: {self.call_count}")

        bookl1 = self._data[symbol][idx]
        self.call_count += 1
        return bookl1


@pytest.fixture
def bookl1_mock() -> BookL1Mock:
    return BookL1Mock()


@pytest.fixture
async def cache(task_manager, message_bus, order_registry, bookl1_mock: BookL1Mock):
    from nexustrader.core.cache import AsyncCache

    cache = AsyncCache(
        strategy_id="strategy-mock",
        user_id="user-mock",
        msgbus=message_bus,
        task_manager=task_manager,
        registry=order_registry,
    )

    cache.bookl1 = bookl1_mock.get_bookl1

    yield cache
    await cache.close()

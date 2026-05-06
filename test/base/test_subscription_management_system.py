import asyncio
from types import SimpleNamespace

import pytest

from nexustrader.base.sms import SubscriptionManagementSystem
from nexustrader.constants import BookLevel, DataType, ExchangeType
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.binance.constants import BinanceAccountType


class _TaskManager:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class _PublicConnector:
    def __init__(self):
        self.calls = []

    async def subscribe_bookl2(self, symbols, level):
        self.calls.append(("subscribe_bookl2", list(symbols), level))

    async def unsubscribe_bookl2(self, symbols, level):
        self.calls.append(("unsubscribe_bookl2", list(symbols), level))


@pytest.mark.asyncio
async def test_subscription_operations_preserve_resubscribe_order():
    connector = _PublicConnector()
    task_manager = _TaskManager()
    account_type = BinanceAccountType.USD_M_FUTURE
    exchange = SimpleNamespace(
        instrument_id_to_account_type=lambda instrument_id: account_type
    )
    sms = SubscriptionManagementSystem(
        exchanges={ExchangeType.BINANCE: exchange},
        public_connectors={account_type: connector},
        task_manager=task_manager,
        clock=LiveClock(),
    )
    await sms.start()

    symbol = "TAUSDT-PERP.BINANCE"
    sms.unsubscribe(symbol, DataType.BOOKL2, params={"level": BookLevel.L5})
    sms.subscribe(
        symbol,
        DataType.BOOKL2,
        params={"level": BookLevel.L5},
        ready=False,
    )

    await asyncio.wait_for(sms._operation_queue.join(), timeout=1.0)

    assert connector.calls == [
        ("unsubscribe_bookl2", [symbol], BookLevel.L5),
        ("subscribe_bookl2", [symbol], BookLevel.L5),
    ]

    for task in task_manager.tasks:
        task.cancel()
    await asyncio.gather(*task_manager.tasks, return_exceptions=True)

import asyncio
from typing import Dict, List
from decimal import Decimal
from nexustrader.constants import AccountType, SubmitType
from nexustrader.schema import OrderSubmit, InstrumentId
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bybit import BybitAccountType
from nexustrader.exchange.bybit.schema import BybitMarket
from nexustrader.base import ExecutionManagementSystem


class BybitExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, BybitMarket]

    def __init__(
        self,
        market: Dict[str, BybitMarket],
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
        is_mock: bool = False,
    ):
        super().__init__(
            market=market,
            cache=cache,
            msgbus=msgbus,
            task_manager=task_manager,
            registry=registry,
            is_mock=is_mock,
        )
        self._bybit_account_type: BybitAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, BybitAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()

    def _set_account_type(self):
        account_types = self._private_connectors.keys()
        self._bybit_account_type = (
            BybitAccountType.UNIFIED_TESTNET
            if BybitAccountType.UNIFIED_TESTNET in account_types
            else BybitAccountType.UNIFIED
        )

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        if self._is_mock:
            if instrument_id.is_spot:
                return BybitAccountType.SPOT_MOCK
            elif instrument_id.is_linear:
                return BybitAccountType.LINEAR_MOCK
            elif instrument_id.is_inverse:
                return BybitAccountType.INVERSE_MOCK
        else:
            return self._bybit_account_type

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        if not account_type:
            if isinstance(order, list):
                account_type = self._instrument_id_to_account_type(
                    order[0].instrument_id
                )
            else:
                account_type = self._instrument_id_to_account_type(order.instrument_id)
        self._order_submit_queues[account_type].put_nowait((order, submit_type))

    def _get_min_order_amount(self, symbol: str, market: BybitMarket) -> Decimal:
        book = self._cache.bookl1(symbol)
        min_order_qty = float(market.info.lotSizeFilter.minOrderQty)
        min_order_amt = float(
            market.info.lotSizeFilter.minOrderAmt
            or market.info.lotSizeFilter.minNotionalValue
        )
        min_order_amount = max(min_order_amt * 1.02 / book.mid, min_order_qty)
        min_order_amount = self._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )
        return min_order_amount

import asyncio
from typing import Dict, List
from decimal import Decimal
from nexustrader.constants import AccountType, SubmitType
from nexustrader.schema import OrderSubmit, InstrumentId, CancelAllOrderSubmit
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bitget import BitgetAccountType
from nexustrader.exchange.bitget.schema import BitgetMarket
from nexustrader.base import ExecutionManagementSystem


class BitgetExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, BitgetMarket]

    def __init__(
        self,
        market: Dict[str, BitgetMarket],
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        registry: OrderRegistry,
        is_mock: bool = False,
    ):
        super().__init__(
            market=market,
            cache=cache,
            msgbus=msgbus,
            clock=clock,
            task_manager=task_manager,
            registry=registry,
            is_mock=is_mock,
        )

        self._bitget_futures_account_type: BitgetAccountType = None
        self._bitget_spot_account_type: BitgetAccountType = None
        self._bitget_uta_account_type: BitgetAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, BitgetAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()

    def _set_account_type(self):
        account_types = self._private_connectors.keys()

        if (
            BitgetAccountType.UTA_DEMO in account_types
            or BitgetAccountType.UTA in account_types
        ):
            self._bitget_uta_account_type = (
                BitgetAccountType.UTA_DEMO
                if BitgetAccountType.UTA_DEMO in account_types
                else BitgetAccountType.UTA
            )
            return

        self._bitget_futures_account_type = (
            BitgetAccountType.FUTURE_DEMO
            if BitgetAccountType.FUTURE_DEMO in account_types
            else BitgetAccountType.FUTURE
        )

        self._bitget_spot_account_type = (
            BitgetAccountType.SPOT_DEMO
            if BitgetAccountType.SPOT_DEMO in account_types
            else BitgetAccountType.SPOT
        )

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        if self._is_mock:
            if instrument_id.is_spot:
                return BitgetAccountType.SPOT_MOCK
            elif instrument_id.is_linear:
                return BitgetAccountType.LINEAR_MOCK
            elif instrument_id.is_inverse:
                return BitgetAccountType.INVERSE_MOCK
        else:
            if self._bitget_uta_account_type:
                return self._bitget_uta_account_type
            if instrument_id.is_spot:
                return self._bitget_spot_account_type
            elif instrument_id.is_linear or instrument_id.is_inverse:
                return self._bitget_futures_account_type

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        if isinstance(order, list):
            if not account_type:
                account_type = self._instrument_id_to_account_type(
                    order[0].instrument_id
                )

            # Split batch orders into chunks of 20
            for i in range(0, len(order), 20):
                batch = order[i : i + 20]
                self._order_submit_queues[account_type].put_nowait((batch, submit_type))
        else:
            if not account_type:
                account_type = self._instrument_id_to_account_type(order.instrument_id)
            self._order_submit_queues[account_type].put_nowait((order, submit_type))

    def _get_min_order_amount(self, symbol: str, market: BitgetMarket) -> Decimal:
        book = self._cache.bookl1(symbol)
        min_order_amt = market.limits.amount.min
        min_order_cost = market.limits.cost.min
        min_order_amount = max(min_order_cost * 1.02 / book.mid, min_order_amt)
        min_order_amount = self._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )
        return min_order_amount


    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        # override the base method
        symbol = order_submit.symbol
        uuids = self._cache.get_open_orders(symbol)
        for uuid in uuids:
            order_id = self._registry.get_order_id(uuid)
            if not order_id:
                continue
            await self._private_connectors[account_type].cancel_order(
                symbol=symbol,
                order_id=order_id,
            )


import asyncio
from decimal import Decimal
from typing import Dict, List
from nexustrader.constants import AccountType, SubmitType
from nexustrader.schema import OrderSubmit, InstrumentId
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.hyperliquid import HyperLiquidAccountType
from nexustrader.exchange.hyperliquid.schema import HyperLiquidMarket
from nexustrader.base import ExecutionManagementSystem
from nexustrader.schema import CancelAllOrderSubmit, CancelOrderSubmit


class HyperLiquidExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, HyperLiquidMarket]

    HYPER_LIQUID_ACCOUNT_TYPE_PRIORITY = [
        HyperLiquidAccountType.MAINNET,
        HyperLiquidAccountType.TESTNET,
    ]

    def __init__(
        self,
        market: Dict[str, HyperLiquidMarket],
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
        self._hyperliquid_account_type: HyperLiquidAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, HyperLiquidAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()
                break

    def _set_account_type(self):
        account_types = self._private_connectors.keys()
        for account_type in self.HYPER_LIQUID_ACCOUNT_TYPE_PRIORITY:
            if account_type in account_types:
                self._hyperliquid_account_type = account_type
                break

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        if self._is_mock:
            if instrument_id.is_spot:
                return HyperLiquidAccountType.SPOT_MOCK
            elif instrument_id.is_linear:
                return HyperLiquidAccountType.LINEAR_MOCK
            elif instrument_id.is_inverse:
                return HyperLiquidAccountType.INVERSE_MOCK
        else:
            return self._hyperliquid_account_type

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

    def _get_min_order_amount(self, symbol: str, market: HyperLiquidMarket) -> Decimal:
        book = self._cache.bookl1(symbol)
        min_order_cost = market.limits.cost.min
        min_order_amount = super()._amount_to_precision(
            symbol, min_order_cost / book.mid * 1.01, mode="ceil"
        )
        return min_order_amount

    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        # override the base method
        symbol = order_submit.symbol
        uuids = self._cache.get_open_orders(symbol)
        for uuid in uuids:
            order_submit = CancelOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                uuid=uuid,
            )
            await self._cancel_order(order_submit, account_type)

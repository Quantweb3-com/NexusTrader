import asyncio
from decimal import Decimal
from typing import Dict, List, Literal
from nexustrader.constants import AccountType, SubmitType
from nexustrader.schema import OrderSubmit, InstrumentId
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.exchange.okx.schema import OkxMarket
from nexustrader.base import ExecutionManagementSystem
from nexustrader.schema import CancelAllOrderSubmit


class OkxExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, OkxMarket]

    OKX_ACCOUNT_TYPE_PRIORITY = [
        OkxAccountType.DEMO,
        OkxAccountType.AWS,
        OkxAccountType.LIVE,
    ]

    def __init__(
        self,
        market: Dict[str, OkxMarket],
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
        self._okx_account_type: OkxAccountType = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, OkxAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()
                break

    def _set_account_type(self):
        account_types = self._private_connectors.keys()
        for account_type in self.OKX_ACCOUNT_TYPE_PRIORITY:
            if account_type in account_types:
                self._okx_account_type = account_type
                break

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        if self._is_mock:
            if instrument_id.is_spot:
                return OkxAccountType.SPOT_MOCK
            elif instrument_id.is_linear:
                return OkxAccountType.LINEAR_MOCK
            elif instrument_id.is_inverse:
                return OkxAccountType.INVERSE_MOCK
        else:
            return self._okx_account_type

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        if not account_type:
            if isinstance(order, list) and order:
                account_type = self._instrument_id_to_account_type(
                    order[0].instrument_id
                )
            else:
                account_type = self._instrument_id_to_account_type(order.instrument_id)
        self._order_submit_queues[account_type].put_nowait((order, submit_type))

    def _get_min_order_amount(self, symbol: str, market: OkxMarket) -> Decimal:
        min_order_amount = market.limits.amount.min
        min_order_amount = super()._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )

        if not market.spot:
            # for linear and inverse, the min order amount is contract size and ctVal is base amount per contract
            min_order_amount *= Decimal(market.info.ctVal)

        return min_order_amount

    # override the base method
    def _amount_to_precision(
        self,
        symbol: str,
        amount: float,
        mode: Literal["round"] | Literal["ceil"] | Literal["floor"] = "round",
    ) -> Decimal:
        market = self._market[symbol]
        ctVal = Decimal("1")
        if not market.spot:
            ctVal = Decimal(market.info.ctVal)
            amount = Decimal(str(amount)) / ctVal
        return super()._amount_to_precision(symbol, amount, mode) * ctVal

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

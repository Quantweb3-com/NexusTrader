import asyncio
from decimal import Decimal
from typing import Dict, List
from nexustrader.constants import AccountType, SubmitType
from nexustrader.schema import OrderSubmit, InstrumentId
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.exchange.binance.schema import BinanceMarket
from nexustrader.base import ExecutionManagementSystem


class BinanceExecutionManagementSystem(ExecutionManagementSystem):
    _market: Dict[str, BinanceMarket]

    BINANCE_SPOT_PRIORITY = [
        BinanceAccountType.ISOLATED_MARGIN,
        BinanceAccountType.MARGIN,
        BinanceAccountType.SPOT_TESTNET,
        BinanceAccountType.SPOT,
    ]

    def __init__(
        self,
        market: Dict[str, BinanceMarket],
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
        self._binance_spot_account_type: BinanceAccountType = None
        self._binance_linear_account_type: BinanceAccountType = None
        self._binance_inverse_account_type: BinanceAccountType = None
        self._binance_pm_account_type: BinanceAccountType = None

    def _set_account_type(self):
        account_types = self._private_connectors.keys()

        if self._is_mock:
            self._binance_spot_account_type = BinanceAccountType.SPOT_MOCK
            self._binance_linear_account_type = BinanceAccountType.LINEAR_MOCK
            self._binance_inverse_account_type = BinanceAccountType.INVERSE_MOCK
        else:
            if BinanceAccountType.PORTFOLIO_MARGIN in account_types:
                self._binance_pm_account_type = BinanceAccountType.PORTFOLIO_MARGIN
                return

            for account_type in self.BINANCE_SPOT_PRIORITY:
                if account_type in account_types:
                    self._binance_spot_account_type = account_type
                    break

            self._binance_linear_account_type = (
                BinanceAccountType.USD_M_FUTURE_TESTNET
                if BinanceAccountType.USD_M_FUTURE_TESTNET in account_types
                else BinanceAccountType.USD_M_FUTURE
            )

            self._binance_inverse_account_type = (
                BinanceAccountType.COIN_M_FUTURE_TESTNET
                if BinanceAccountType.COIN_M_FUTURE_TESTNET in account_types
                else BinanceAccountType.COIN_M_FUTURE
            )

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        if self._binance_pm_account_type:
            return self._binance_pm_account_type
        if instrument_id.is_spot:
            return self._binance_spot_account_type
        elif instrument_id.is_linear:
            return self._binance_linear_account_type
        elif instrument_id.is_inverse:
            return self._binance_inverse_account_type

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, BinanceAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()

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

    def _get_min_order_amount(self, symbol: str, market: BinanceMarket) -> Decimal:
        book = self._cache.bookl1(symbol)
        cost_min = market.limits.cost.min
        amount_min = market.limits.amount.min

        min_order_amount = max(cost_min / book.mid, amount_min)
        min_order_amount = self._amount_to_precision(
            symbol, min_order_amount, mode="ceil"
        )
        return min_order_amount

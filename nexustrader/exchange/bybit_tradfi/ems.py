"""
ExecutionManagementSystem for Bybit TradeFi (MT5).

MT5 has only one account type (LIVE or DEMO), so the order-routing
logic is much simpler than multi-product crypto exchanges.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import List

from nexustrader.base.ems import ExecutionManagementSystem
from nexustrader.constants import AccountType, SubmitType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager
from nexustrader.schema import BaseMarket, InstrumentId, OrderSubmit


class BybitTradeFiExecutionManagementSystem(ExecutionManagementSystem):
    """
    EMS for Bybit TradeFi.

    A single asyncio.Queue is used for all order submissions because MT5
    has only one unified account (LIVE or DEMO).
    """

    def __init__(
        self,
        exchange: BybitTradeFiExchangeManager,
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        registry: OrderRegistry,
        is_mock: bool = False,
    ) -> None:
        super().__init__(
            market=exchange.market,
            cache=cache,
            msgbus=msgbus,
            clock=clock,
            task_manager=task_manager,
            registry=registry,
            is_mock=is_mock,
        )
        self._exchange = exchange
        self._account_type: BybitTradeFiAccountType | None = None

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _set_account_type(self) -> None:
        """Determine whether we are using a LIVE or DEMO account."""
        for at in self._private_connectors:
            if isinstance(at, BybitTradeFiAccountType):
                self._account_type = at
                return

    def _build_order_submit_queues(self) -> None:
        """Create one asyncio.Queue per BybitTradeFi account type found in private connectors."""
        for at in self._private_connectors:
            if isinstance(at, BybitTradeFiAccountType):
                self._order_submit_queues[at] = asyncio.Queue()

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> BybitTradeFiAccountType:
        """All MT5 instruments route to the single configured account type."""
        if self._account_type is not None:
            return self._account_type
        # Fallback: use exchange manager logic
        return self._exchange.instrument_id_to_account_type(instrument_id)

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ) -> None:
        if isinstance(order, list):
            at = account_type or (
                self._instrument_id_to_account_type(order[0].instrument_id)
                if order
                else self._account_type
            )
            self._order_submit_queues[at].put_nowait((order, submit_type))
        else:
            at = account_type or self._instrument_id_to_account_type(
                order.instrument_id
            )
            self._order_submit_queues[at].put_nowait((order, submit_type))

    def _get_min_order_amount(
        self, symbol: str, market: BaseMarket, px: float
    ) -> Decimal:
        """Minimum order volume from MT5 symbol info."""
        min_vol = market.limits.amount.min
        if min_vol is None:
            min_vol = market.precision.amount
        return Decimal(str(min_vol))

import asyncio
from decimal import Decimal
from typing import Dict, List

from nexustrader.base import ExecutionManagementSystem
from nexustrader.constants import AccountType, SubmitType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.schema import BaseMarket, InstrumentId, OrderSubmit

from .constants import KucoinAccountType


class KucoinExecutionManagementSystem(ExecutionManagementSystem):

    _market: Dict[str, BaseMarket]

    # Prefer Margin over Spot if both are connected for spot instruments
    KUCOIN_SPOT_PRIORITY = [KucoinAccountType.MARGIN, KucoinAccountType.SPOT]

    def __init__(
        self,
        market: Dict[str, BaseMarket],
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
        self._kucoin_spot_account_type: KucoinAccountType | None = None
        self._kucoin_futures_account_type: KucoinAccountType | None = None

    def _build_order_submit_queues(self):
        for account_type in self._private_connectors.keys():
            if isinstance(account_type, KucoinAccountType):
                self._order_submit_queues[account_type] = asyncio.Queue()

    def _set_account_type(self):
        account_types = self._private_connectors.keys()

        if KucoinAccountType.SPOT in account_types:
            self._kucoin_futures_account_type = KucoinAccountType.SPOT
        if KucoinAccountType.FUTURES in account_types:
            self._kucoin_futures_account_type = KucoinAccountType.FUTURES

    def _instrument_id_to_account_type(self, instrument_id: InstrumentId) -> AccountType:
        if instrument_id.is_spot:
            if self._kucoin_spot_account_type:
                return self._kucoin_spot_account_type
            return KucoinAccountType.SPOT
        elif instrument_id.is_linear or instrument_id.is_inverse:
            return self._kucoin_futures_account_type or KucoinAccountType.FUTURES

    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        if isinstance(order, list):
            if not account_type:
                account_type = self._instrument_id_to_account_type(order[0].instrument_id)

            # Split batch orders into chunks (KuCoin allows sizeable batches; 20 is a safe queue chunk)
            for i in range(0, len(order), 20):
                batch = order[i : i + 20]
                self._order_submit_queues[account_type].put_nowait((batch, submit_type))
        else:
            if not account_type:
                account_type = self._instrument_id_to_account_type(order.instrument_id)
            self._order_submit_queues[account_type].put_nowait((order, submit_type))

    def _get_min_order_amount(self, symbol: str, market: BaseMarket, px: float) -> Decimal:
        
        amount_min = market.limits.amount.min if market.limits and market.limits.amount else None
        cost_min = market.limits.cost.min if market.limits and market.limits.cost else None

        min_amt = Decimal("0")
        if market.spot:
            candidates: list[Decimal] = []
            if cost_min is not None and px > 0:
                try:
                    candidates.append(Decimal(str(cost_min)) * Decimal("1.01") / Decimal(str(px)))
                except Exception:
                    pass
            if amount_min is not None:
                candidates.append(Decimal(str(amount_min)))
            if candidates:
                min_amt = max(candidates)
            else:
                min_amt = Decimal("0")
        else:
            lot_size = None
            try:
                lot_size = getattr(market.info, "lotSize", None)
            except Exception:
                lot_size = None

            if lot_size is not None:
                min_amt = Decimal(str(lot_size))
            elif amount_min is not None:
                min_amt = Decimal(str(amount_min))
            else:
                min_amt = Decimal("0")

        min_amt = self._amount_to_precision(symbol, float(min_amt), mode="ceil")
        return min_amt

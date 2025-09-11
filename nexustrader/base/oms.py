from abc import ABC, abstractmethod
from typing import Dict, List, Literal
from decimal import Decimal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import Logger, LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.base.api_client import ApiClient
from nexustrader.base.ws_client import WSClient
from nexustrader.schema import (
    Order,
    BaseMarket,
    BatchOrderSubmit,
)
from nexustrader.constants import (
    OrderSide,
    OrderType,
    TimeInForce,
    TriggerType,
    OrderStatus,
)


class OrderManagementSystem(ABC):
    def __init__(
        self,
        account_type: AccountType,
        market: Dict[str, BaseMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: ApiClient,
        ws_client: WSClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
    ):
        self._log = Logger(name=type(self).__name__)
        self._market = market
        self._market_id = market_id
        self._registry = registry
        self._account_type = account_type
        self._cache = cache
        self._api_client = api_client
        self._ws_client = ws_client
        self._exchange_id = exchange_id
        self._clock = clock
        self._msgbus = msgbus

        self._init_account_balance()
        self._init_position()
        self._position_mode_check()

    def order_status_update(self, order: Order):
        match order.status:
            case OrderStatus.PENDING:
                self._log.debug(f"ORDER STATUS PENDING: {str(order)}")
                self._cache._order_initialized(order)  # INITIALIZED -> PENDING
                self._msgbus.send(endpoint="pending", msg=order)
            case OrderStatus.FAILED:
                self._log.debug(f"ORDER STATUS FAILED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="failed", msg=order)
            case OrderStatus.ACCEPTED:
                self._log.debug(f"ORDER STATUS ACCEPTED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="accepted", msg=order)
            case OrderStatus.PARTIALLY_FILLED:
                self._log.debug(f"ORDER STATUS PARTIALLY FILLED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="partially_filled", msg=order)
            case OrderStatus.CANCELED:
                self._log.debug(f"ORDER STATUS CANCELED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="canceled", msg=order)
            case OrderStatus.CANCELING:
                self._log.debug(f"ORDER STATUS CANCELING: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="canceling", msg=order)
            case OrderStatus.CANCEL_FAILED:
                self._log.debug(f"ORDER STATUS CANCEL FAILED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="cancel_failed", msg=order)
            case OrderStatus.FILLED:
                self._log.debug(f"ORDER STATUS FILLED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="filled", msg=order)
            case OrderStatus.EXPIRED:
                self._log.debug(f"ORDER STATUS EXPIRED: {str(order)}")
                self._cache._order_status_update(order)
            case _:
                self._log.error(f"ORDER STATUS UNKNOWN: {str(order)}")

    def _price_to_precision(
        self,
        symbol: str,
        price: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        """
        Convert the price to the precision of the market
        """
        market = self._market[symbol]
        price: Decimal = Decimal(str(price))

        decimal = market.precision.price

        if decimal >= 1:
            exp = Decimal(int(decimal))
            precision_decimal = Decimal("1")
        else:
            exp = Decimal("1")
            precision_decimal = Decimal(str(decimal))

        if mode == "round":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_HALF_UP
            ) * exp
        elif mode == "ceil":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_CEILING
            ) * exp
        elif mode == "floor":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_FLOOR
            ) * exp
        return format_price

    @abstractmethod
    def _init_account_balance(self):
        """Initialize the account balance"""
        pass

    @abstractmethod
    def _init_position(self):
        """Initialize the position"""
        pass

    @abstractmethod
    def _position_mode_check(self):
        """Check the position mode"""
        pass

    @abstractmethod
    async def create_tp_sl_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = TimeInForce.GTC,
        tp_order_type: OrderType | None = None,
        tp_trigger_price: Decimal | None = None,
        tp_price: Decimal | None = None,
        tp_trigger_type: TriggerType | None = TriggerType.LAST_PRICE,
        sl_order_type: OrderType | None = None,
        sl_trigger_price: Decimal | None = None,
        sl_price: Decimal | None = None,
        sl_trigger_type: TriggerType | None = TriggerType.LAST_PRICE,
        **kwargs,
    ) -> Order:
        """Create a take profit and stop loss order"""
        pass

    @abstractmethod
    async def create_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce,
        reduce_only: bool,
        # position_side: PositionSide,
        **kwargs,
    ) -> Order:
        """Create an order"""
        pass

    @abstractmethod
    async def create_order_ws(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce,
        reduce_only: bool,
        # position_side: PositionSide,
        **kwargs,
    ):
        pass

    @abstractmethod
    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create a batch of orders"""
        pass

    @abstractmethod
    async def cancel_order(
        self, oid: str, symbol: str, **kwargs
    ) -> Order:
        """Cancel an order"""
        pass

    @abstractmethod
    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        """Cancel an order"""
        pass

    @abstractmethod
    async def modify_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        """Modify an order"""
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders"""
        pass

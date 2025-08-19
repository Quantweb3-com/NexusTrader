from abc import ABC, abstractmethod
from typing import Dict, List, Literal
from decimal import Decimal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import Logger, LiveClock
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

        self._init_account_balance()
        self._init_position()
        self._position_mode_check()

    def order_submit(self, order: Order):
        """
        Handle the order event
        """
        # handle the ACCEPTED, PARTIALLY_FILLED, CANCELED, FILLED, EXPIRED arived early than the order submit uuid
        uuid = self._registry.get_uuid(order.id)  # check if the order id is registered
        if not uuid:
            self._log.debug(f"WAIT FOR ORDER ID: {order.id} TO BE REGISTERED")
            self._registry.add_to_waiting(order)
        else:
            order.uuid = uuid
            self._registry.order_status_update(order)

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
        uuid: str,
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
        uuid: str,
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
    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create a batch of orders"""
        pass

    @abstractmethod
    async def cancel_order(self, uuid:str, symbol: str, order_id: str, **kwargs) -> Order:
        """Cancel an order"""
        pass

    @abstractmethod
    async def modify_order(
        self,
        uuid: str,
        symbol: str,
        order_id: str,
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

import asyncio
import msgspec
import sys
from typing import Dict, Any, List
from decimal import Decimal
from nexustrader.error import PositionModeError
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
    KlineInterval,
    TriggerType,
    BookLevel,
)
from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    MarkPrice,
    FundingRate,
    IndexPrice,
    BookL2,
    Order,
    Position,
    KlineList,
    BatchOrderSubmit,
    Ticker,
)
from nexustrader.exchange.hyperliquid.schema import HyperLiquidMarket
from nexustrader.exchange.hyperliquid.rest_api import HyperLiquidApiClient
from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType
from nexustrader.exchange.hyperliquid.websockets import HyperLiquidWSClient
from nexustrader.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidOrderType,
    HyperLiquidTimeInForce,
    HyperLiquidOrderSide,
)
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidKline,
    HyperLiquidTrade,
    HyperLiquidOrderBook,
    HyperLiquidTicker,
)
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager


class HyperLiquidPublicConnector(PublicConnector):
    """Public connector for Hyperliquid exchange"""
    
    _ws_client: HyperLiquidWSClient
    _account_type: HyperLiquidAccountType
    _market: Dict[str, HyperLiquidMarket]
    _market_id: Dict[str, str]
    _api_client: HyperLiquidApiClient

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        exchange: HyperLiquidExchangeManager,
        msgbus: MessageBus,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=HyperLiquidWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
            ),
            msgbus=msgbus,
            api_client=HyperLiquidApiClient(
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )

    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        pass

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        pass

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request index klines - not supported by Hyperliquid"""
        raise NotImplementedError("Index klines not supported by Hyperliquid")

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request klines/candlestick data"""
        pass

    async def subscribe_funding_rate(self, symbol: str | List[str]):
        """Subscribe to funding rate - not supported by Hyperliquid"""
        pass

    async def subscribe_index_price(self, symbol: str | List[str]):
        """Subscribe to index price - not supported by Hyperliquid"""
        pass

    async def subscribe_mark_price(self, symbol: str | List[str]):
        """Subscribe to mark price"""
        pass

    async def subscribe_trade(self, symbol: str | List[str]):
        """Subscribe to trade data"""
        pass

    async def subscribe_bookl1(self, symbol: str | List[str]):
        """Subscribe to book level 1 data"""
        pass

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        """Subscribe to book level 2 data"""
        pass

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        """Subscribe to kline data"""
        pass

    def _ws_msg_handler(self, raw: bytes):
        """Handle WebSocket messages"""
        pass

    def _parse_kline_response(
        self, symbol: str, interval: KlineInterval, kline: HyperLiquidKline
    ) -> Kline:
        """Parse kline response from Hyperliquid"""
        pass


class HyperLiquidPrivateConnector(PrivateConnector):
    """Private connector for Hyperliquid exchange"""
    
    _ws_client: HyperLiquidWSClient
    _account_type: HyperLiquidAccountType
    _market: Dict[str, HyperLiquidMarket]
    _market_id: Dict[str, str]
    _api_client: HyperLiquidApiClient

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        exchange: HyperLiquidExchangeManager,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=HyperLiquidWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
            ),
            api_client=HyperLiquidApiClient(
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
                secret=exchange.secret,
                # TODO: remove this after refactor
                # This is used by rest api to sign l1 action
                exchange=exchange,  
            ),
            msgbus=msgbus,
            cache=cache,
            task_manager=task_manager,
        )

    async def _init_account_balance(self):
        """Initialize account balance"""
        pass

    async def _init_position(self):
        """Initialize positions"""
        pass

    async def _position_mode_check(self):
        """Check position mode - not applicable for Hyperliquid"""
        pass

    async def connect(self):
        """Connect to Hyperliquid"""
        pass

    def _ws_msg_handler(self, raw: bytes):
        """Handle WebSocket messages"""
        pass

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        # time_in_force: TimeInForce,
        # position_side: PositionSide,
        **kwargs,
    ) -> Order:
        """Create an order"""
        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        # Convert order parameters to Hyperliquid format
        is_buy = side == OrderSide.BUY
        sz = str(amount)
        limit_px = str(price)
        
        # Convert order type
        order_type_map = {
            OrderType.LIMIT: "Limit",
            OrderType.MARKET: "Market",
            OrderType.POST_ONLY: "PostOnly",
        }
        hl_order_type = order_type_map.get(type, "Limit")
        
        # Place order via API
        response = await self._api_client.place_order(
            user=self._api_client._api_key,
            asset=int(market.id),
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            order_type=hl_order_type,
        )
        
        # Create Order object
        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            status=OrderStatus.PENDING,
            id=str(response.response.data.statuses[0].resting.get("oid", 0)),
            side=side,
            type=type,
            amount=amount,
            price=price,
            time_in_force=TimeInForce.GTC,
            timestamp=self._clock.timestamp_ms(),
        )
        
        return order

    async def cancel_order(self, symbol: str, oid: int, **kwargs) -> Order:
        """Cancel an order"""
        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        response = await self._api_client.cancel_order(
            asset=int(market.id),
            oid=int(oid),
        )
        
        # Create Order object for cancellation
        order = Order(
            exchange=self._exchange_id,
            id=str(oid),
            symbol=symbol,
            status=OrderStatus.CANCELING,
            side=OrderSide.BUY,  # Default, will be updated
            type=OrderType.LIMIT,  # Default, will be updated
            amount=Decimal("0"),
            price=Decimal("0"),
            time_in_force=TimeInForce.GTC,
            timestamp=self._clock.timestamp_ms(),
        )
        
        return order

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders for a symbol"""
        pass

    async def modify_order(
        self,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        """Modify an order - not directly supported by Hyperliquid"""
        pass

    async def create_batch_orders(self, orders: List[BatchOrderSubmit]) -> List[Order]:
        """Create batch orders"""
        pass

    async def create_tp_sl_order(
        self,
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
        """Create take profit and stop loss orders"""
        pass

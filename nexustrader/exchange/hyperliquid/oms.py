import msgspec
from decimal import Decimal
from typing import Dict, List
from nexustrader.error import PositionModeError
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    TriggerType,
    PositionSide,
)
from nexustrader.exchange.hyperliquid.rest_api import HyperLiquidApiClient
from nexustrader.base import OrderManagementSystem
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    Balance,
    Order,
    BatchOrderSubmit,
    Position,
)
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidMarket,
    HyperLiquidWsMessageGeneral,
    HyperLiquidWsOrderUpdatesMsg,
    HyperLiquidWsUserFillsMsg,
    HyperLiquidWsApiGeneralMsg,
    HyperLiquidWsApiOrderData,
    HyperLiquidWsApiMessageData,
    HyperLiquidWsApiOrderStatus,
)
from nexustrader.exchange.hyperliquid.websockets import (
    HyperLiquidWSClient,
    HyperLiquidWSApiClient,
)
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidEnumParser,
    HyperLiquidOrderRequest,
    HyperLiquidCloidCancelRequest,
    HyperLiquidTimeInForce,
)


class HyperLiquidOrderManagementSystem(OrderManagementSystem):
    _ws_client: HyperLiquidWSClient
    _ws_api_client: HyperLiquidWSApiClient
    _account_type: HyperLiquidAccountType
    _market: Dict[str, HyperLiquidMarket]
    _market_id: Dict[str, str]
    _api_client: HyperLiquidApiClient

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        api_key: str,
        secret: str,
        market: Dict[str, HyperLiquidMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: HyperLiquidApiClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        max_slippage: float,
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=HyperLiquidWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                clock=clock,
                task_manager=task_manager,
                api_key=api_key,
            ),
            exchange_id=exchange_id,
            clock=clock,
            msgbus=msgbus,
        )

        self._max_slippage = max_slippage
        self._ws_msg_general_decoder = msgspec.json.Decoder(HyperLiquidWsMessageGeneral)
        self._ws_msg_order_updates_decoder = msgspec.json.Decoder(
            HyperLiquidWsOrderUpdatesMsg
        )
        self._ws_msg_user_events_decoder = msgspec.json.Decoder(
            HyperLiquidWsUserFillsMsg
        )

        # Initialize WebSocket API client
        self._ws_api_client = HyperLiquidWSApiClient(
            account_type=account_type,
            api_key=api_key,
            secret=secret,
            handler=self._ws_api_msg_handler,
            task_manager=task_manager,
            clock=clock,
            enable_rate_limit=True,
        )
        self._ws_api_msg_decoder = msgspec.json.Decoder(HyperLiquidWsApiGeneralMsg)

    def _init_account_balance(self):
        """Initialize the account balance"""
        res = self._api_client.get_user_spot_summary()
        self._cache._apply_balance(
            account_type=self._account_type, balances=res.parse_to_balances()
        )

    def _init_position(self):
        """Initialize the position"""
        res = self._api_client.get_user_perps_summary()
        for pos_data in res.assetPositions:
            if pos_data.type != "oneWay":
                raise PositionModeError(
                    f"HyperLiquid only supports one-way position mode, but got {pos_data.type}"
                )

            symbol = self._market_id.get(pos_data.position.coin, None)
            if not symbol:
                continue

            signed_amount = Decimal(pos_data.position.szi)
            if signed_amount == Decimal("0"):
                continue

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=Decimal(pos_data.position.szi),
                side=PositionSide.LONG
                if signed_amount > Decimal("0")
                else PositionSide.SHORT,
                entry_price=float(pos_data.position.entryPx),
                unrealized_pnl=float(pos_data.position.unrealizedPnl),
            )
            self._cache._apply_position(position)

    def _position_mode_check(self):
        """Check the position mode"""
        # NOTE: HyperLiquid only supports one-way position mode
        pass

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
        raise NotImplementedError

    async def create_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        **kwargs,
    ) -> Order:
        """Create an order"""
        self._registry.register_tmp_order(
            order=Order(
                oid=oid,
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.INITIALIZED,
                amount=amount,
                type=type,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                timestamp=self._clock.timestamp_ms(),
                reduce_only=reduce_only,
            )
        )

        market = self._market.get(symbol)
        if not market:
            raise ValueError(
                f"Market {symbol} not found in exchange {self._exchange_id}"
            )

        if type.is_limit:
            time_in_force = HyperLiquidEnumParser.to_hyperliquid_time_in_force(
                time_in_force
            )
        elif type.is_market:
            time_in_force = HyperLiquidTimeInForce.IOC
            bookl1 = self._cache.bookl1(symbol)
            if not bookl1:
                raise ValueError(
                    "Please subscribe to bookl1 first, Market requires bookl1"
                )
            if side.is_buy:
                price = self._price_to_precision(
                    symbol, bookl1.ask * (1 + self._max_slippage), "ceil"
                )
            else:
                price = self._price_to_precision(
                    symbol, bookl1.bid * (1 - self._max_slippage), "floor"
                )

        elif type.is_post_only:
            time_in_force = HyperLiquidTimeInForce.ALO

        params: HyperLiquidOrderRequest = {
            "a": int(market.baseId),
            "b": side.is_buy,
            "p": str(price),
            "s": str(amount),
            "r": reduce_only,
            "t": {"limit": {"tif": time_in_force.value}},
            "c": oid,  # client order id
        }
        params.update(kwargs)

        try:
            res = await self._api_client.place_orders(orders=[params])
            status = res.response.data.statuses[0]

            if status.error:
                error_msg = status.error
                self._log.error(
                    f"Failed to place order for {symbol}: {error_msg} params: {str(params)}"
                )
                order = Order(
                    exchange=self._exchange_id,
                    oid=oid,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=symbol,
                    type=type,
                    side=side,
                    amount=amount,
                    price=float(price),
                    time_in_force=time_in_force,
                    status=OrderStatus.FAILED,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                )
            else:
                order_status = status.resting or status.filled
                order = Order(
                    oid=oid,
                    eid=str(order_status.oid),
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=symbol,
                    type=type,
                    side=side,
                    amount=amount,
                    price=float(price),
                    time_in_force=time_in_force,
                    status=OrderStatus.PENDING,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                )
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(
                f"Failed to place order for {symbol}: {error_msg} params: {str(params)}"
            )
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price),
                time_in_force=time_in_force,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=reduce_only,
            )
        self.order_status_update(order)

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create a batch of orders"""

        batch_orders: List[HyperLiquidOrderRequest] = []
        for order in orders:
            self._registry.register_tmp_order(
                order=Order(
                    oid=order.oid,
                    exchange=self._exchange_id,
                    symbol=order.symbol,
                    status=OrderStatus.INITIALIZED,
                    amount=order.amount,
                    type=order.type,
                    price=float(order.price) if order.price else None,
                    time_in_force=order.time_in_force,
                    timestamp=self._clock.timestamp_ms(),
                    reduce_only=order.reduce_only,
                )
            )

            market = self._market.get(order.symbol)
            if not market:
                raise ValueError(
                    f"Market {order.symbol} not found in exchange {self._exchange_id}"
                )
            price = order.price
            if order.type.is_limit:
                time_in_force = HyperLiquidEnumParser.to_hyperliquid_time_in_force(
                    order.time_in_force
                )
            elif order.type.is_market:
                time_in_force = HyperLiquidTimeInForce.IOC
                bookl1 = self._cache.bookl1(order.symbol)
                if not bookl1:
                    raise ValueError(
                        "Please subscribe to bookl1 first, Market requires bookl1"
                    )
                if order.side.is_buy:
                    price = self._price_to_precision(
                        order.symbol, bookl1.ask * (1 + self._max_slippage), "ceil"
                    )
                else:
                    price = self._price_to_precision(
                        order.symbol, bookl1.bid * (1 - self._max_slippage), "floor"
                    )

            elif order.type.is_post_only:
                time_in_force = HyperLiquidTimeInForce.ALO

            params: HyperLiquidOrderRequest = {
                "a": int(market.baseId),
                "b": order.side.is_buy,
                "p": str(price),
                "s": str(order.amount),
                "r": order.reduce_only,
                "t": {"limit": {"tif": time_in_force.value}},
                "c": order.oid,  # client order id
            }
            params.update(order.kwargs)
            batch_orders.append(params)

        try:
            res = await self._api_client.place_orders(orders=batch_orders)
            for order, status in zip(orders, res.response.data.statuses):
                if status.error:
                    error_msg = status.error
                    self._log.error(
                        f"Failed to place order for {order.symbol}: {error_msg} params: {str(params)}"
                    )
                    res_batch_order = Order(
                        oid=order.oid,
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price),
                        time_in_force=order.time_in_force,
                        status=OrderStatus.FAILED,
                        filled=Decimal(0),
                        remaining=order.amount,
                        reduce_only=order.reduce_only,
                    )
                else:
                    order_status = status.resting or status.filled
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        eid=str(order_status.oid),
                        oid=order.oid,
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price),
                        time_in_force=order.time_in_force,
                        status=OrderStatus.PENDING,
                        filled=Decimal(0),
                        remaining=order.amount,
                        reduce_only=order.reduce_only,
                    )
                self.order_status_update(res_batch_order)

        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating batch orders: {error_msg}")
            for order in orders:
                order = Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=order.symbol,
                    oid=order.oid,
                    type=order.type,
                    side=order.side,
                    amount=order.amount,
                    price=float(order.price) if order.price else None,
                    time_in_force=order.time_in_force,
                    status=OrderStatus.FAILED,
                    filled=Decimal(0),
                    remaining=order.amount,
                    reduce_only=order.reduce_only,
                )
                self.order_status_update(order)

    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        """Cancel an order"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(
                f"Market {symbol} not found in exchange {self._exchange_id}"
            )

        params: HyperLiquidCloidCancelRequest = {
            "asset": int(market.baseId),
            "cloid": oid,
        }

        try:
            res = await self._api_client.cancel_orders_by_cloid(cancels=[params])
            status = res.response.data.statuses[0]
            if status == "success":
                order = Order(
                    oid=oid,
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=symbol,
                    status=OrderStatus.CANCELING,
                )
            else:
                error_msg = status.error if status.error else "Unknown error"
                self._log.error(
                    f"Failed to cancel order for {symbol}: {error_msg} params: {str(params)}"
                )
                order = Order(
                    oid=oid,
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=symbol,
                    status=OrderStatus.CANCEL_FAILED,
                )
            self.order_status_update(order)
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.CANCEL_FAILED,
            )
            self.order_status_update(order)

    async def modify_order(
        self,
        oid: str,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        """Modify an order"""
        raise NotImplementedError

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders"""
        pass

    async def create_order_ws(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        **kwargs,
    ):
        """Create an order via WebSocket API"""
        self._registry.register_tmp_order(
            order=Order(
                oid=oid,
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.INITIALIZED,
                amount=amount,
                type=type,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                timestamp=self._clock.timestamp_ms(),
                reduce_only=reduce_only,
            )
        )

        market = self._market.get(symbol)
        if not market:
            raise ValueError(
                f"Market {symbol} not found in exchange {self._exchange_id}"
            )

        if type.is_limit:
            time_in_force = HyperLiquidEnumParser.to_hyperliquid_time_in_force(
                time_in_force
            )
        elif type.is_market:
            time_in_force = HyperLiquidTimeInForce.IOC
            bookl1 = self._cache.bookl1(symbol)
            if not bookl1:
                raise ValueError(
                    "Please subscribe to bookl1 first, Market requires bookl1"
                )
            if side.is_buy:
                price = self._price_to_precision(
                    symbol, bookl1.ask * (1 + self._max_slippage), "ceil"
                )
            else:
                price = self._price_to_precision(
                    symbol, bookl1.bid * (1 - self._max_slippage), "floor"
                )
        elif type.is_post_only:
            time_in_force = HyperLiquidTimeInForce.ALO

        params: HyperLiquidOrderRequest = {
            "a": int(market.baseId),
            "b": side.is_buy,
            "p": str(price),
            "s": str(amount),
            "r": reduce_only,
            "t": {"limit": {"tif": time_in_force.value}},
            "c": oid,  # client order id
        }
        params.update(kwargs)

        await self._ws_api_client.place_order(id=oid, orders=[params])

    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(
                f"Market {symbol} not found in exchange {self._exchange_id}"
            )

        params: HyperLiquidCloidCancelRequest = {
            "asset": int(market.baseId),
            "cloid": oid,
        }

        await self._ws_api_client.cancel_orders_by_cloid(id=oid, cancels=[params])

    def _ws_msg_handler(self, raw: bytes):
        """Handle WebSocket messages"""
        try:
            ws_msg: HyperLiquidWsMessageGeneral = self._ws_msg_general_decoder.decode(
                raw
            )
            # if ws_msg.channel == "pong":
            #     self._ws_client._transport.notify_user_specific_pong_received()
            #     self._log.debug("Pong received")
            #     return

            if ws_msg.channel == "orderUpdates":
                self._parse_order_update(raw)
            elif ws_msg.channel == "user":
                self._parse_user_events(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding WebSocket message: {str(raw)} {e}")
            return

    def _ws_api_msg_handler(self, raw: bytes):
        """Handle WebSocket API messages for order operations"""
        try:
            ws_msg: HyperLiquidWsApiGeneralMsg = self._ws_api_msg_decoder.decode(raw)

            # if ws_msg.is_pong:
            #     self._ws_api_client._transport.notify_user_specific_pong_received()
            #     self._log.debug("API Pong received")
            #     return

            if ws_msg.is_order_response and ws_msg.data:
                self._parse_ws_api_response(ws_msg.data)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding WebSocket API message: {str(raw)} {e}")
            return

    def _parse_ws_api_response(self, data: HyperLiquidWsApiMessageData):
        """Parse WebSocket API response and create Order objects"""
        request_id = data.id
        oid = self._ws_api_client._int_to_oid(request_id)
        response = data.response

        if response.payload.status != "ok":
            self._log.error(
                f"WebSocket API error for request {request_id}: {response.payload.status}"
            )
            return

        response_data = response.payload.response
        if response_data.type == "order":
            # Handle order placement response
            order_data: HyperLiquidWsApiOrderData = response_data.data
            for status in order_data.statuses:
                self._create_order_from_ws_response(oid, status)
        elif response_data.type == "cancel":
            # Handle order cancellation response
            cancel_data: HyperLiquidWsApiOrderData = response_data.data
            for status in cancel_data.statuses:
                self._create_cancel_order_from_ws_response(oid, status)

    def _create_order_from_ws_response(
        self, oid: str, status: HyperLiquidWsApiOrderStatus
    ) -> Order | None:
        """Create Order object from WebSocket API order response"""
        temp_order = self._registry.get_tmp_order(oid)
        if not temp_order:
            return

        if status.error:
            self._log.error(f"Order placement failed for {oid}: {status.error}")
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=temp_order.symbol,
                type=temp_order.type,
                side=temp_order.side,
                amount=temp_order.amount,
                price=temp_order.price,
                time_in_force=temp_order.time_in_force,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=temp_order.amount,
                reduce_only=temp_order.reduce_only,
            )
            self.order_status_update(order)
        else:
            eid = None
            if status.filled:
                eid = status.filled.oid
            elif status.resting:
                eid = status.resting.oid

            if eid:
                order = Order(
                    oid=oid,
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    eid=str(eid),
                    symbol=temp_order.symbol,
                    type=temp_order.type,
                    side=temp_order.side,
                    amount=temp_order.amount,
                    price=temp_order.price,
                    time_in_force=temp_order.time_in_force,
                    status=OrderStatus.PENDING,
                    filled=Decimal(0),
                    remaining=temp_order.amount,
                    reduce_only=temp_order.reduce_only,
                )
                self.order_status_update(order)

    def _create_cancel_order_from_ws_response(
        self, oid: str, status: str | HyperLiquidWsApiOrderStatus
    ) -> Order | None:
        """Create Order object from WebSocket API cancel response"""
        temp_order = self._registry.get_tmp_order(oid)
        if not temp_order:
            return

        if isinstance(status, str) and status == "success":
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=temp_order.symbol,
                status=OrderStatus.CANCELING,
            )
        elif isinstance(status, HyperLiquidWsApiOrderStatus):
            self._log.error(f"Order cancellation failed for {oid}: {status.error}")
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=temp_order.symbol,
                status=OrderStatus.CANCEL_FAILED,
            )
        self.order_status_update(order)

    def _parse_user_events(self, raw: bytes):
        user_fills_msg = self._ws_msg_user_events_decoder.decode(raw)
        self._log.debug(f"User fills received: {str(user_fills_msg)}")
        if not user_fills_msg.data.fills:
            return

        fills = user_fills_msg.data.fills
        for fill in fills:
            symbol = self._market_id.get(fill.coin, None)
            if not symbol:
                return

            market = self._market[symbol]
            if market.swap:
                sz = Decimal(fill.sz) if fill.side.is_buy else -Decimal(fill.sz)
                signed_amount = Decimal(fill.startPosition) + sz
                position = Position(
                    symbol=symbol,
                    exchange=self._exchange_id,
                    signed_amount=signed_amount,
                    entry_price=float(
                        fill.px
                    ),  # NOTE: HyperLiquid does not provide entry price in fills, using fill price instead,
                    # I know we can use current position to calculate the entry price, but it costs performance
                    side=PositionSide.LONG
                    if signed_amount > Decimal("0")
                    else PositionSide.SHORT,
                )
                self._cache._apply_position(position)
                self._log.debug(f"Position updated: {str(position)}")
            else:
                current_balance = self._cache.get_balance(
                    account_type=self._account_type
                )

                quote_total = current_balance.balance_total.get(
                    market.quote, Decimal("0")
                )  # zero if not found
                if fill.side.is_buy:
                    base_amount = (
                        Decimal(fill.sz)
                        + Decimal(fill.startPosition)
                        - Decimal(fill.fee)
                    )
                    quote_amount = quote_total - Decimal(fill.px) * Decimal(fill.sz)
                    balances = [
                        Balance(asset=market.baseName, free=base_amount),
                        Balance(asset=market.quote, free=quote_amount),
                    ]

                else:
                    base_amount = Decimal(fill.startPosition) - Decimal(fill.sz)
                    quote_amount = (
                        quote_total
                        + Decimal(fill.px) * Decimal(fill.sz)
                        - Decimal(fill.fee)
                    )

                    balances = [
                        Balance(asset=market.baseName, free=base_amount),
                        Balance(asset=market.quote, free=quote_amount),
                    ]

                self._log.debug(
                    f"\nbase: {market.baseName}, free: {base_amount}\n"
                    f"quote: {market.quote}, free: {quote_amount}"
                )

                self._cache._apply_balance(
                    account_type=self._account_type, balances=balances
                )

    def _parse_order_update(self, raw: bytes):
        order_msg: HyperLiquidWsOrderUpdatesMsg = (
            self._ws_msg_order_updates_decoder.decode(raw)
        )
        self._log.debug(f"Order update received: {str(order_msg)}")

        for data in order_msg.data:
            tmp_order = self._registry.get_tmp_order(data.order.cloid)
            if not tmp_order:
                continue

            id = data.order.coin
            symbol = self._market_id[id]
            order_status = HyperLiquidEnumParser.parse_order_status(data.status)
            order = Order(
                exchange=self._exchange_id,
                eid=str(data.order.oid),
                oid=data.order.cloid,
                symbol=symbol,
                type=tmp_order.type,  # HyperLiquid only have limit orders
                side=OrderSide.BUY if data.order.side.is_buy else OrderSide.SELL,
                amount=Decimal(data.order.origSz),
                price=float(data.order.limitPx),
                average=float(data.order.limitPx),
                status=order_status,
                filled=Decimal(data.order.origSz) - Decimal(data.order.sz),
                remaining=Decimal(data.order.sz),
                timestamp=data.order.timestamp,
                reduce_only=tmp_order.reduce_only,
            )
            self._log.debug(f"Parsed order: {str(order)}")
            self.order_status_update(order)

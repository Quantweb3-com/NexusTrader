import msgspec
from decimal import Decimal
from typing import Dict, List
from nexustrader.error import PositionModeError
from nexustrader.constants import (
    KlineInterval,
    BookLevel,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    TriggerType,
    PositionSide,
)
from nexustrader.core.nautilius_core import (
    MessageBus,
    LiveClock,
)
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    KlineList,
    Ticker,
    Balance,
    BookL1,
    Trade,
    Kline,
    Order,
    BatchOrderSubmit,
    Position,
)
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidMarket,
    HyperLiquidWsMessageGeneral,
    HyperLiquidWsBboMsg,
    HyperLiquidWsTradeMsg,
    HyperLiquidWsCandleMsg,
    HyperLiquidWsOrderUpdatesMsg,
    HyperLiquidWsUserFillsMsg,
)
from nexustrader.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hyperliquid.websockets import HyperLiquidWSClient
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidEnumParser,
    HyperLiquidOrderRequest,
    HyperLiquidOrderCancelRequest,
    HyperLiquidTimeInForce,
)
from nexustrader.exchange.hyperliquid.restapi import HyperLiquidApiClient


class HyperLiquidPublicConnector(PublicConnector):
    _ws_client: HyperLiquidWSClient
    _account_type: HyperLiquidAccountType
    _market: Dict[str, HyperLiquidMarket]

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        exchange: HyperLiquidExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
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
                clock=clock,
                custom_url=custom_url,
            ),
            api_client=HyperLiquidApiClient(
                clock=clock,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            msgbus=msgbus,
            clock=clock,
            task_manager=task_manager,
        )

        self._ws_msg_general_decoder = msgspec.json.Decoder(HyperLiquidWsMessageGeneral)
        self._ws_msg_bbo_decoder = msgspec.json.Decoder(HyperLiquidWsBboMsg)
        self._ws_msg_trade_decoder = msgspec.json.Decoder(HyperLiquidWsTradeMsg)
        self._ws_msg_candle_decoder = msgspec.json.Decoder(HyperLiquidWsCandleMsg)

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request klines"""
        raise NotImplementedError

    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        raise NotImplementedError

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        raise NotImplementedError

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request index klines"""
        raise NotImplementedError

    def _ws_msg_handler(self, raw: bytes):
        try:
            ws_msg: HyperLiquidWsMessageGeneral = self._ws_msg_general_decoder.decode(
                raw
            )
            if ws_msg.channel == "pong":
                self._ws_client._transport.notify_user_specific_pong_received()
                self._log.debug("Pong received")
                return

            if ws_msg.channel == "bbo":
                self._parse_bbo_update(raw)
            elif ws_msg.channel == "trades":
                self._parse_trades_update(raw)
            elif ws_msg.channel == "candle":
                self._parse_candle_update(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Failed to decode WebSocket message: {e}")
            return

    def _parse_candle_update(self, raw: bytes):
        candle_msg: HyperLiquidWsCandleMsg = self._ws_msg_candle_decoder.decode(raw)
        candle_data = candle_msg.data
        id = candle_data.s
        symbol = self._market_id[id]
        interval = HyperLiquidEnumParser.parse_kline_interval(candle_data.i)
        ts = self._clock.timestamp_ms()
        kline = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            start=candle_data.t,
            timestamp=ts,
            open=float(candle_data.o),
            high=float(candle_data.h),
            low=float(candle_data.l),
            close=float(candle_data.c),
            volume=float(candle_data.v),
            interval=interval,
            confirm=False,  # NOTE: you should define how to handle confirmation in HyperLiquid
        )
        self._msgbus.publish(topic="kline", msg=kline)

    def _parse_trades_update(self, raw: bytes):
        trade_msg: HyperLiquidWsTradeMsg = self._ws_msg_trade_decoder.decode(raw)
        for data in trade_msg.data:
            id = data.coin
            symbol = self._market_id[id]
            trade = Trade(
                exchange=self._exchange_id,
                symbol=symbol,
                timestamp=data.time,
                price=float(data.px),
                size=float(data.sz),
            )
            self._msgbus.publish(topic="trade", msg=trade)

    def _parse_bbo_update(self, raw: bytes):
        bbo_msg: HyperLiquidWsBboMsg = self._ws_msg_bbo_decoder.decode(raw)
        id = bbo_msg.data.coin
        symbol = self._market_id[id]
        bid_data = bbo_msg.data.bbo[0]
        ask_data = bbo_msg.data.bbo[1]
        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            timestamp=bbo_msg.data.time,
            bid=float(bid_data.px),
            bid_size=float(bid_data.sz),
            ask=float(ask_data.px),
            ask_size=float(ask_data.sz),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbol = [symbol] if isinstance(symbol, str) else symbol
        symbols = []
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(
                    f"Market {sym} not found in exchange {self._exchange_id}"
                )
            symbols.append(market.baseName if market.swap else market.id)
        await self._ws_client.subscribe_bbo(symbols)

    async def subscribe_trade(self, symbol):
        symbol = [symbol] if isinstance(symbol, str) else symbol
        symbols = []
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(
                    f"Market {sym} not found in exchange {self._exchange_id}"
                )
            symbols.append(market.baseName if market.swap else market.id)
        await self._ws_client.subscribe_trades(symbols)

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        """Subscribe to the kline data"""
        symbol = [symbol] if isinstance(symbol, str) else symbol
        symbols = []
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(
                    f"Market {sym} not found in exchange {self._exchange_id}"
                )
            symbols.append(market.baseName if market.swap else market.id)
        hyper_interval = HyperLiquidEnumParser.to_hyperliquid_kline_interval(interval)
        await self._ws_client.subscribe_candle(symbols, hyper_interval)

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        """Subscribe to the bookl2 data"""
        raise NotImplementedError

    async def subscribe_funding_rate(self, symbol: str | List[str]):
        """Subscribe to the funding rate data"""
        raise NotImplementedError

    async def subscribe_index_price(self, symbol: str | List[str]):
        """Subscribe to the index price data"""
        raise NotImplementedError

    async def subscribe_mark_price(self, symbol: str | List[str]):
        """Subscribe to the mark price data"""
        raise NotImplementedError


class HyperLiquidPrivateConnector(PrivateConnector):
    _api_client: HyperLiquidApiClient
    _ws_client: HyperLiquidWSClient
    _market: Dict[str, HyperLiquidMarket]

    def __init__(
        self,
        exchange: HyperLiquidExchangeManager,
        account_type: HyperLiquidAccountType,
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret:
            raise ValueError(
                "API key and secret must be provided for private connector"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=HyperLiquidWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                clock=clock,
                task_manager=task_manager,
                api_key=exchange.api_key,
            ),
            api_client=HyperLiquidApiClient(
                clock=clock,
                api_key=exchange.api_key,
                secret=exchange.secret,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            msgbus=msgbus,
            clock=clock,
            cache=cache,
            task_manager=task_manager,
            max_slippage=kwargs.get("max_slippage", 0.02),  # 2% slippage
        )

        self._ws_msg_general_decoder = msgspec.json.Decoder(HyperLiquidWsMessageGeneral)
        self._ws_msg_order_updates_decoder = msgspec.json.Decoder(
            HyperLiquidWsOrderUpdatesMsg
        )
        self._ws_msg_user_events_decoder = msgspec.json.Decoder(
            HyperLiquidWsUserFillsMsg
        )

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
                return Order(
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
            order_status = status.resting or status.filled
            return Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                id=str(order_status.oid),
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
            return Order(
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

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create a batch of orders"""

        batch_orders: List[HyperLiquidOrderRequest] = []
        for order in orders:
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
            }
            params.update(order.kwargs)
            batch_orders.append(params)

        try:
            res = await self._api_client.place_orders(orders=batch_orders)

            res_batch_orders = []
            for order, status in zip(orders, res.response.data.statuses):
                if status.error:
                    error_msg = status.error
                    self._log.error(
                        f"Failed to place order for {order.symbol}: {error_msg} params: {str(params)}"
                    )
                    res_batch_order = Order(
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
                    order = Order(
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        id=str(order_status.oid),
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
                res_batch_orders.append(res_batch_order)
            return res_batch_orders

        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating batch orders: {error_msg}")
            res_batch_orders = [
                Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=order.symbol,
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
                for order in orders
            ]
            return res_batch_orders

    async def cancel_order(self, symbol: str, order_id: str, **kwargs) -> Order:
        """Cancel an order"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(
                f"Market {symbol} not found in exchange {self._exchange_id}"
            )

        params: HyperLiquidOrderCancelRequest = {
            "a": int(market.baseId),
            "o": int(order_id),
        }

        try:
            res = await self._api_client.cancel_orders(cancels=[params])
            status = res.response.data.statuses[0]
            if status == "success":
                return Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    id=order_id,
                    symbol=symbol,
                    status=OrderStatus.CANCELING,
                )
            else:
                error_msg = status.error if status.error else "Unknown error"
                self._log.error(
                    f"Failed to cancel order for {symbol}: {error_msg} params: {str(params)}"
                )
                return Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    id=order_id,
                    symbol=symbol,
                    status=OrderStatus.CANCEL_FAILED,
                )

        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            return Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                id=order_id,
                symbol=symbol,
                status=OrderStatus.CANCEL_FAILED,
            )

    async def modify_order(
        self,
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

    async def connect(self):
        """Connect to the exchange"""
        await self._ws_client.subscribe_order_updates()
        await self._ws_client.subscribe_user_events()

    def _ws_msg_handler(self, raw: bytes):
        """Handle WebSocket messages"""
        try:
            ws_msg: HyperLiquidWsMessageGeneral = self._ws_msg_general_decoder.decode(
                raw
            )
            if ws_msg.channel == "pong":
                self._ws_client._transport.notify_user_specific_pong_received()
                self._log.debug("Pong received")
                return

            if ws_msg.channel == "orderUpdates":
                self._parse_order_update(raw)
            elif ws_msg.channel == "user":
                self._parse_user_events(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding WebSocket message: {str(raw)} {e}")
            return

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
            id = data.order.coin
            symbol = self._market_id[id]
            order_status = HyperLiquidEnumParser.parse_order_status(data.status)
            order = Order(
                exchange=self._exchange_id,
                id=str(data.order.oid),
                symbol=symbol,
                type=OrderType.LIMIT,  # HyperLiquid only have limit orders
                side=OrderSide.BUY if data.order.side.is_buy else OrderSide.SELL,
                amount=Decimal(data.order.origSz),
                price=float(data.order.limitPx),
                average=float(data.order.limitPx),
                status=order_status,
                filled=Decimal(data.order.origSz) - Decimal(data.order.sz),
                remaining=Decimal(data.order.sz),
                timestamp=data.order.timestamp,
                client_order_id=data.order.cloid,
            )
            self._log.debug(f"Parsed order: {str(order)}")
            self._msgbus.send(endpoint="hyper.order", msg=order)

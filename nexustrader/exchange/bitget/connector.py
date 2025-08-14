import msgspec

# import asyncio
from typing import Dict, List
from decimal import Decimal
from nexustrader.error import PositionModeError
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    BookL1,
    Order,
    Trade,
    Position,
    Kline,
    # BookL2,
    # BookOrderData,
    # FundingRate,
    # IndexPrice,
    # MarkPrice,
    KlineList,
    BatchOrderSubmit,
    Ticker,
)
from nexustrader.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    KlineInterval,
    TriggerType,
    BookLevel,
)
from nexustrader.exchange.bitget.schema import (
    BitgetMarket,
    BitgetWsGeneralMsg,
    BitgetWsUtaGeneralMsg,
    BitgetWsUtaArgMsg,
    BitgetBooks1WsMsg,
    BitgetWsArgMsg,
    BitgetWsTradeWsMsg,
    BitgetWsCandleWsMsg,
    BitgetOrderWsMsg,
    BitgetPositionWsMsg,
    BitgetUtaOrderWsMsg,
    BitgetUtaPositionWsMsg,
    BitgetSpotAccountWsMsg,
    BitgetFuturesAccountWsMsg,
    BitgetUtaAccountWsMsg,
)
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
from nexustrader.exchange.bitget.websockets import BitgetWSClient
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetKlineInterval,
    BitgetInstType,
    BitgetUtaInstType,
    BitgetEnumParser,
    BitgetPositionSide,
)
from nexustrader.exchange.bitget.exchange import BitgetExchangeManager


class BitgetPublicConnector(PublicConnector):
    _inst_type_map = {
        BitgetUtaInstType.SPOT: "spot",
        BitgetUtaInstType.USDC_FUTURES: "linear",
        BitgetUtaInstType.USDT_FUTURES: "linear",
        BitgetUtaInstType.COIN_FUTURES: "inverse",
    }
    _api_client: BitgetApiClient
    _ws_client: BitgetWSClient
    _account_type: BitgetAccountType

    def __init__(
        self,
        account_type: BitgetAccountType,
        exchange: BitgetExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
    ):
        if not account_type.is_uta:
            raise ValueError(
                "Public connector only supports UTA account type."
                "Please set `account_type` to `BitgetAccountType.UTA` or `BitgetAccountType.UTA_DEMO`."
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BitgetWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                clock=clock,
                task_manager=task_manager,
                custom_url=custom_url,
            ),
            clock=clock,
            msgbus=msgbus,
            api_client=BitgetApiClient(
                clock=clock,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )
        self._testnet = account_type.is_testnet
        self._ws_msg_general_decoder = msgspec.json.Decoder(BitgetWsUtaGeneralMsg)
        self._ws_books1_decoder = msgspec.json.Decoder(BitgetBooks1WsMsg)
        self._ws_trade_decoder = msgspec.json.Decoder(BitgetWsTradeWsMsg)
        self._ws_candle_decoder = msgspec.json.Decoder(BitgetWsCandleWsMsg)

    def _get_inst_type(self, market: BitgetMarket):
        if market.spot:
            return "spot"
        elif market.linear:
            return "usdt-futures" if market.quote == "USDT" else "usdc-futures"
        elif market.inverse:
            return "coin-futures"

    def _inst_type_suffix(self, inst_type: BitgetUtaInstType):
        return self._inst_type_map[inst_type]

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
        """Handle incoming WebSocket messages"""
        # Process the message based on its type
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return

        try:
            msg = self._ws_msg_general_decoder.decode(raw)
            if msg.is_event_data:
                self._handle_event_data(msg)
            elif msg.arg.topic == "books1":
                self._handle_books1_data(raw, msg.arg)
            elif msg.arg.topic == "publicTrade":
                self._handle_trade_data(raw, msg.arg)
            elif msg.arg.topic == "kline":
                self._handle_candle_data(raw, msg.arg)

            # print(f"Received WebSocket message: {raw}")
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_event_data(self, msg: BitgetWsUtaGeneralMsg):
        if msg.event == "subscribe":
            arg = msg.arg
            self._log.debug(f"Subscribed to {arg.message}")
        elif msg.event == "error":
            code = msg.code
            error_msg = msg.msg
            self._log.error(f"Subscribed error code={code} {error_msg}")

    def _handle_candle_data(self, raw: bytes, arg: BitgetWsUtaArgMsg):
        msg = self._ws_candle_decoder.decode(raw)
        self._log.debug(f"Received kline data: {str(msg)}")
        sym_id = f"{arg.symbol}_{self._inst_type_suffix(arg.instType)}"
        symbol = self._market_id[sym_id]
        interval = BitgetEnumParser.parse_kline_interval(
            BitgetKlineInterval(arg.interval)
        )
        for data in msg.data:
            kline = Kline(
                exchange=self._exchange_id,
                symbol=symbol,
                open=float(data.open),
                high=float(data.high),
                low=float(data.low),
                close=float(data.close),
                volume=float(data.volume),
                quote_volume=float(data.turnover),
                start=int(data.start),
                timestamp=self._clock.timestamp_ms(),
                interval=interval,
                confirm=False,  # NOTE: need to handle confirm yourself
            )
            self._msgbus.publish(topic="kline", msg=kline)
            # self._log.debug(f"Kline update: {str(kline)}")

    def _handle_trade_data(self, raw: bytes, arg: BitgetWsUtaArgMsg):
        msg = self._ws_trade_decoder.decode(raw)
        sym_id = f"{arg.symbol}_{self._inst_type_suffix(arg.instType)}"
        for data in msg.data:
            trade = Trade(
                exchange=self._exchange_id,
                symbol=self._market_id[sym_id],
                price=float(data.p),
                size=float(data.v),
                timestamp=int(data.T),
            )
            self._msgbus.publish(topic="trade", msg=trade)
            # self._log.debug(f"Trade update: {str(trade)}")

    def _handle_books1_data(self, raw: bytes, arg: BitgetWsUtaArgMsg):
        msg = self._ws_books1_decoder.decode(raw)
        sym_id = f"{arg.symbol}_{self._inst_type_suffix(arg.instType)}"
        symbol = self._market_id[sym_id]
        for data in msg.data:
            bids = data.b[0]
            asks = data.a[0]
            bookl1 = BookL1(
                exchange=self._exchange_id,
                symbol=symbol,
                bid=float(bids.px),
                bid_size=float(bids.sz),
                ask=float(asks.px),
                ask_size=float(asks.sz),
                timestamp=int(data.ts),
            )
            self._msgbus.publish(topic="bookl1", msg=bookl1)
            # self._log.debug(f"BookL1 update: {str(bookl1)}")

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        symbol = symbol if isinstance(symbol, list) else [symbol]
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(f"Symbol {sym} not found in market data.")
            symbols.append(market.id)
            inst_type = self._get_inst_type(market)
        await self._ws_client.subscribe_depth_v3(symbols, inst_type, "books1")

    async def subscribe_trade(self, symbol):
        symbols = []
        symbol = symbol if isinstance(symbol, list) else [symbol]
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(f"Symbol {sym} not found in market data.")
            symbols.append(market.id)
            inst_type = self._get_inst_type(market)
        await self._ws_client.subscribe_trades_v3(symbols, inst_type)

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        """Subscribe to the kline data"""
        symbols = []
        symbol = symbol if isinstance(symbol, list) else [symbol]
        bitget_interval = BitgetEnumParser.to_bitget_kline_interval(interval)
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(f"Symbol {sym} not found in market data.")
            symbols.append(market.id)
            inst_type = self._get_inst_type(market)
        await self._ws_client.subscribe_candlestick_v3(
            symbols, inst_type, bitget_interval
        )

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


class BitgetPrivateConnector(PrivateConnector):
    _inst_type_map = {
        BitgetInstType.SPOT: "spot",
        BitgetInstType.USDC_FUTURES: "linear",
        BitgetInstType.USDT_FUTURES: "linear",
        BitgetInstType.COIN_FUTURES: "inverse",
    }
    _uta_inst_type_map = {
        BitgetUtaInstType.SPOT: "spot",
        BitgetUtaInstType.USDC_FUTURES: "linear",
        BitgetUtaInstType.USDT_FUTURES: "linear",
        BitgetUtaInstType.COIN_FUTURES: "inverse",
    }
    _ws_client: BitgetWSClient
    _account_type: BitgetAccountType
    _market: Dict[str, BitgetMarket]
    _market_id: Dict[str, str]
    _api_client: BitgetApiClient

    def __init__(
        self,
        exchange: BitgetExchangeManager,
        account_type: BitgetAccountType,
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret or not exchange.passphrase:
            raise ValueError(
                "ApiKey, Secret and Passphrase must be provided for private connector."
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BitgetWSClient(
                account_type=account_type,
                handler=self._ws_uta_msg_handler
                if account_type.is_uta
                else self._ws_msg_handler,
                clock=clock,
                task_manager=task_manager,
                api_key=exchange.api_key,
                secret=exchange.secret,
                passphrase=exchange.passphrase,
            ),
            api_client=BitgetApiClient(
                clock=clock,
                api_key=exchange.api_key,
                secret=exchange.secret,
                passphrase=exchange.passphrase,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
                **kwargs,
            ),
            msgbus=msgbus,
            clock=clock,
            cache=cache,
            task_manager=task_manager,
            max_slippage=kwargs.get("max_slippage", 0.02),  # Default to 2% slippage
        )

        self._ws_msg_general_decoder = msgspec.json.Decoder(BitgetWsGeneralMsg)
        self._ws_msg_uta_general_decoder = msgspec.json.Decoder(BitgetWsUtaGeneralMsg)
        self._ws_msg_orders_decoder = msgspec.json.Decoder(BitgetOrderWsMsg)
        self._ws_msg_uta_orders_decoder = msgspec.json.Decoder(BitgetUtaOrderWsMsg)
        self._ws_msg_positions_decoder = msgspec.json.Decoder(BitgetPositionWsMsg)
        self._ws_msg_uta_positions_decoder = msgspec.json.Decoder(
            BitgetUtaPositionWsMsg
        )

        self._ws_msg_spot_account_decoder = msgspec.json.Decoder(BitgetSpotAccountWsMsg)
        self._ws_msg_futures_account_decoder = msgspec.json.Decoder(
            BitgetFuturesAccountWsMsg
        )
        self._ws_msg_uta_account_decoder = msgspec.json.Decoder(BitgetUtaAccountWsMsg)

    def _inst_type_suffix(self, inst_type: BitgetInstType):
        return self._inst_type_map[inst_type]

    def _uta_inst_type_suffix(self, category: BitgetUtaInstType) -> str:
        """Convert UTA category to internal suffix"""
        return self._uta_inst_type_map[category]

    def _get_inst_type(self, market: BitgetMarket):
        if market.spot:
            return "SPOT"
        elif market.linear:
            return "USDT-FUTURES" if market.quote == "USDT" else "USDC-FUTURES"
        elif market.inverse:
            return "COIN-FUTURES"

    def _init_account_balance(self):
        """Initialize account balance"""
        pass

    def _init_position(self):
        """Initialize position"""
        # Bitget has different product types for different instrument types

        if self._account_type.is_uta:
            pass
        else:
            product_types = ["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]

            for product_type in product_types:
                # Get all positions for this product type
                response = self._api_client.get_api_v2_mix_position_all_position(
                    productType=product_type
                )

                for pos_data in response.data:
                    # Check position mode - only support one-way mode
                    if pos_data.posMode != "one_way_mode":
                        raise PositionModeError(
                            f"Only one-way position mode is supported. Current mode: {pos_data.posMode}"
                        )

                    # Skip positions with zero amount
                    if float(pos_data.total) == 0:
                        continue

                    # Map symbol from Bitget format to our internal format
                    inst_type = BitgetInstType(product_type)
                    inst_type_suffix = self._inst_type_suffix(inst_type)
                    symbol = self._market_id.get(
                        f"{pos_data.symbol}_{inst_type_suffix}"
                    )

                    if not symbol:
                        self._log.warning(
                            f"Symbol {pos_data.symbol} not found in market mapping"
                        )
                        continue

                    # Convert holdSide string to BitgetPositionSide enum
                    hold_side = BitgetPositionSide(pos_data.holdSide)

                    # Convert to signed amount based on position side
                    signed_amount = Decimal(pos_data.total)
                    if hold_side == BitgetPositionSide.SHORT:
                        signed_amount = -signed_amount

                    # Parse position side
                    position_side = hold_side.parse_to_position_side()

                    # Create Position object
                    position = Position(
                        symbol=symbol,
                        exchange=self._exchange_id,
                        signed_amount=signed_amount,
                        entry_price=float(pos_data.openPriceAvg),
                        side=position_side,
                        unrealized_pnl=float(pos_data.unrealizedPL),
                        realized_pnl=float(pos_data.achievedProfits),
                    )

                    # Apply position to cache
                    self._cache._apply_position(position)
                    self._log.debug(f"Initialized position: {str(position)}")

    def _position_mode_check(self):
        """Check the position mode"""
        # Position mode check is performed in _init_position for each position
        # Only one-way mode is supported
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
            raise ValueError(f"Symbol {symbol} not found in market data.")

        if self._account_type.is_uta:
            category = kwargs.pop("category", self._get_inst_type(market))
            params = {
                "category": category,
                "symbol": market.id,
                "qty": str(amount),
            }
            if type.is_limit:
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["timeInForce"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            if reduce_only:
                params["reduceOnly"] = "yes"

            params.update(kwargs)

            try:
                res = await self._api_client.post_api_v3_trade_place_order(**params)

                return Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    id=str(res.data.orderId),
                    client_order_id=str(res.data.clientOid),
                    status=OrderStatus.PENDING,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=res.requestTime,
                )

            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(
                    f"Error creating order: {error_msg} params: {str(params)}"
                )
                return Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    status=OrderStatus.FAILED,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=self._clock.timestamp_ms(),
                )

        else:
            params = {
                "symbol": market.id,
                "side": BitgetEnumParser.to_bitget_order_side(side).value,
                "size": str(amount),
            }
            if type.is_limit:
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["force"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            params.update(kwargs)

            try:
                if market.swap:
                    params["marginCoin"] = market.quote
                    params["marginMode"] = kwargs.get("marginMode", "crossed")
                    params["productType"] = self._get_inst_type(market)
                    if reduce_only:
                        params["reduceOnly"] = "YES"

                    res = await self._api_client.post_api_v2_mix_order_place_order(
                        **params
                    )
                else:
                    res = await self._api_client.post_api_v2_spot_trade_place_order(
                        **params
                    )

                return Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    id=str(res.data.orderId),
                    client_order_id=str(res.data.clientOid),
                    status=OrderStatus.PENDING,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=res.requestTime,
                )

            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(
                    f"Error creating order: {error_msg} params: {str(params)}"
                )
                return Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    status=OrderStatus.FAILED,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=self._clock.timestamp_ms(),
                )

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create multiple orders in a batch"""
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str, **kwargs) -> Order:
        """Cancel an order"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id
        params = {
            "symbol": id,
            "orderId": order_id,
        }
        params.update(kwargs)
        try:
            if self._account_type.is_uta:
                res = await self._api_client.post_api_v3_trade_cancel_order(
                    orderId=order_id,
                    clientOid=kwargs.get("clientOid", None),
                )

            else:
                if market.swap:
                    params["productType"] = self._get_inst_type(market)
                    res = await self._api_client.post_api_v2_mix_order_cancel_order(
                        **params
                    )
                else:
                    res = await self._api_client.post_api_v2_spot_trade_cancel_order(
                        **params
                    )
            return Order(
                exchange=self._exchange_id,
                id=res.data.orderId,
                client_order_id=res.data.clientOid,
                timestamp=res.requestTime,
                symbol=symbol,
                status=OrderStatus.CANCELING,
            )
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            return Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
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
        if self._account_type.is_uta:
            await self._ws_client.subscribe_v3_order()
            await self._ws_client.subscribe_v3_position()
            await self._ws_client.subscribe_v3_account()
        elif self._account_type.is_future:
            await self._ws_client.subscribe_orders(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
            await self._ws_client.subscribe_positions(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
            await self._ws_client.subscribe_account(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
        elif self._account_type.is_spot:
            await self._ws_client.subscribe_orders(inst_types=["SPOT"])
            await self._ws_client.subscribe_account(inst_types=["SPOT"])

    def _ws_uta_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return
        try:
            ws_msg = self._ws_msg_uta_general_decoder.decode(raw)
            if ws_msg.is_event_data:
                self._handle_event_data(ws_msg)
            elif ws_msg.arg.topic == "order":
                self._handle_uta_order_event(raw)
            elif ws_msg.arg.topic == "position":
                self._handle_uta_position_event(raw)
            elif ws_msg.arg.topic == "account":
                self._handle_uta_account_event(raw)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_uta_account_event(self, raw: bytes):
        msg = self._ws_msg_uta_account_decoder.decode(raw)
        balances = msg.parse_to_balances()
        self._cache._apply_balance(
            account_type=self._account_type,
            balances=balances,
        )
        for balance in balances:
            self._log.debug(
                f"Balance update: {balance.asset} - {balance.free} free, {balance.locked} locked"
            )

    def _handle_uta_position_event(self, raw: bytes):
        msg = self._ws_msg_uta_positions_decoder.decode(raw)
        for data in msg.data:
            # Determine suffix based on marginCoin
            if data.marginCoin in ["USDT", "USDC"]:
                suffix = "linear"
            else:
                suffix = "inverse"

            sym_id = f"{data.symbol}_{suffix}"
            symbol = self._market_id.get(sym_id)

            if not symbol:
                self._log.warning(f"Symbol not found for UTA position: {sym_id}")
                continue

            # Parse position side
            position_side = data.posSide.parse_to_position_side()
            signed_amount = Decimal(data.size)
            if position_side.is_short:
                signed_amount = -signed_amount

            # Create Position object
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                entry_price=float(data.openPriceAvg or 0.0),
                side=position_side,
                unrealized_pnl=float(data.unrealisedPnl or 0.0),
                realized_pnl=float(data.curRealisedPnl or 0.0),
            )

            # Apply position to cache
            self._cache._apply_position(position)
            self._log.debug(f"Position update: {str(position)}")

    def _handle_uta_order_event(self, raw: bytes):
        msg = self._ws_msg_uta_orders_decoder.decode(raw)
        for data in msg.data:
            status = BitgetEnumParser.parse_order_status(data.orderStatus)
            if not status:
                continue
            # Build symbol ID using the helper method
            inst_type_suffix = self._uta_inst_type_suffix(data.category)
            sym_id = f"{data.symbol}_{inst_type_suffix}"

            symbol = self._market_id.get(sym_id)
            if not symbol:
                self._log.warning(f"Symbol not found for {sym_id}")
                continue

            # Parse order data
            timestamp = int(data.updatedTime)

            # Parse order type
            if data.orderType.is_market:
                order_type = OrderType.MARKET
            elif data.timeInForce.is_post_only:
                order_type = OrderType.POST_ONLY
            else:
                order_type = OrderType.LIMIT  # Default fallback

            # Calculate remaining quantity
            remaining = Decimal(data.qty) - Decimal(data.cumExecQty)

            # Calculate average price
            average_price = data.avgPrice or 0
            price = data.price or 0

            # Calculate fee
            total_fee = Decimal(0)
            fee_currency = None
            if data.feeDetail:
                total_fee = sum(Decimal(fee.fee) for fee in data.feeDetail)
                if data.feeDetail:
                    fee_currency = data.feeDetail[0].feeCoin

            order = Order(
                exchange=self._exchange_id,
                id=data.orderId,
                client_order_id=data.clientOid,
                timestamp=timestamp,
                symbol=symbol,
                type=order_type,
                side=BitgetEnumParser.parse_order_side(data.side),
                price=price,
                average=average_price,
                amount=Decimal(data.qty),
                filled=Decimal(data.cumExecQty),
                remaining=remaining,
                status=status,
                fee=total_fee,
                fee_currency=fee_currency,
                cum_cost=Decimal(data.cumExecValue or 0),
                reduce_only=data.reduceOnly == "yes",
            )
            self._log.debug(f"Order update: {str(order)}")
            self._msgbus.send(endpoint="bitget.order", msg=order)

    def _ws_msg_handler(self, raw: bytes):
        """Handle incoming WebSocket messages"""
        # Process the message based on its type
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return

        try:
            ws_msg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.is_event_data:
                self._handle_event_data(ws_msg)
            elif ws_msg.arg.channel == "orders":
                self._handle_orders_event(raw, ws_msg.arg)
            elif ws_msg.arg.channel == "positions":
                self._handle_positions_event(raw, ws_msg.arg)
            elif ws_msg.arg.channel == "account":
                self._handle_account_event(raw, ws_msg.arg)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_account_event(self, raw: bytes, arg: BitgetWsArgMsg):
        if arg.instType.is_spot:
            msg = self._ws_msg_spot_account_decoder.decode(raw)
        else:
            msg = self._ws_msg_futures_account_decoder.decode(raw)
        self._cache._apply_balance(
            account_type=self._account_type, balances=msg.parse_to_balances()
        )

    def _handle_positions_event(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_msg_positions_decoder.decode(raw)

        # Get existing positions for this specific instrument type
        existing_positions = self._cache.get_all_positions(exchange=self._exchange_id)
        inst_type_suffix = self._inst_type_suffix(arg.instType)

        # Filter existing positions to only include those from this instrument type
        if arg.instType.is_usdt_swap:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].quote == "USDT"
            }
        elif arg.instType.is_usdc_swap:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].quote == "USDC"
            }
        elif arg.instType.is_inverse:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].inverse
            }

        active_symbols = set()

        for data in msg.data:
            sym_id = data.instId
            symbol = self._market_id[f"{sym_id}_{inst_type_suffix}"]
            active_symbols.add(symbol)

            # Convert Bitget position data to Position
            signed_amount = Decimal(data.total)
            if data.holdSide.is_short:
                signed_amount = -signed_amount

            position_side = data.holdSide.parse_to_position_side()

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                entry_price=float(data.openPriceAvg),
                side=position_side,
                unrealized_pnl=float(data.unrealizedPL),
                realized_pnl=float(data.achievedProfits),
            )

            self._cache._apply_position(position)
            self._log.debug(f"Position update: {str(position)}")

        # Close positions that are not in the snapshot (position goes to 0)
        # Only check positions for the current instrument type
        for symbol, existing_position in existing_positions_for_inst_type.items():
            if symbol not in active_symbols:
                # Create a closed position with signed_amount = 0
                closed_position = Position(
                    symbol=symbol,
                    exchange=self._exchange_id,
                    signed_amount=Decimal("0"),
                    entry_price=existing_position.entry_price,
                    side=None,
                    unrealized_pnl=0,
                    realized_pnl=existing_position.realized_pnl,
                )
                self._cache._apply_position(closed_position)
                self._log.debug(f"Position closed: {str(closed_position)}")

    def _handle_event_data(self, msg: BitgetWsGeneralMsg | BitgetWsUtaGeneralMsg):
        if msg.event == "subscribe":
            arg = msg.arg
            self._log.debug(f"Subscribed to {arg.message}")
        elif msg.event == "error":
            code = msg.code
            error_msg = msg.msg
            self._log.error(f"Subscribed error code={code} {error_msg}")
        elif msg.event == "login":
            if msg.code == 0:
                self._log.debug("WebSocket login successful")
            else:
                self._log.error(f"WebSocket login failed: {msg.msg}")

    def _handle_orders_event(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_msg_orders_decoder.decode(raw)
        for data in msg.data:
            sym_id = data.instId
            timestamp = int(data.uTime)
            if data.orderType.is_market:
                typ = OrderType.MARKET
            elif data.force.is_post_only:
                typ = OrderType.POST_ONLY
            else:
                typ = OrderType.LIMIT

            status = BitgetEnumParser.parse_order_status(data.status)
            side = BitgetEnumParser.parse_order_side(data.side)

            if fee_details := data.feeDetail:
                fee = fee_details[0].fee
                fee_currency = fee_details[0].feeCoin
            else:
                fee = 0
                fee_currency = None
            filled = data.accBaseVolume
            last_filled = data.accBaseVolume or 0
            last_filled_price = data.fillPrice or 0
            price = data.price or 0
            average = data.priceAvg or 0

            if arg.instType.is_spot:
                symbol = self._market_id[f"{sym_id}_spot"]
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    id=str(data.orderId),
                    client_order_id=str(data.clientOid),
                    amount=Decimal(data.newSize),
                    filled=Decimal(filled),
                    timestamp=timestamp,
                    status=status,
                    side=side,
                    type=typ,
                    last_filled=Decimal(last_filled),
                    last_filled_price=float(last_filled_price),
                    remaining=Decimal(data.newSize) - Decimal(data.accBaseVolume),
                    fee=Decimal(fee),
                    fee_currency=fee_currency,
                    price=float(price),
                    average=float(average),
                    cost=Decimal(last_filled) * Decimal(last_filled_price),
                    cum_cost=Decimal(filled) * Decimal(average),
                )
            else:
                symbol = self._market_id[
                    f"{sym_id}_{self._inst_type_suffix(arg.instType)}"
                ]
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    id=str(data.orderId),
                    client_order_id=str(data.clientOid),
                    amount=Decimal(data.size),
                    filled=Decimal(filled),
                    timestamp=timestamp,
                    status=status,
                    side=side,
                    type=typ,
                    last_filled=Decimal(last_filled),
                    last_filled_price=float(last_filled_price),
                    remaining=Decimal(data.size) - Decimal(data.accBaseVolume),
                    fee=Decimal(fee),
                    fee_currency=fee_currency,
                    average=float(average),
                    price=float(price),
                    cost=Decimal(last_filled) * Decimal(last_filled_price),
                    cum_cost=Decimal(filled) * Decimal(average),
                    reduce_only=data.reduceOnly == "yes",
                )
            self._log.debug(f"Order update: {str(order)}")
            self._msgbus.send(endpoint="bitget.order", msg=order)


# async def main():
#     from nexustrader.constants import settings

#     API_KEY = settings.BITGET.DEMO1.API_KEY
#     SECRET = settings.BITGET.DEMO1.SECRET
#     PASSPHRASE = settings.BITGET.DEMO1.PASSPHRASE
#     exchange = BitgetExchangeManager(
#         config={
#             "apiKey": API_KEY,
#             "secret": SECRET,
#             "password": PASSPHRASE,
#         }
#     )
#     logguard, msgbus, clock = setup_nautilus_core("test-001", level_stdout="DEBUG")
#     task_manager = TaskManager(
#         loop=asyncio.get_event_loop(),
#     )
#     private_connector = BitgetPrivateConnector(
#         exchange=exchange,
#         account_type=BitgetAccountType.UTA_DEMO,
#         cache=AsyncCache(
#             strategy_id="bitget_test",
#             user_id="test_user",
#             msgbus=msgbus,
#             clock=clock,
#             task_manager=task_manager,
#         ),
#         msgbus=msgbus,
#         clock=clock,
#         task_manager=task_manager,
#         enable_rate_limit=True,
#     )
#     await private_connector.connect()

#     public_connector = BitgetPublicConnector(
#         account_type=BitgetAccountType.UTA,
#         exchange=exchange,
#         msgbus=msgbus,
#         clock=clock,
#         task_manager=task_manager,
#     )
#     await public_connector.subscribe_kline("BTCUSDT-PERP.BITGET", interval=KlineInterval.MINUTE_1)

#     await task_manager.wait()


# if __name__ == "__main__":
#     asyncio.run(main())

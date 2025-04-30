import msgspec
from typing import Dict, List
from decimal import Decimal
from collections import defaultdict
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager, RateLimit
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import BookL1, Order, Trade, Position, Kline, BookL2, BookOrderData
from nexustrader.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    PositionSide,
    KlineInterval,
    TriggerType,
    BookLevel,
)
from nexustrader.exchange.bybit.schema import (
    BybitWsMessageGeneral,
    BybitWsOrderMsg,
    BybitWsOrderbookDepthMsg,
    BybitOrderBook,
    BybitMarket,
    BybitWsTradeMsg,
    BybitWsPositionMsg,
    BybitWsAccountWalletMsg,
    BybitWsKlineMsg,
    BybitWalletBalanceResponse,
    BybitPositionResponse,
)
from nexustrader.exchange.bybit.rest_api import BybitApiClient
from nexustrader.exchange.bybit.websockets import BybitWSClient
from nexustrader.exchange.bybit.constants import (
    BybitAccountType,
    BybitEnumParser,
)
from nexustrader.exchange.bybit.exchange import BybitExchangeManager


class BybitPublicConnector(PublicConnector):
    _ws_client: BybitWSClient
    _account_type: BybitAccountType

    def __init__(
        self,
        account_type: BybitAccountType,
        exchange: BybitExchangeManager,
        msgbus: MessageBus,
        task_manager: TaskManager,
        rate_limit: RateLimit | None = None,
        custom_url: str | None = None,
    ):
        if account_type in {BybitAccountType.UNIFIED, BybitAccountType.UNIFIED_TESTNET}:
            raise ValueError(
                "Please not using `BybitAccountType.UNIFIED` or `BybitAccountType.UNIFIED_TESTNET` in `PublicConnector`"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BybitWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                custom_url=custom_url,
            ),
            msgbus=msgbus,
            api_client=BybitApiClient(
                testnet=account_type.is_testnet,
            ),
            task_manager=task_manager,
            rate_limit=rate_limit,
        )
        self._ws_msg_trade_decoder = msgspec.json.Decoder(BybitWsTradeMsg)
        self._ws_msg_orderbook_decoder = msgspec.json.Decoder(BybitWsOrderbookDepthMsg)
        self._ws_msg_general_decoder = msgspec.json.Decoder(BybitWsMessageGeneral)
        self._ws_msg_kline_decoder = msgspec.json.Decoder(BybitWsKlineMsg)
        self._orderbook = defaultdict(BybitOrderBook)

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"
        else:
            raise ValueError(f"Unsupported BybitAccountType.{self._account_type.value}")

    def _ws_msg_handler(self, raw: bytes):
        try:
            ws_msg: BybitWsMessageGeneral = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.ret_msg == "pong":
                self._ws_client._transport.notify_user_specific_pong_received()
                self._log.debug(f"Pong received {str(ws_msg)}")
                return
            if ws_msg.success is False:
                self._log.error(f"WebSocket error: {ws_msg}")
                return

            if "orderbook.1" in ws_msg.topic:
                self._handle_orderbook(raw)
            elif "orderbook.50" in ws_msg.topic:
                self._handle_orderbook_50(raw)
            elif "publicTrade" in ws_msg.topic:
                self._handle_trade(raw)
            elif "kline" in ws_msg.topic:
                self._handle_kline(raw)

        except msgspec.DecodeError:
            self._log.error(f"Error decoding message: {str(raw)}")

    def _handle_kline(self, raw: bytes):
        msg: BybitWsKlineMsg = self._ws_msg_kline_decoder.decode(raw)
        id = msg.topic.split(".")[-1] + self.market_type
        symbol = self._market_id[id]
        for d in msg.data:
            interval = BybitEnumParser.parse_kline_interval(d.interval)
            kline = Kline(
                exchange=self._exchange_id,
                symbol=symbol,
                interval=interval,
                open=float(d.open),
                high=float(d.high),
                low=float(d.low),
                close=float(d.close),
                volume=float(d.volume),
                start=d.start,
                confirm=d.confirm,
                timestamp=msg.ts,
            )
            self._msgbus.publish(topic="kline", msg=kline)

    def _handle_trade(self, raw: bytes):
        msg: BybitWsTradeMsg = self._ws_msg_trade_decoder.decode(raw)
        for d in msg.data:
            id = d.s + self.market_type
            symbol = self._market_id[id]
            trade = Trade(
                exchange=self._exchange_id,
                symbol=symbol,
                price=float(d.p),
                size=float(d.v),
                timestamp=msg.ts,
            )
            self._msgbus.publish(topic="trade", msg=trade)

    def _handle_orderbook(self, raw: bytes):
        msg: BybitWsOrderbookDepthMsg = self._ws_msg_orderbook_decoder.decode(raw)
        id = msg.data.s + self.market_type
        symbol = self._market_id[id]
        res = self._orderbook[symbol].parse_orderbook_depth(msg, levels=1)

        bid, bid_size = (
            (res["bids"][0].price, res["bids"][0].size) if res["bids"] else (0, 0)
        )
        ask, ask_size = (
            (res["asks"][0].price, res["asks"][0].size) if res["asks"] else (0, 0)
        )

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            timestamp=msg.ts,
            bid=bid,
            bid_size=bid_size,
            ask=ask,
            ask_size=ask_size,
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)
    
    def _handle_orderbook_50(self, raw: bytes):
        msg: BybitWsOrderbookDepthMsg = self._ws_msg_orderbook_decoder.decode(raw)
        id = msg.data.s + self.market_type
        symbol = self._market_id[id]
        res = self._orderbook[symbol].parse_orderbook_depth(msg, levels=50)

        bids = res["bids"] if res["bids"] else [BookOrderData(price=0, size=0)]
        asks = res["asks"] if res["asks"] else [BookOrderData(price=0, size=0)]

        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            timestamp=msg.ts,
            bids=bids,
            asks=asks,
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Kline]:
        # TODO: implement
        pass

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_order_book(symbols, depth=1)

    async def subscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_trade(symbols)

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        interval = BybitEnumParser.to_bybit_kline_interval(interval)
        await self._ws_client.subscribe_kline(symbols, interval)

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        if level != BookLevel.L50:
            raise ValueError(f"Unsupported book level: {level}")
        
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_order_book(symbols, depth=50)

class BybitPrivateConnector(PrivateConnector):
    _ws_client: BybitWSClient
    _account_type: BybitAccountType
    _market: Dict[str, BybitMarket]
    _market_id: Dict[str, str]
    _api_client: BybitApiClient

    def __init__(
        self,
        exchange: BybitExchangeManager,
        account_type: BybitAccountType,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        rate_limit: RateLimit | None = None,
    ):
        # all the private endpoints are the same for all account types, so no need to pass account_type
        # only need to determine if it's testnet or not

        if not exchange.api_key or not exchange.secret:
            raise ValueError("API key and secret are required for private endpoints")

        if account_type not in {
            BybitAccountType.UNIFIED,
            BybitAccountType.UNIFIED_TESTNET,
        }:
            raise ValueError(
                "Please using `BybitAccountType.UNIFIED` or `BybitAccountType.UNIFIED_TESTNET` in `PrivateConnector`"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BybitWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                api_key=exchange.api_key,
                secret=exchange.secret,
            ),
            api_client=BybitApiClient(
                api_key=exchange.api_key,
                secret=exchange.secret,
                testnet=account_type.is_testnet,
            ),
            msgbus=msgbus,
            cache=cache,
            rate_limit=rate_limit,
            task_manager=task_manager,
        )

        self._ws_msg_general_decoder = msgspec.json.Decoder(BybitWsMessageGeneral)
        self._ws_msg_order_update_decoder = msgspec.json.Decoder(BybitWsOrderMsg)
        self._ws_msg_position_decoder = msgspec.json.Decoder(BybitWsPositionMsg)
        self._ws_msg_wallet_decoder = msgspec.json.Decoder(BybitWsAccountWalletMsg)

    async def connect(self):
        await super().connect()
        await self._ws_client.subscribe_order()
        await self._ws_client.subscribe_position()
        await self._ws_client.subscribe_wallet()

    def _ws_msg_handler(self, raw: bytes):
        try:
            ws_msg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.op == "pong":
                self._ws_client._transport.notify_user_specific_pong_received()
                self._log.debug(f"Pong received {str(ws_msg)}")
                return
            if ws_msg.success is False:
                self._log.error(f"WebSocket error: {ws_msg}")
                return
            if "order" in ws_msg.topic:
                self._parse_order_update(raw)
            elif "position" in ws_msg.topic:
                self._parse_position_update(raw)
            elif "wallet" == ws_msg.topic:
                self._parse_wallet_update(raw)
        except msgspec.DecodeError:
            self._log.error(f"Error decoding message: {str(raw)}")

    def _get_category(self, market: BybitMarket):
        if market.spot:
            return "spot"
        elif market.linear:
            return "linear"
        elif market.inverse:
            return "inverse"
        else:
            raise ValueError(f"Unsupported market type: {market.type}")

    async def cancel_order(self, symbol: str, order_id: str, **kwargs):
        if self._limiter:
            await self._limiter.acquire()
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id

            category = self._get_category(market)

            params = {
                "category": category,
                "symbol": symbol,
                "order_id": order_id,
                **kwargs,
            }

            res = await self._api_client.post_v5_order_cancel(**params)
            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                client_order_id=res.result.orderLinkId,
                timestamp=res.time,
                symbol=market.symbol,
                status=OrderStatus.CANCELING,
            )
            return order
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.CANCEL_FAILED,
            )
            return order

    async def _init_account_balance(self):
        res: BybitWalletBalanceResponse = (
            await self._api_client.get_v5_account_wallet_balance(account_type="UNIFIED")
        )
        for result in res.result.list:
            self._cache._apply_balance(self._account_type, result.parse_to_balances())

    async def _init_position(self):
        res_linear: BybitPositionResponse = await self._api_client.get_v5_position_list(
            category="linear", settleCoin="USDT", limit=200
        )  # TODO: position must be smaller than 200
        res_inverse: BybitPositionResponse = (
            await self._api_client.get_v5_position_list(category="inverse", limit=200)
        )

        cache_positions = self._cache.get_all_positions(self._exchange_id)

        self._apply_cache_position(res_linear, cache_positions)
        self._apply_cache_position(res_inverse, cache_positions)

        for symbol, position in cache_positions.items():
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=None,
                signed_amount=Decimal(0),
                entry_price=0,
                unrealized_pnl=0,
                realized_pnl=0,
            )
            self._cache._apply_position(position)

    def _apply_cache_position(
        self, res: BybitPositionResponse, cache_positions: Dict[str, Position]
    ):
        category = res.result.category
        for result in res.result.list:
            side = result.side.parse_to_position_side()
            if side == PositionSide.FLAT:
                signed_amount = Decimal(0)
                side = None
            elif side == PositionSide.LONG:
                signed_amount = Decimal(result.size)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(result.size)

            if category.is_inverse:
                id = result.symbol + "_inverse"
            elif category.is_linear:
                id = result.symbol + "_linear"

            symbol = self._market_id[id]

            cache_positions.pop(symbol, None)

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(result.avgPrice),
                unrealized_pnl=float(result.unrealisedPnl),
                realized_pnl=float(result.cumRealisedPnl),
            )
            self._cache._apply_position(position)

    async def create_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ) -> Order:
        # TODO: implement
        pass

    async def create_take_profit_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ) -> Order:
        # TODO: implement
        pass

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        if self._limiter:
            await self._limiter.acquire()
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        symbol = market.id

        category = self._get_category(market)

        params = {
            "category": category,
            "symbol": symbol,
            "order_type": BybitEnumParser.to_bybit_order_type(type).value,
            "side": BybitEnumParser.to_bybit_order_side(side).value,
            "qty": str(amount),
        }

        if type == OrderType.LIMIT:
            if not price:
                raise ValueError("Price is required for limit order")
            params["price"] = str(price)
            params["timeInForce"] = BybitEnumParser.to_bybit_time_in_force(
                time_in_force
            ).value

        if position_side:
            params["positionSide"] = BybitEnumParser.to_bybit_position_side(
                position_side
            ).value

        reduce_only = kwargs.pop("reduceOnly", False) or kwargs.pop(
            "reduce_only", False
        )
        if reduce_only:
            params["reduceOnly"] = True
        params.update(kwargs)

        try:
            res = await self._api_client.post_v5_order_create(**params)

            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                client_order_id=res.result.orderLinkId,
                timestamp=int(res.time),
                symbol=market.symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=reduce_only,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        if self._limiter:
            await self._limiter.acquire()
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id

            category = self._get_category(market)

            params = {
                "category": category,
                "symbol": symbol,
            }

            await self._api_client.post_v5_order_cancel_all(**params)
            return True 
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling all orders: {error_msg} params: {str(params)}")
            return False

    async def modify_order(
        self,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ):
        #NOTE: side is not supported for modify order
        if self._limiter:
            await self._limiter.acquire()
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        symbol = market.id
        
        category = self._get_category(market)
        params = {
            "category": category,
            "symbol": symbol,
            "orderId": order_id,
            "price": str(price) if price else None,
            "qty": str(amount) if amount else None,
            **kwargs,
        }
        
        try:
            res = await self._api_client.post_v5_order_amend(**params)
            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                client_order_id=res.result.orderLinkId,
                timestamp=int(res.time),
                symbol=market.symbol,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                price=float(price) if price else None,
                remaining=amount,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
                price=float(price) if price else None,
            )
            return order

    def _parse_order_update(self, raw: bytes):
        order_msg = self._ws_msg_order_update_decoder.decode(raw)
        self._log.debug(f"Order update: {str(order_msg)}")
        for data in order_msg.data:
            category = data.category
            if category.is_spot:
                id = data.symbol + "_spot"
            elif category.is_linear:
                id = data.symbol + "_linear"
            elif category.is_inverse:
                id = data.symbol + "_inverse"
            symbol = self._market_id[id]

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=BybitEnumParser.parse_order_status(data.orderStatus),
                id=data.orderId,
                client_order_id=data.orderLinkId,
                timestamp=int(data.updatedTime),
                type=BybitEnumParser.parse_order_type(data.orderType),
                side=BybitEnumParser.parse_order_side(data.side),
                time_in_force=BybitEnumParser.parse_time_in_force(data.timeInForce),
                price=float(data.price),
                average=float(data.avgPrice) if data.avgPrice else None,
                amount=Decimal(data.qty),
                filled=Decimal(data.cumExecQty),
                remaining=Decimal(data.qty)
                - Decimal(
                    data.cumExecQty
                ),  # TODO: check if this is correct leavsQty is not correct
                fee=Decimal(data.cumExecFee),
                fee_currency=data.feeCurrency,
                cum_cost=Decimal(data.cumExecValue),
                reduce_only=data.reduceOnly,
                position_side=BybitEnumParser.parse_position_side(data.positionIdx),
            )

            self._msgbus.send(endpoint="bybit.order", msg=order)

    def _parse_position_update(self, raw: bytes):
        position_msg = self._ws_msg_position_decoder.decode(raw)
        self._log.debug(f"Position update: {str(position_msg)}")

        for data in position_msg.data:
            category = data.category
            if category.is_linear:  # only linear/inverse/ position is supported
                id = data.symbol + "_linear"
            elif category.is_inverse:
                id = data.symbol + "_inverse"
            symbol = self._market_id[id]

            side = data.side.parse_to_position_side()
            if side == PositionSide.LONG:
                signed_amount = Decimal(data.size)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.size)
            else:
                side = None
                signed_amount = Decimal(0)

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(data.entryPrice),
                unrealized_pnl=float(data.unrealisedPnl),
                realized_pnl=float(data.cumRealisedPnl),
            )

            self._cache._apply_position(position)

    def _parse_wallet_update(self, raw: bytes):
        wallet_msg = self._ws_msg_wallet_decoder.decode(raw)
        self._log.debug(f"Wallet update: {str(wallet_msg)}")

        for data in wallet_msg.data:
            balances = data.parse_to_balances()
            self._cache._apply_balance(self._account_type, balances)

    async def disconnect(self):
        await super().disconnect()
        await self._api_client.close_session()

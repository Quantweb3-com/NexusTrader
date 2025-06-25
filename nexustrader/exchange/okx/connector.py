import msgspec
import warnings
from typing import Dict, List
from decimal import Decimal
from nexustrader.error import PositionModeError
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.exchange.okx.websockets import OkxWSClient
from nexustrader.exchange.okx.exchange import OkxExchangeManager
from nexustrader.exchange.okx.schema import OkxWsGeneralMsg
from nexustrader.schema import (
    Trade,
    BookL1,
    Kline,
    Order,
    Position,
    BookL2,
    IndexPrice,
    FundingRate,
    MarkPrice,
    BatchOrderSubmit,
    KlineList,
)
from nexustrader.exchange.okx.schema import (
    OkxMarket,
    OkxWsBboTbtMsg,
    OkxWsCandleMsg,
    OkxWsTradeMsg,
    OkxWsIndexTickerMsg,
    OkxWsFundingRateMsg,
    OkxWsMarkPriceMsg,
    OkxWsOrderMsg,
    OkxWsPositionMsg,
    OkxWsAccountMsg,
    OkxBalanceResponse,
    OkxPositionResponse,
    OkxCandlesticksResponse,
    OkxCandlesticksResponseData,
    OkxWsBook5Msg,
    OkxIndexCandlesticksResponseData,
)
from nexustrader.constants import (
    OrderStatus,
    TimeInForce,
    PositionSide,
    KlineInterval,
    TriggerType,
    BookLevel,
)
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.exchange.okx.rest_api import OkxApiClient
from nexustrader.constants import OrderSide, OrderType
from nexustrader.exchange.okx.constants import (
    OkxTdMode,
    OkxEnumParser,
    OkxKlineInterval,
)


class OkxPublicConnector(PublicConnector):
    _ws_client: OkxWSClient
    _api_client: OkxApiClient
    _account_type: OkxAccountType

    def __init__(
        self,
        account_type: OkxAccountType,
        exchange: OkxExchangeManager,
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
            ws_client=OkxWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                custom_url=custom_url,
            ),
            msgbus=msgbus,
            api_client=OkxApiClient(
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )
        self._business_ws_client = OkxWSClient(
            account_type=account_type,
            handler=self._business_ws_msg_handler,
            task_manager=task_manager,
            business_url=True,
            custom_url=custom_url,
        )
        self._ws_msg_general_decoder = msgspec.json.Decoder(OkxWsGeneralMsg)
        self._ws_msg_bbo_tbt_decoder = msgspec.json.Decoder(OkxWsBboTbtMsg)
        self._ws_msg_book5_decoder = msgspec.json.Decoder(OkxWsBook5Msg)
        self._ws_msg_candle_decoder = msgspec.json.Decoder(OkxWsCandleMsg)
        self._ws_msg_trade_decoder = msgspec.json.Decoder(OkxWsTradeMsg)
        self._ws_msg_index_ticker_decoder = msgspec.json.Decoder(OkxWsIndexTickerMsg)
        self._ws_msg_mark_price_decoder = msgspec.json.Decoder(OkxWsMarkPriceMsg)
        self._ws_msg_funding_rate_decoder = msgspec.json.Decoder(OkxWsFundingRateMsg)

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        okx_interval = OkxEnumParser.to_okx_kline_interval(interval)
        all_klines: list[Kline] = []
        seen_timestamps: set[int] = set()

        # First request to get the most recent data using before parameter
        klines_response: OkxCandlesticksResponse = (
            self._api_client.get_api_v5_market_history_index_candles(
                instId=self._market[symbol].id,
                bar=okx_interval.value,
                limit=100,  # Maximum allowed by the API is 100
                before="0",  # Get the latest klines
            )
        )

        response_klines = sorted(klines_response.data, key=lambda x: int(x.ts))
        klines = [
            self._handle_index_candlesticks(
                symbol=symbol, interval=interval, kline=kline
            )
            for kline in response_klines
            if int(kline.ts) not in seen_timestamps
        ]
        all_klines.extend(klines)
        seen_timestamps.update(int(kline.ts) for kline in response_klines)

        # Continue fetching older data using after parameter if needed
        if (
            start_time is not None
            and all_klines
            and int(all_klines[0].timestamp) > start_time
        ):
            while True:
                # Use the oldest timestamp we have as the 'after' parameter
                oldest_timestamp = (
                    min(int(kline.ts) for kline in response_klines)
                    if response_klines
                    else None
                )

                if not oldest_timestamp or (
                    start_time is not None and oldest_timestamp <= start_time
                ):
                    break

                klines_response = (
                    self._api_client.get_api_v5_market_history_index_candles(
                        instId=self._market[symbol].id,
                        bar=okx_interval.value,
                        limit=100,
                        after=str(oldest_timestamp),  # Get klines before this timestamp
                    )
                )

                response_klines = sorted(klines_response.data, key=lambda x: int(x.ts))
                if not response_klines:
                    break

                # Process klines and filter out duplicates
                new_klines = [
                    self._handle_index_candlesticks(
                        symbol=symbol, interval=interval, kline=kline
                    )
                    for kline in response_klines
                    if int(kline.ts) not in seen_timestamps
                ]

                if not new_klines:
                    break

                all_klines = (
                    new_klines + all_klines
                )  # Prepend new klines as they are older
                seen_timestamps.update(int(kline.ts) for kline in response_klines)

        # Apply limit if specified
        if limit is not None and len(all_klines) > limit:
            all_klines = all_klines[-limit:]  # Take the most recent klines

        if end_time:
            all_klines = [kline for kline in all_klines if kline.timestamp < end_time]

        kline_list = KlineList(
            all_klines,
            fields=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "confirm",
            ],
        )
        return kline_list

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        okx_interval = OkxEnumParser.to_okx_kline_interval(interval)
        all_klines: list[Kline] = []
        seen_timestamps: set[int] = set()

        # First request to get the most recent data using before parameter
        klines_response: OkxCandlesticksResponse = (
            self._api_client.get_api_v5_market_history_candles(
                instId=self._market[symbol].id,
                bar=okx_interval.value,
                limit=100,  # Maximum allowed by the API is 100
                before="0",  # Get the latest klines
            )
        )

        response_klines = sorted(klines_response.data, key=lambda x: int(x.ts))
        klines = [
            self._handle_candlesticks(symbol=symbol, interval=interval, kline=kline)
            for kline in response_klines
            if int(kline.ts) not in seen_timestamps
        ]
        all_klines.extend(klines)
        seen_timestamps.update(int(kline.ts) for kline in response_klines)

        # Continue fetching older data using after parameter if needed
        if (
            start_time is not None
            and all_klines
            and int(all_klines[0].timestamp) > start_time
        ):
            while True:
                # Use the oldest timestamp we have as the 'after' parameter
                oldest_timestamp = (
                    min(int(kline.ts) for kline in response_klines)
                    if response_klines
                    else None
                )

                if not oldest_timestamp or (
                    start_time is not None and oldest_timestamp <= start_time
                ):
                    break

                klines_response = self._api_client.get_api_v5_market_history_candles(
                    instId=self._market[symbol].id,
                    bar=okx_interval.value,
                    limit=100,
                    after=str(oldest_timestamp),  # Get klines before this timestamp
                )

                response_klines = sorted(klines_response.data, key=lambda x: int(x.ts))
                if not response_klines:
                    break

                # Process klines and filter out duplicates
                new_klines = [
                    self._handle_candlesticks(
                        symbol=symbol, interval=interval, kline=kline
                    )
                    for kline in response_klines
                    if int(kline.ts) not in seen_timestamps
                ]

                if not new_klines:
                    break

                all_klines = (
                    new_klines + all_klines
                )  # Prepend new klines as they are older
                seen_timestamps.update(int(kline.ts) for kline in response_klines)

        # Apply limit if specified
        if limit is not None and len(all_klines) > limit:
            all_klines = all_klines[-limit:]  # Take the most recent klines

        if end_time:
            all_klines = [kline for kline in all_klines if kline.timestamp < end_time]

        kline_list = KlineList(
            all_klines,
            fields=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "confirm",
            ],
        )
        return kline_list

    async def subscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_trade(symbols)

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_order_book(symbols, channel="bbo-tbt")

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        if level != BookLevel.L5:
            raise ValueError("Only L5 book level is supported for OKX")

        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_order_book(symbols, channel="books5")

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        interval = OkxEnumParser.to_okx_kline_interval(interval)
        await self._business_ws_client.subscribe_candlesticks(symbols, interval)

    async def subscribe_funding_rate(self, symbol: List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_funding_rate(symbols)

    async def subscribe_index_price(self, symbol: List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_index_price(symbols)

    async def subscribe_mark_price(self, symbol: List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} not found in market")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(symbols)

    def _business_ws_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._business_ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received:{str(raw)}")
            return
        try:
            ws_msg: OkxWsGeneralMsg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.is_event_msg:
                self._handle_event_msg(ws_msg)
            else:
                channel: str = ws_msg.arg.channel
                if channel.startswith("candle"):
                    self._handle_kline(raw)
        except msgspec.DecodeError:
            self._log.error(f"Error decoding message: {str(raw)}")

    def _ws_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received:{str(raw)}")
            return
        try:
            ws_msg: OkxWsGeneralMsg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.is_event_msg:
                self._handle_event_msg(ws_msg)
            else:
                channel: str = ws_msg.arg.channel
                if channel == "bbo-tbt":
                    self._handle_bbo_tbt(raw)
                elif channel == "trades":
                    self._handle_trade(raw)
                elif channel.startswith("candle"):
                    self._handle_kline(raw)
                elif channel == "books5":
                    self._handle_book5(raw)
                elif channel == "index-ticker":
                    self._handle_index_ticker(raw)
                elif channel == "mark-price":
                    self._handle_mark_price(raw)
                elif channel == "funding-rate":
                    self._handle_funding_rate(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_index_ticker(self, raw: bytes):
        msg: OkxWsIndexTickerMsg = self._ws_msg_index_ticker_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]

        for d in msg.data:
            index_price = IndexPrice(
                exchange=self._exchange_id,
                symbol=symbol,
                price=float(d.idxPx),
                timestamp=int(d.ts),
            )
            self._msgbus.publish(topic="index_price", msg=index_price)

    def _handle_mark_price(self, raw: bytes):
        msg: OkxWsMarkPriceMsg = self._ws_msg_mark_price_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]

        for d in msg.data:
            mark_price = MarkPrice(
                exchange=self._exchange_id,
                symbol=symbol,
                price=float(d.markPx),
                timestamp=int(d.ts),
            )
            self._msgbus.publish(topic="mark_price", msg=mark_price)

    def _handle_funding_rate(self, raw: bytes):
        msg: OkxWsFundingRateMsg = self._ws_msg_funding_rate_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]

        for d in msg.data:
            funding_rate = FundingRate(
                exchange=self._exchange_id,
                symbol=symbol,
                rate=float(d.fundingRate),
                timestamp=int(d.ts),
                next_funding_time=int(d.fundingTime),
            )
            self._msgbus.publish(topic="funding_rate", msg=funding_rate)

    def _handle_book5(self, raw: bytes):
        msg: OkxWsBook5Msg = self._ws_msg_book5_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]

        for d in msg.data:
            asks = [d.parse_to_book_order_data() for d in d.asks]
            bids = [d.parse_to_book_order_data() for d in d.bids]
            bookl2 = BookL2(
                exchange=self._exchange_id,
                symbol=symbol,
                asks=asks,
                bids=bids,
                timestamp=int(d.ts),
            )
            self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _handle_event_msg(self, ws_msg: OkxWsGeneralMsg):
        if ws_msg.event == "error":
            self._log.error(f"Error code: {ws_msg.code}, message: {ws_msg.msg}")
        elif ws_msg.event == "login":
            self._log.debug("Login success")
        elif ws_msg.event == "subscribe":
            self._log.debug(f"Subscribed to {ws_msg.arg.channel}")

    def _handle_kline(self, raw: bytes):
        msg: OkxWsCandleMsg = self._ws_msg_candle_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]
        okx_interval = OkxKlineInterval(msg.arg.channel)
        interval = OkxEnumParser.parse_kline_interval(okx_interval)

        for d in msg.data:
            kline = Kline(
                exchange=self._exchange_id,
                symbol=symbol,
                interval=interval,
                open=float(d[1]),
                high=float(d[2]),
                low=float(d[3]),
                close=float(d[4]),
                volume=float(d[5]),
                start=int(d[0]),
                timestamp=self._clock.timestamp_ms(),
                confirm=False if d[8] == "0" else True,
            )
            self._msgbus.publish(topic="kline", msg=kline)

    def _handle_trade(self, raw: bytes):
        msg: OkxWsTradeMsg = self._ws_msg_trade_decoder.decode(raw)
        id = msg.arg.instId
        symbol = self._market_id[id]
        for d in msg.data:
            trade = Trade(
                exchange=self._exchange_id,
                symbol=symbol,
                price=float(d.px),
                size=float(d.sz),
                timestamp=int(d.ts),
            )
            self._msgbus.publish(topic="trade", msg=trade)

    def _handle_bbo_tbt(self, raw: bytes):
        msg: OkxWsBboTbtMsg = self._ws_msg_bbo_tbt_decoder.decode(raw)

        id = msg.arg.instId
        symbol = self._market_id[id]

        for d in msg.data:
            if not d.bids or not d.asks:
                continue

            bookl1 = BookL1(
                exchange=self._exchange_id,
                symbol=symbol,
                bid=float(d.bids[0][0]),
                ask=float(d.asks[0][0]),
                bid_size=float(d.bids[0][1]),
                ask_size=float(d.asks[0][1]),
                timestamp=int(d.ts),
            )
            self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _handle_index_candlesticks(
        self,
        symbol: str,
        interval: KlineInterval,
        kline: OkxIndexCandlesticksResponseData,
    ) -> Kline:
        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.o),
            high=float(kline.h),
            low=float(kline.l),
            close=float(kline.c),
            start=int(kline.ts),
            timestamp=self._clock.timestamp_ms(),
            confirm=False if int(kline.confirm) == 0 else True,
        )

    def _handle_candlesticks(
        self, symbol: str, interval: KlineInterval, kline: OkxCandlesticksResponseData
    ) -> Kline:
        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.o),
            high=float(kline.h),
            low=float(kline.l),
            close=float(kline.c),
            volume=float(kline.vol),
            quote_volume=float(kline.volCcyQuote),
            start=int(kline.ts),
            timestamp=self._clock.timestamp_ms(),
            confirm=False if int(kline.confirm) == 0 else True,
        )

    async def disconnect(self):
        await super().disconnect()
        self._business_ws_client.disconnect()


class OkxPrivateConnector(PrivateConnector):
    _ws_client: OkxWSClient
    _api_client: OkxApiClient
    _account_type: OkxAccountType
    _market: Dict[str, OkxMarket]
    _market_id: Dict[str, str]

    def __init__(
        self,
        exchange: OkxExchangeManager,
        account_type: OkxAccountType,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
    ):
        if not exchange.api_key or not exchange.secret or not exchange.passphrase:
            raise ValueError(
                "API key, secret, and passphrase are required for private endpoints"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=OkxWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                api_key=exchange.api_key,
                secret=exchange.secret,
                passphrase=exchange.passphrase,
            ),
            api_client=OkxApiClient(
                api_key=exchange.api_key,
                secret=exchange.secret,
                passphrase=exchange.passphrase,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            msgbus=msgbus,
            cache=cache,
            task_manager=task_manager,
        )

        self._decoder_ws_general_msg = msgspec.json.Decoder(OkxWsGeneralMsg)
        self._decoder_ws_order_msg = msgspec.json.Decoder(OkxWsOrderMsg, strict=False)
        self._decoder_ws_position_msg = msgspec.json.Decoder(
            OkxWsPositionMsg, strict=False
        )
        self._decoder_ws_account_msg = msgspec.json.Decoder(
            OkxWsAccountMsg, strict=False
        )

        self._acctLv = None

    async def connect(self):
        await super().connect()
        await self._ws_client.subscribe_orders()
        await self._ws_client.subscribe_positions()
        await self._ws_client.subscribe_account()
        # await self._ws_client.subscribe_account_position()
        # await self._ws_client.subscribe_fills()

    async def _position_mode_check(self):
        res = await self._api_client.get_api_v5_account_config()
        for data in res.data:
            if not data.posMode.is_one_way_mode:
                raise PositionModeError(
                    "Please Set Position Mode to `One-Way Mode` in OKX App"
                )
            if data.acctLv.is_portfolio_margin:
                warnings.warn(
                    "For Portfolio Margin Account, `Reduce Only` is not supported"
                )
            self._acctLv = data.acctLv

    async def _init_account_balance(self):
        res: OkxBalanceResponse = await self._api_client.get_api_v5_account_balance()
        for data in res.data:
            self._cache._apply_balance(self._account_type, data.parse_to_balances())

    async def _init_position(self):
        res: OkxPositionResponse = await self._api_client.get_api_v5_account_positions()
        for data in res.data:
            side = data.posSide.parse_to_position_side()
            if side == PositionSide.FLAT:
                signed_amount = Decimal(data.pos)
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT
                else:
                    side = None
            elif side == PositionSide.LONG:
                signed_amount = Decimal(data.pos)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.pos)

            symbol = self._market_id.get(data.instId)
            if not symbol:
                warnings.warn(f"Symbol {data.instId} not found in market")
                continue
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(data.avgPx) if data.avgPx else 0,
                unrealized_pnl=float(data.upl) if data.upl else 0,
                realized_pnl=float(data.realizedPnl) if data.realizedPnl else 0,
            )
            self._cache._apply_position(position)

    def _handle_event_msg(self, msg: OkxWsGeneralMsg):
        if msg.event == "error":
            self._log.error(msg)
        elif msg.event == "login":
            self._log.debug("Login success")
        elif msg.event == "subscribe":
            self._log.debug(f"Subscribed to {msg.arg.channel}")

    def _ws_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: {str(raw)}")
            return
        try:
            ws_msg: OkxWsGeneralMsg = self._decoder_ws_general_msg.decode(raw)
            if ws_msg.is_event_msg:
                self._handle_event_msg(ws_msg)
            else:
                channel = ws_msg.arg.channel
                if channel == "orders":
                    self._handle_orders(raw)
                elif channel == "positions":
                    self._handle_positions(raw)
                elif channel == "account":
                    self._handle_account(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_orders(self, raw: bytes):
        msg: OkxWsOrderMsg = self._decoder_ws_order_msg.decode(raw)
        self._log.debug(f"Order update: {str(msg)}")
        for data in msg.data:
            symbol = self._market_id[data.instId]

            market = self._market[symbol]

            if not market.spot:
                ct_val = Decimal(market.info.ctVal)  # contract size
            else:
                ct_val = Decimal("1")

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OkxEnumParser.parse_order_status(data.state),
                id=data.ordId,
                amount=Decimal(data.sz) * ct_val,
                filled=Decimal(data.accFillSz) * ct_val,
                client_order_id=data.clOrdId,
                timestamp=data.uTime,
                type=OkxEnumParser.parse_order_type(data.ordType),
                side=OkxEnumParser.parse_order_side(data.side),
                time_in_force=OkxEnumParser.parse_time_in_force(data.ordType),
                price=float(data.px) if data.px else None,
                average=float(data.avgPx) if data.avgPx else None,
                last_filled_price=float(data.fillPx) if data.fillPx else None,
                last_filled=Decimal(data.fillSz) * ct_val
                if data.fillSz
                else Decimal(0),
                remaining=Decimal(data.sz) * ct_val - Decimal(data.accFillSz) * ct_val,
                fee=Decimal(data.fee),  # accumalated fee
                fee_currency=data.feeCcy,  # accumalated fee currency
                cost=Decimal(data.avgPx) * Decimal(data.fillSz) * ct_val,
                cum_cost=Decimal(data.avgPx) * Decimal(data.accFillSz) * ct_val,
                reduce_only=data.reduceOnly,
                position_side=OkxEnumParser.parse_position_side(data.posSide),
            )
            self._msgbus.send(endpoint="okx.order", msg=order)

    def _handle_positions(self, raw: bytes):
        position_msg = self._decoder_ws_position_msg.decode(raw)
        self._log.debug(f"Okx Position Msg: {str(position_msg)}")

        for data in position_msg.data:
            symbol = self._market_id.get(data.instId)
            if not symbol:
                continue
            market = self._market[symbol]

            if market.info.ctVal:
                ct_val = Decimal(market.info.ctVal)
            else:
                ct_val = Decimal("1")

            side = data.posSide.parse_to_position_side()
            if side == PositionSide.LONG:
                signed_amount = Decimal(data.pos)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.pos)
            elif side == PositionSide.FLAT:
                # one way mode, posSide always is 'net' from OKX ws msg, and pos amount is signed
                signed_amount = Decimal(data.pos)
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT
                else:
                    side = None
            else:
                self._log.warning(f"Invalid position side: {side}")

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount * ct_val,
                entry_price=float(data.avgPx) if data.avgPx else 0,
                unrealized_pnl=float(data.upl) if data.upl else 0,
                realized_pnl=float(data.realizedPnl) if data.realizedPnl else 0,
            )
            self._log.debug(f"Position updated: {str(position)}")
            self._cache._apply_position(position)

    def _handle_account(self, raw: bytes):
        account_msg: OkxWsAccountMsg = self._decoder_ws_account_msg.decode(raw)
        self._log.debug(f"Account update: {str(account_msg)}")

        for data in account_msg.data:
            balances = data.parse_to_balance()
            self._cache._apply_balance(self._account_type, balances)

    def _get_td_mode(self, market: OkxMarket):
        if (
            not market.spot
            or self._acctLv.is_portfolio_margin
            or self._acctLv.is_multi_currency_margin
        ):
            return OkxTdMode.CROSS
        else:
            return OkxTdMode.CASH

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
        raise NotImplementedError("Stop loss order is not currently supported for okx")

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
        raise NotImplementedError(
            "Take profit order is not currently supported for okx"
        )

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ):
        if not orders:
            raise ValueError("Orders list cannot be empty")

        batch_orders = []
        for order in orders:
            market = self._market.get(order.symbol)
            if not market:
                raise ValueError(
                    f"Symbol {order.symbol} formated wrongly, or not supported"
                )
            inst_id = market.id

            td_mode = order.kwargs.pop("td_mode", None) or order.kwargs.pop(
                "tdMode", None
            )
            if not td_mode:
                td_mode = self._get_td_mode(market)
            else:
                td_mode = OkxTdMode(td_mode)

            if not market.spot:
                ct_val = Decimal(market.info.ctVal)
                sz = format(order.amount / ct_val, "f")
            else:
                sz = str(order.amount)

            params = {
                "inst_id": inst_id,
                "td_mode": td_mode.value,
                "side": OkxEnumParser.to_okx_order_side(order.side).value,
                "ord_type": OkxEnumParser.to_okx_order_type(
                    order.type, order.time_in_force
                ).value,
                "sz": sz,
            }

            if order.type == OrderType.LIMIT:
                if not order.price:
                    raise ValueError("Price is required for limit order")
                params["px"] = str(order.price)
            else:
                if (
                    market.spot
                    and not self._acctLv.is_futures
                    and not td_mode.is_isolated
                ):
                    params["tgtCcy"] = "base_ccy"

            if (
                market.spot
                and self._acctLv.is_futures
                and (td_mode.is_cross or td_mode.is_isolated)
            ):
                if order.side == OrderSide.BUY:
                    params["ccy"] = market.quote
                else:
                    params["ccy"] = market.base

            reduce_only = order.kwargs.pop("reduceOnly", False) or order.kwargs.pop(
                "reduce_only", False
            )
            if reduce_only:
                params["reduceOnly"] = True

            params.update(order.kwargs)
            batch_orders.append(params)

        try:
            res = await self._api_client.post_api_v5_trade_batch_orders(
                payload=batch_orders
            )
            res_batch_orders = []
            for order, res_order in zip(orders, res.data):
                if res_order.sCode == "0":
                    order_result = Order(
                        exchange=self._exchange_id,
                        uuid=order.uuid,
                        id=res_order.ordId,
                        client_order_id=res_order.clOrdId,
                        timestamp=int(res_order.ts),
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price) if order.price else None,
                        time_in_force=order.time_in_force,
                        status=OrderStatus.PENDING,
                        filled=Decimal(0),
                        remaining=order.amount,
                    )
                else:
                    order_result = Order(
                        exchange=self._exchange_id,
                        uuid=order.uuid,
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
                    )
                    self._log.error(
                        f"Failed to create order for {order.symbol}: {res_order.sMsg}: {res_order.sCode}: {order.uuid}"
                    )
                res_batch_orders.append(order_result)
            return res_batch_orders
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(
                f"Error creating batch orders: {error_msg} params: {str(orders)}"
            )
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
                )
                for order in orders
            ]
            return res_batch_orders

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        td_mode = kwargs.pop("td_mode", None) or kwargs.pop("tdMode", None)
        if not td_mode:
            td_mode = self._get_td_mode(market)
        else:
            td_mode = OkxTdMode(td_mode)

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f")
        else:
            sz = str(amount)

        params = {
            "inst_id": inst_id,
            "td_mode": td_mode.value,
            "side": OkxEnumParser.to_okx_order_side(side).value,
            "ord_type": OkxEnumParser.to_okx_order_type(type, time_in_force).value,
            "sz": sz,
            "tag": "f50cdd72d3b6BCDE",
        }

        if type == OrderType.LIMIT:
            if not price:
                raise ValueError("Price is required for limit order")
            params["px"] = str(price)
        else:
            if market.spot and not self._acctLv.is_futures and not td_mode.is_isolated:
                params["tgtCcy"] = "base_ccy"

        if (
            market.spot
            and self._acctLv.is_futures
            and (td_mode.is_cross or td_mode.is_isolated)
        ):
            if side == OrderSide.BUY:
                params["ccy"] = market.quote
            else:
                params["ccy"] = market.base

        if position_side:
            params["posSide"] = OkxEnumParser.to_okx_position_side(position_side).value

        reduce_only = kwargs.pop("reduceOnly", False) or kwargs.pop(
            "reduce_only", False
        )
        if reduce_only:
            params["reduceOnly"] = True

        params.update(kwargs)

        try:
            res = await self._api_client.post_api_v5_trade_order(**params)
            res = res.data[0]
            order = Order(
                exchange=self._exchange_id,
                id=res.ordId,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
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

    async def cancel_order(self, symbol: str, order_id: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        params = {"inst_id": inst_id, "ord_id": order_id, **kwargs}

        try:
            res = await self._api_client.post_api_v5_trade_cancel_order(**params)
            res = res.data[0]
            order = Order(
                exchange=self._exchange_id,
                id=res.ordId,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
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

    async def modify_order(
        self,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ):
        # NOTE: modify order with side is not supported by OKX
        if price is None and amount is None:
            raise ValueError("Either price or amount must be provided")
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f") if amount else None
        else:
            sz = str(amount) if amount else None

        params = {
            "instId": inst_id,
            "ordId": order_id,
            "newPx": str(price) if price else None,
            "newSz": sz,
            **kwargs,
        }

        try:
            res = await self._api_client.post_api_v5_trade_amend_order(**params)
            res = res.data[0]
            order = Order(
                exchange=self._exchange_id,
                id=res.ordId,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
                status=OrderStatus.PENDING,
            )
            return order
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.FAILED,
            )
            return order

    async def cancel_all_orders(self, symbol: str) -> bool:
        """
        no cancel all orders in OKX
        """
        pass

    async def disconnect(self):
        await super().disconnect()
        await self._api_client.close_session()

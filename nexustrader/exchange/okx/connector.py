import msgspec
from typing import Dict, List
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.exchange.okx.websockets import OkxWSClient
from nexustrader.exchange.okx.exchange import OkxExchangeManager
from nexustrader.exchange.okx.schema import OkxWsGeneralMsg
from nexustrader.exchange.okx.oms import OkxOrderManagementSystem
from nexustrader.schema import (
    Trade,
    BookL1,
    Kline,
    BookL2,
    IndexPrice,
    FundingRate,
    MarkPrice,
    KlineList,
    Ticker,
)
from nexustrader.exchange.okx.schema import (
    OkxMarket,
    OkxWsBboTbtMsg,
    OkxWsCandleMsg,
    OkxWsTradeMsg,
    OkxWsIndexTickerMsg,
    OkxWsFundingRateMsg,
    OkxWsMarkPriceMsg,
    OkxCandlesticksResponse,
    OkxCandlesticksResponseData,
    OkxWsBook5Msg,
    OkxTickersResponse,
    OkxIndexCandlesticksResponseData,
)
from nexustrader.constants import (
    KlineInterval,
    BookLevel,
)
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.okx.rest_api import OkxApiClient
from nexustrader.exchange.okx.constants import (
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
            ws_client=OkxWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                custom_url=custom_url,
                clock=clock,
            ),
            msgbus=msgbus,
            clock=clock,
            api_client=OkxApiClient(
                clock=clock,
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
            clock=clock,
        )
        self._ws_msg_general_decoder = msgspec.json.Decoder(OkxWsGeneralMsg)
        self._ws_msg_bbo_tbt_decoder = msgspec.json.Decoder(OkxWsBboTbtMsg)
        self._ws_msg_book5_decoder = msgspec.json.Decoder(OkxWsBook5Msg)
        self._ws_msg_candle_decoder = msgspec.json.Decoder(OkxWsCandleMsg)
        self._ws_msg_trade_decoder = msgspec.json.Decoder(OkxWsTradeMsg)
        self._ws_msg_index_ticker_decoder = msgspec.json.Decoder(OkxWsIndexTickerMsg)
        self._ws_msg_mark_price_decoder = msgspec.json.Decoder(OkxWsMarkPriceMsg)
        self._ws_msg_funding_rate_decoder = msgspec.json.Decoder(OkxWsFundingRateMsg)

    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        ticker_response: OkxTickersResponse = self._api_client.get_api_v5_market_ticker(
            inst_id=market.id
        )
        for item in ticker_response.data:
            ticker = Ticker(
                exchange=self._exchange_id,
                symbol=symbol,
                last_price=float(item.last) if item.last else 0.0,
                timestamp=int(item.ts),
                volume=float(item.vol24h) if item.vol24h else 0.0,
                volumeCcy=float(item.volCcy24h) if item.volCcy24h else 0.0,
            )
            return ticker

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        spot_tickers_response: OkxTickersResponse = (
            self._api_client.get_api_v5_market_tickers(inst_type="SPOT")
        )
        swap_tickers_response: OkxTickersResponse = (
            self._api_client.get_api_v5_market_tickers(inst_type="SWAP")
        )
        future_tickers_response: OkxTickersResponse = (
            self._api_client.get_api_v5_market_tickers(inst_type="FUTURES")
        )

        tickers = {}
        for item in (
            spot_tickers_response.data
            + swap_tickers_response.data
            + future_tickers_response.data
        ):
            symbol = self._market_id.get(item.instId)
            if not symbol:
                continue
            tickers[symbol] = Ticker(
                exchange=self._exchange_id,
                symbol=symbol,
                last_price=float(item.last) if item.last else 0.0,
                timestamp=int(item.ts),
                volume=float(item.vol24h) if item.vol24h else 0.0,
                volumeCcy=float(item.volCcy24h) if item.volCcy24h else 0.0,
            )

        return tickers

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
            self._log.debug(f"Pong received:{raw.decode()}")
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
                side=OkxEnumParser.parse_order_side(d.side),
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
    _api_client: OkxApiClient
    _account_type: OkxAccountType
    _market: Dict[str, OkxMarket]
    _market_id: Dict[str, str]
    _oms: OkxOrderManagementSystem

    def __init__(
        self,
        account_type: OkxAccountType,
        exchange: OkxExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret or not exchange.passphrase:
            raise ValueError(
                "API key, secret, and passphrase are required for private endpoints"
            )

        api_client = OkxApiClient(
            clock=clock,
            api_key=exchange.api_key,
            secret=exchange.secret,
            passphrase=exchange.passphrase,
            testnet=account_type.is_testnet,
            enable_rate_limit=enable_rate_limit,
            **kwargs,
        )

        oms = OkxOrderManagementSystem(
            account_type=account_type,
            api_key=exchange.api_key,
            secret=exchange.secret,
            passphrase=exchange.passphrase,
            market=exchange.market,
            market_id=exchange.market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            exchange_id=exchange.exchange_id,
            clock=clock,
            msgbus=msgbus,
            task_manager=task_manager,
            enable_rate_limit=enable_rate_limit,
        )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            api_client=api_client,
            task_manager=task_manager,
            oms=oms,
        )

    async def connect(self):
        await self._oms._ws_api_client.connect()
        await self._oms._ws_client.subscribe_orders()
        await self._oms._ws_client.subscribe_positions()
        await self._oms._ws_client.subscribe_account()

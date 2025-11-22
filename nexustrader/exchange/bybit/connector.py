import msgspec
from typing import Dict, List
from collections import defaultdict
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    BookL2,
    BookOrderData,
    FundingRate,
    IndexPrice,
    MarkPrice,
    KlineList,
    Ticker,
)
from nexustrader.constants import (
    KlineInterval,
    BookLevel,
)
from nexustrader.exchange.bybit.schema import (
    BybitKlineResponse,
    BybitKlineResponseArray,
    BybitWsMessageGeneral,
    BybitWsOrderbookDepthMsg,
    BybitOrderBook,
    BybitMarket,
    BybitWsTradeMsg,
    BybitWsTickerMsg,
    BybitWsKlineMsg,
    BybitTicker,
    BybitIndexKlineResponse,
    BybitIndexKlineResponseArray,
)
from nexustrader.exchange.bybit.rest_api import BybitApiClient
from nexustrader.exchange.bybit.websockets import BybitWSClient
from nexustrader.exchange.bybit.oms import BybitOrderManagementSystem
from nexustrader.exchange.bybit.constants import (
    BybitAccountType,
    BybitEnumParser,
)
from nexustrader.exchange.bybit.exchange import BybitExchangeManager


class BybitPublicConnector(PublicConnector):
    _api_client: BybitApiClient
    _ws_client: BybitWSClient
    _account_type: BybitAccountType

    def __init__(
        self,
        account_type: BybitAccountType,
        exchange: BybitExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
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
                clock=clock,
                task_manager=task_manager,
                custom_url=custom_url,
            ),
            clock=clock,
            msgbus=msgbus,
            api_client=BybitApiClient(
                clock=clock,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )
        self._ws_msg_trade_decoder = msgspec.json.Decoder(BybitWsTradeMsg)
        self._ws_msg_orderbook_decoder = msgspec.json.Decoder(BybitWsOrderbookDepthMsg)
        self._ws_msg_general_decoder = msgspec.json.Decoder(BybitWsMessageGeneral)
        self._ws_msg_kline_decoder = msgspec.json.Decoder(BybitWsKlineMsg)
        self._ws_msg_ticker_decoder = msgspec.json.Decoder(BybitWsTickerMsg)
        self._bookl1_orderbook = defaultdict(BybitOrderBook)
        self._bookl2_orderbook = defaultdict(BybitOrderBook)
        self._ticker: Dict[str, BybitTicker] = defaultdict(BybitTicker)

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

    def _get_category(self, market: BybitMarket):
        if market.spot:
            return "spot"
        elif market.linear:
            return "linear"
        elif market.inverse:
            return "inverse"
        else:
            raise ValueError(f"Unsupported market type: {market.type}")

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
            elif "tickers" in ws_msg.topic:
                self._handle_ticker(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_ticker(self, raw: bytes):
        msg: BybitWsTickerMsg = self._ws_msg_ticker_decoder.decode(raw)
        id = msg.data.symbol + self.market_type
        symbol = self._market_id[id]

        ticker = self._ticker[symbol]
        ticker.parse_ticker(msg)

        funding_rate = FundingRate(
            exchange=self._exchange_id,
            symbol=symbol,
            rate=float(ticker.fundingRate),
            timestamp=msg.ts,
            next_funding_time=int(ticker.nextFundingTime),
        )

        index_price = IndexPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=ticker.indexPrice,
            timestamp=msg.ts,
        )

        mark_price = MarkPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=ticker.markPrice,
            timestamp=msg.ts,
        )

        self._msgbus.publish(topic="funding_rate", msg=funding_rate)
        self._msgbus.publish(topic="index_price", msg=index_price)
        self._msgbus.publish(topic="mark_price", msg=mark_price)

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
                side=BybitEnumParser.parse_order_side(d.S),
            )
            self._msgbus.publish(topic="trade", msg=trade)

    def _handle_orderbook(self, raw: bytes):
        msg: BybitWsOrderbookDepthMsg = self._ws_msg_orderbook_decoder.decode(raw)
        id = msg.data.s + self.market_type
        symbol = self._market_id[id]
        res = self._bookl1_orderbook[symbol].parse_orderbook_depth(msg, levels=1)

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
        res = self._bookl2_orderbook[symbol].parse_orderbook_depth(msg, levels=50)

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

    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        category = self._get_category(market)
        id = market.id
        ticker_response = self._api_client.get_v5_market_tickers(
            category=category, symbol=id
        )
        for ticker in ticker_response.result.list:
            return Ticker(
                exchange=self._exchange_id,
                symbol=symbol,
                last_price=float(ticker.lastPrice),
                timestamp=ticker_response.time,
                volume=float(ticker.volume24h),
                volumeCcy=float(ticker.turnover24h),
            )

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        if self._account_type.is_spot:
            category = "spot"
        elif self._account_type.is_linear:
            category = "linear"
        elif self._account_type.is_inverse:
            category = "inverse"
        ticker_response = self._api_client.get_v5_market_tickers(
            category=category,
        )
        tickers = {}
        for ticker in ticker_response.result.list:
            id = ticker.symbol + self.market_type
            symbol = self._market_id.get(id)
            if not symbol:
                continue
            tickers[symbol] = Ticker(
                exchange=self._exchange_id,
                symbol=symbol,
                last_price=float(ticker.lastPrice),
                timestamp=ticker_response.time,
                volume=float(ticker.volume24h),
                volumeCcy=float(ticker.turnover24h),
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
        if market.spot:
            raise ValueError("Spot market is not supported for index klines")
        category = self._get_category(market)
        id = market.id
        bybit_interval = BybitEnumParser.to_bybit_kline_interval(interval)
        all_klines: list[Kline] = []
        seen_timestamps: set[int] = set()
        prev_start_time: int | None = None

        while True:
            # Check for infinite loop condition
            if prev_start_time is not None and prev_start_time == start_time:
                break
            prev_start_time = start_time

            klines_response: BybitIndexKlineResponse = (
                self._api_client.get_v5_market_index_price_kline(
                    category=category,
                    symbol=id,
                    interval=bybit_interval.value,
                    limit=1000,
                    start=start_time,
                    end=end_time,
                )
            )

            # Sort klines by start time and filter out duplicates
            response_klines = sorted(
                klines_response.result.list, key=lambda k: int(k.startTime)
            )
            klines: list[Kline] = [
                self._handle_index_candlesticks(
                    symbol=symbol,
                    interval=interval,
                    kline=kline,
                    timestamp=klines_response.time,
                )
                for kline in response_klines
                if int(kline.startTime) not in seen_timestamps
            ]

            all_klines.extend(klines)
            seen_timestamps.update(int(kline.startTime) for kline in response_klines)

            # If no new klines were found, break
            if not klines:
                break

            # Update the start_time to fetch the next set of bars
            start_time = int(response_klines[-1].startTime) + 1

            # No more bars to fetch if we've reached the end time
            if end_time is not None and start_time >= end_time:
                break

        # If limit is specified, return the last 'limit' number of klines
        if limit is not None and len(all_klines) > limit:
            all_klines = all_klines[-limit:]

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
        category = self._get_category(market)
        id = market.id
        bybit_interval = BybitEnumParser.to_bybit_kline_interval(interval)
        all_klines: list[Kline] = []
        seen_timestamps: set[int] = set()
        prev_start_time: int | None = None

        while True:
            # Check for infinite loop condition
            if prev_start_time is not None and prev_start_time == start_time:
                break
            prev_start_time = start_time

            klines_response: BybitKlineResponse = self._api_client.get_v5_market_kline(
                category=category,
                symbol=id,
                interval=bybit_interval.value,
                limit=1000,
                start=start_time,
                end=end_time,
            )

            # Sort klines by start time and filter out duplicates
            response_klines = sorted(
                klines_response.result.list, key=lambda k: int(k.startTime)
            )
            klines: list[Kline] = [
                self._handle_candlesticks(
                    symbol=symbol,
                    interval=interval,
                    kline=kline,
                    timestamp=klines_response.time,
                )
                for kline in response_klines
                if int(kline.startTime) not in seen_timestamps
            ]

            all_klines.extend(klines)
            seen_timestamps.update(int(kline.startTime) for kline in response_klines)

            # If no new klines were found, break
            if not klines:
                break

            # Update the start_time to fetch the next set of bars
            start_time = int(response_klines[-1].startTime) + 1

            # No more bars to fetch if we've reached the end time
            if end_time is not None and start_time >= end_time:
                break

        # If limit is specified, return the last 'limit' number of klines
        if limit is not None and len(all_klines) > limit:
            all_klines = all_klines[-limit:]

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
                "turnover",
                "confirm",
            ],
        )
        return kline_list

    async def subscribe_funding_rate(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_ticker(symbols)

    async def unsubscribe_funding_rate(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.unsubscribe_ticker(symbols)

    async def subscribe_index_price(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_ticker(symbols)

    async def unsubscribe_index_price(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.unsubscribe_ticker(symbols)

    async def subscribe_mark_price(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.subscribe_ticker(symbols)

    async def unsubscribe_mark_price(self, symbol: str):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.unsubscribe_ticker(symbols)

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

    async def unsubscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.unsubscribe_order_book(symbols, depth=1)

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

    async def unsubscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        await self._ws_client.unsubscribe_trade(symbols)

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

    async def unsubscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        interval = BybitEnumParser.to_bybit_kline_interval(interval)
        await self._ws_client.unsubscribe_kline(symbols, interval)

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

    async def unsubscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
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

        await self._ws_client.unsubscribe_order_book(symbols, depth=50)

    def _handle_index_candlesticks(
        self,
        symbol: str,
        interval: KlineInterval,
        kline: BybitIndexKlineResponseArray,
        timestamp: int,
    ) -> Kline:
        local_timestamp = self._clock.timestamp_ms()
        confirm = (
            True
            if local_timestamp >= int(kline.startTime) + interval.seconds * 1000 - 1
            else False
        )
        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.openPrice),
            high=float(kline.highPrice),
            low=float(kline.lowPrice),
            close=float(kline.closePrice),
            start=int(kline.startTime),
            timestamp=timestamp,
            confirm=confirm,
        )

    def _handle_candlesticks(
        self,
        symbol: str,
        interval: KlineInterval,
        kline: BybitKlineResponseArray,
        timestamp: int,
    ) -> Kline:
        local_timestamp = self._clock.timestamp_ms()
        confirm = (
            True
            if local_timestamp >= int(kline.startTime) + interval.seconds * 1000 - 1
            else False
        )
        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.openPrice),
            high=float(kline.highPrice),
            low=float(kline.lowPrice),
            close=float(kline.closePrice),
            volume=float(kline.volume),
            start=int(kline.startTime),
            turnover=float(kline.turnover),
            timestamp=timestamp,
            confirm=confirm,
        )


class BybitPrivateConnector(PrivateConnector):
    _account_type: BybitAccountType
    _market: Dict[str, BybitMarket]
    _market_id: Dict[str, str]
    _api_client: BybitApiClient
    _oms: BybitOrderManagementSystem

    def __init__(
        self,
        account_type: BybitAccountType,
        exchange: BybitExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret:
            raise ValueError("API key and secret are required for private endpoints")

        if account_type not in {
            BybitAccountType.UNIFIED,
            BybitAccountType.UNIFIED_TESTNET,
        }:
            raise ValueError(
                "Please using `BybitAccountType.UNIFIED` or `BybitAccountType.UNIFIED_TESTNET` in `PrivateConnector`"
            )

        api_client = BybitApiClient(
            clock=clock,
            api_key=exchange.api_key,
            secret=exchange.secret,
            testnet=account_type.is_testnet,
            enable_rate_limit=enable_rate_limit,
            **kwargs,
        )

        oms = BybitOrderManagementSystem(
            account_type=account_type,
            api_key=exchange.api_key,
            secret=exchange.secret,
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
        await self._oms._ws_client.subscribe_order()
        await self._oms._ws_client.subscribe_position()
        await self._oms._ws_client.subscribe_wallet()

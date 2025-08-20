import asyncio
import msgspec
import sys
from typing import Dict, List
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.constants import (
    KlineInterval,
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
    KlineList,
    Ticker,
)
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.binance.schema import BinanceMarket
from nexustrader.exchange.binance.rest_api import BinanceApiClient
from nexustrader.exchange.binance.constants import BinanceAccountType
from nexustrader.exchange.binance.websockets import BinanceWSClient
from nexustrader.exchange.binance.exchange import BinanceExchangeManager
from nexustrader.exchange.binance.oms import BinanceOrderManagementSystem
from nexustrader.exchange.binance.constants import (
    BinanceWsEventType,
    BinanceEnumParser,
)
from nexustrader.exchange.binance.schema import (
    BinanceResponseKline,
    BinanceIndexResponseKline,
    BinanceWsMessageGeneral,
    BinanceTradeData,
    BinanceSpotBookTicker,
    BinanceFuturesBookTicker,
    BinanceKline,
    BinanceMarkPrice,
    BinanceResultId,
    BinanceSpotOrderBookMsg,
    BinanceFuturesOrderBookMsg,
)
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager


class BinancePublicConnector(PublicConnector):
    _ws_client: BinanceWSClient
    _account_type: BinanceAccountType
    _market: Dict[str, BinanceMarket]
    _market_id: Dict[str, str]
    _api_client: BinanceApiClient

    def __init__(
        self,
        account_type: BinanceAccountType,
        exchange: BinanceExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
    ):
        if not account_type.is_spot and not account_type.is_future:
            raise ValueError(
                f"BinanceAccountType.{account_type.value} is not supported for Binance Public Connector"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BinanceWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
                custom_url=custom_url,
                ws_suffix="/stream",
            ),
            msgbus=msgbus,
            clock=clock,
            api_client=BinanceApiClient(
                clock=clock,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )
        self._ws_general_decoder = msgspec.json.Decoder(BinanceWsMessageGeneral)
        self._ws_trade_decoder = msgspec.json.Decoder(BinanceTradeData)
        self._ws_spot_book_ticker_decoder = msgspec.json.Decoder(BinanceSpotBookTicker)
        self._ws_futures_book_ticker_decoder = msgspec.json.Decoder(
            BinanceFuturesBookTicker
        )
        self._ws_kline_decoder = msgspec.json.Decoder(BinanceKline)
        self._ws_mark_price_decoder = msgspec.json.Decoder(BinanceMarkPrice)
        self._ws_result_id_decoder = msgspec.json.Decoder(BinanceResultId)

        self._ws_spot_depth_decoder = msgspec.json.Decoder(BinanceSpotOrderBookMsg)
        self._ws_futures_depth_decoder = msgspec.json.Decoder(
            BinanceFuturesOrderBookMsg
        )

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"
        else:
            raise ValueError(
                f"Unsupported BinanceAccountType.{self._account_type.value}"
            )

    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        if market.spot:
            ticker_response = self._api_client.get_api_v3_ticker_24hr(symbol=market.id)[
                0
            ]
        elif market.linear:
            ticker_response = self._api_client.get_fapi_v1_ticker_24hr(
                symbol=market.id
            )[0]
        elif market.inverse:
            ticker_response = self._api_client.get_dapi_v1_ticker_24hr(
                symbol=market.id
            )[0]
        ticker = Ticker(
            exchange=self._exchange_id,
            symbol=symbol,
            last_price=float(ticker_response.lastPrice),
            volume=float(ticker_response.volume),
            volumeCcy=float(
                ticker_response.quoteVolume or ticker_response.baseVolume or 0.0
            ),
            timestamp=self._clock.timestamp_ms(),
        )
        return ticker

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        all_tickers: Dict[str, Ticker] = {}
        if self._account_type.is_spot:
            all_tickers_response = self._api_client.get_api_v3_ticker_24hr()
        elif self._account_type.is_linear:
            all_tickers_response = self._api_client.get_fapi_v1_ticker_24hr()
        elif self._account_type.is_inverse:
            all_tickers_response = self._api_client.get_dapi_v1_ticker_24hr()
        for ticker_response in all_tickers_response:
            id = ticker_response.symbol
            symbol = self._market_id.get(f"{id}{self.market_type}")
            if symbol not in self._market:
                continue

            all_tickers[symbol] = Ticker(
                exchange=self._exchange_id,
                symbol=symbol,
                last_price=float(ticker_response.lastPrice),
                volume=float(ticker_response.volume),
                volumeCcy=float(
                    ticker_response.quoteVolume or ticker_response.baseVolume or 0.0
                ),
                timestamp=self._clock.timestamp_ms(),
            )
        return all_tickers

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        bnc_interval = BinanceEnumParser.to_binance_kline_interval(interval)

        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        if market.linear:
            query_klines = self._api_client.get_fapi_v1_index_price_klines
        elif market.inverse:
            query_klines = self._api_client.get_dapi_v1_index_price_klines
        else:
            raise ValueError(f"Unsupported {market.type} market")

        end_time_ms = int(end_time) if end_time is not None else sys.maxsize
        limit = int(limit) if limit is not None else 500
        all_klines: list[Kline] = []
        while True:
            klines_response: list[BinanceIndexResponseKline] = query_klines(
                pair=market.id,
                interval=bnc_interval.value,
                limit=limit,
                startTime=start_time,
                endTime=end_time,
            )
            klines: list[Kline] = [
                self._parse_index_kline_response(
                    symbol=symbol, interval=interval, kline=kline
                )
                for kline in klines_response
            ]
            all_klines.extend(klines)

            # Update the start_time to fetch the next set of bars
            if klines:
                next_start_time = klines[-1].start + 1
            else:
                # Handle the case when klines is empty
                break

            # No more bars to fetch
            if (limit and len(klines) < limit) or next_start_time >= end_time_ms:
                break

            start_time = next_start_time

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
        bnc_interval = BinanceEnumParser.to_binance_kline_interval(interval)

        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        if market.spot:
            query_klines = self._api_client.get_api_v3_klines
        elif market.linear:
            query_klines = self._api_client.get_fapi_v1_klines
        elif market.inverse:
            query_klines = self._api_client.get_dapi_v1_klines
        else:
            raise ValueError(f"Unsupported {market.type} market")

        end_time_ms = int(end_time) if end_time is not None else sys.maxsize
        limit = int(limit) if limit is not None else 500
        all_klines: list[Kline] = []
        while True:
            klines_response: list[BinanceResponseKline] = query_klines(
                symbol=market.id,
                interval=bnc_interval.value,
                limit=limit,
                startTime=start_time,
                endTime=end_time,
            )
            klines: list[Kline] = [
                self._parse_kline_response(
                    symbol=symbol, interval=interval, kline=kline
                )
                for kline in klines_response
            ]
            all_klines.extend(klines)

            # Update the start_time to fetch the next set of bars
            if klines:
                next_start_time = klines[-1].start + 1
            else:
                # Handle the case when klines is empty
                break

            # No more bars to fetch
            if (limit and len(klines) < limit) or next_start_time >= end_time_ms:
                break

            start_time = next_start_time

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
                "taker_volume",
                "taker_quote_volume",
                "confirm",
            ],
        )
        return kline_list

    async def subscribe_funding_rate(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(
            symbols
        )  # NOTE: funding rate is in mark price

    async def subscribe_index_price(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(
            symbols
        )  # NOTE: index price is in mark price

    async def subscribe_mark_price(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(symbols)

    async def subscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_trade(symbols)

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)
        await self._ws_client.subscribe_book_ticker(symbols)

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)
        await self._ws_client.subscribe_partial_book_depth(symbols, int(level.value))

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        interval = BinanceEnumParser.to_binance_kline_interval(interval)

        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_kline(symbols, interval)

    def _ws_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_general_decoder.decode(raw)
            if msg.data.e:
                match msg.data.e:
                    case BinanceWsEventType.TRADE:
                        self._parse_trade(raw)
                    case BinanceWsEventType.BOOK_TICKER:
                        self._parse_futures_book_ticker(raw)
                    case BinanceWsEventType.KLINE:
                        self._parse_kline(raw)
                    case BinanceWsEventType.MARK_PRICE_UPDATE:
                        self._parse_mark_price(raw)
                    case BinanceWsEventType.DEPTH_UPDATE:
                        self._parse_futures_depth(raw)

            elif msg.data.u:
                # NOTE: spot book ticker doesn't have "e" key. FUCK BINANCE
                self._parse_spot_book_ticker(raw)
            else:
                # NOTE: spot partial depth doesn't have "e" and "u" keys
                self._parse_spot_depth(raw)
        except msgspec.DecodeError as e:
            res = self._ws_result_id_decoder.decode(raw)
            if res.id:
                return
            self._log.error(f"Error decoding message: {str(raw)} {str(e)}")

    def _parse_spot_depth(self, raw: bytes):
        res = self._ws_spot_depth_decoder.decode(raw)
        stream = res.stream
        id = stream.split("@")[0].upper() + self.market_type
        symbol = self._market_id[id]
        depth = res.data
        bids = [b.parse_to_book_order_data() for b in depth.bids]
        asks = [a.parse_to_book_order_data() for a in depth.asks]
        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_futures_depth(self, raw: bytes):
        res = self._ws_futures_depth_decoder.decode(raw)
        id = res.data.s + self.market_type
        symbol = self._market_id[id]
        depth = res.data
        bids = [b.parse_to_book_order_data() for b in depth.b]
        asks = [a.parse_to_book_order_data() for a in depth.a]
        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_index_kline_response(
        self, symbol: str, interval: KlineInterval, kline: BinanceIndexResponseKline
    ) -> Kline:
        timestamp = self._clock.timestamp_ms()

        if kline.close_time > timestamp:
            confirm = False
        else:
            confirm = True

        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.open),
            high=float(kline.high),
            low=float(kline.low),
            close=float(kline.close),
            start=kline.open_time,
            timestamp=timestamp,
            confirm=confirm,
        )

    def _parse_kline_response(
        self, symbol: str, interval: KlineInterval, kline: BinanceResponseKline
    ) -> Kline:
        timestamp = self._clock.timestamp_ms()

        if kline.close_time > timestamp:
            confirm = False
        else:
            confirm = True

        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.open),
            high=float(kline.high),
            low=float(kline.low),
            close=float(kline.close),
            volume=float(kline.volume),
            quote_volume=float(kline.asset_volume),
            taker_volume=float(kline.taker_base_volume),
            taker_quote_volume=float(kline.taker_quote_volume),
            start=kline.open_time,
            timestamp=timestamp,
            confirm=confirm,
        )

    def _parse_kline(self, raw: bytes) -> Kline:
        res = self._ws_kline_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]
        interval = BinanceEnumParser.parse_kline_interval(res.k.i)
        ticker = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(res.k.o),
            high=float(res.k.h),
            low=float(res.k.l),
            close=float(res.k.c),
            volume=float(res.k.v),
            quote_volume=float(res.k.q),
            taker_volume=float(res.k.V),
            taker_quote_volume=float(res.k.Q),
            start=res.k.t,
            timestamp=res.E,
            confirm=res.k.x,
        )
        self._msgbus.publish(topic="kline", msg=ticker)

    def _parse_trade(self, raw: bytes) -> Trade:
        res = self._ws_trade_decoder.decode(raw).data

        id = res.s + self.market_type
        symbol = self._market_id[id]  # map exchange id to ccxt symbol

        trade = Trade(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.p),
            size=float(res.q),
            timestamp=res.T,
        )
        self._msgbus.publish(topic="trade", msg=trade)

    def _parse_spot_book_ticker(self, raw: bytes) -> BookL1:
        res = self._ws_spot_book_ticker_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=float(res.b),
            ask=float(res.a),
            bid_size=float(res.B),
            ask_size=float(res.A),
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _parse_futures_book_ticker(self, raw: bytes) -> BookL1:
        res = self._ws_futures_book_ticker_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]
        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=float(res.b),
            ask=float(res.a),
            bid_size=float(res.B),
            ask_size=float(res.A),
            timestamp=res.E,
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _parse_mark_price(self, raw: bytes):
        res = self._ws_mark_price_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]

        mark_price = MarkPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.p),
            timestamp=res.E,
        )

        funding_rate = FundingRate(
            exchange=self._exchange_id,
            symbol=symbol,
            rate=float(res.r),
            timestamp=res.E,
            next_funding_time=res.T,
        )

        index_price = IndexPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.i),
            timestamp=res.E,
        )
        self._msgbus.publish(topic="funding_rate", msg=funding_rate)
        self._msgbus.publish(topic="mark_price", msg=mark_price)
        self._msgbus.publish(topic="index_price", msg=index_price)


class BinancePrivateConnector(PrivateConnector):
    _account_type: BinanceAccountType
    _market: Dict[str, BinanceMarket]
    _api_client: BinanceApiClient
    _oms: BinanceOrderManagementSystem

    def __init__(
        self,
        account_type: BinanceAccountType,
        exchange: BinanceExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        # Initialize API client first
        api_client = BinanceApiClient(
            clock=clock,
            api_key=exchange.api_key,
            secret=exchange.secret,
            testnet=account_type.is_testnet,
            enable_rate_limit=enable_rate_limit,
            **kwargs,
        )

        # Initialize OMS with the API client
        oms = BinanceOrderManagementSystem(
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

    async def _start_user_data_stream(self):
        if self._account_type.is_spot:
            res = await self._api_client.post_api_v3_user_data_stream()
        elif self._account_type.is_margin:
            res = await self._api_client.post_sapi_v1_user_data_stream()
        elif self._account_type.is_linear:
            res = await self._api_client.post_fapi_v1_listen_key()
        elif self._account_type.is_inverse:
            res = await self._api_client.post_dapi_v1_listen_key()
        elif self._account_type.is_portfolio_margin:
            res = await self._api_client.post_papi_v1_listen_key()
        return res.listenKey

    async def _keep_alive_listen_key(self, listen_key: str):
        if self._account_type.is_spot:
            await self._api_client.put_api_v3_user_data_stream(listen_key=listen_key)
        elif self._account_type.is_margin:
            await self._api_client.put_sapi_v1_user_data_stream(listen_key=listen_key)
        elif self._account_type.is_linear:
            await self._api_client.put_fapi_v1_listen_key()
        elif self._account_type.is_inverse:
            await self._api_client.put_dapi_v1_listen_key()
        elif self._account_type.is_portfolio_margin:
            await self._api_client.put_papi_v1_listen_key()

    async def _keep_alive_user_data_stream(
        self, listen_key: str, interval: int = 20, max_retry: int = 5
    ):
        retry_count = 0
        while retry_count < max_retry:
            await asyncio.sleep(60 * interval)
            try:
                await self._keep_alive_listen_key(listen_key)
                retry_count = 0  # Reset retry count on successful keep-alive
            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(f"Failed to keep alive listen key: {error_msg}")
                retry_count += 1
                if retry_count < max_retry:
                    await asyncio.sleep(5)
                else:
                    self._log.error(
                        f"Max retries ({max_retry}) reached. Stopping keep-alive attempts."
                    )
                    break

    async def connect(self):
        if self._oms._ws_api_client:
            await self._oms._ws_api_client.connect()

        listen_key = await self._start_user_data_stream()

        if listen_key:
            self._task_manager.create_task(
                self._keep_alive_user_data_stream(listen_key)
            )
            await self._oms._ws_client.subscribe_user_data_stream(listen_key)
        else:
            raise RuntimeError("Failed to start user data stream")

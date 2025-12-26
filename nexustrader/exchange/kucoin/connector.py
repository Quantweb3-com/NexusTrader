import msgspec
from typing import Dict, List

from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.constants import KlineInterval
from nexustrader.schema import KlineList, Ticker, BookOrderData
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.entity import TaskManager

from nexustrader.exchange.kucoin.exchange import KuCoinExchangeManager
from nexustrader.exchange.kucoin.websockets import KucoinWSClient
from nexustrader.exchange.kucoin.constants import KucoinAccountType, KucoinWsEventType
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient
from nexustrader.exchange.kucoin.oms import KucoinOrderManagementSystem

from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    BookL2,
    KlineList,
    Ticker,
)
from nexustrader.constants import (
    KlineInterval,
    OrderSide,
)

from nexustrader.exchange.kucoin.schema import (
    KucoinWsTradeMessage,
    KucoinWsKlinesMessage,
    KucoinWsSpotBook1Message,
    KucoinWsBook2Message,
)

class KucoinPublicConnector(PublicConnector):
    _ws_client: KucoinWSClient
    _account_type: KucoinAccountType
    _market: Dict[str, object]
    _market_id: Dict[str, str]
    _api_client: KucoinApiClient

    def __init__(
        self,
        account_type: KucoinAccountType,
        exchange: KuCoinExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        custom_url: str | None = None,
        token: str | None = None,
        enable_rate_limit: bool = True,
        handler = None,
    ):
        if not account_type.is_spot and account_type != KucoinAccountType.FUTURES:
            raise ValueError(
                f"KucoinAccountType.{account_type.value} is not supported for Kucoin Public Connector"
            )
        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=KucoinWSClient(
                account_type=account_type,
                handler= handler or self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
                custom_url=custom_url,
                token=token,
            ),
            msgbus=msgbus,
            clock=clock,
            api_client=KucoinApiClient(clock=clock, enable_rate_limit=enable_rate_limit),
            task_manager=task_manager,
        )

        self._ws_general_decoder = msgspec.json.Decoder(dict)
        self._ws_trade_decoder = msgspec.json.Decoder(KucoinWsTradeMessage)
        self._ws_spot_book_l1_decoder = msgspec.json.Decoder(KucoinWsSpotBook1Message)
        self._ws_book_l2_decoder = msgspec.json.Decoder(KucoinWsBook2Message)
        self._ws_kline_decoder = msgspec.json.Decoder(KucoinWsKlinesMessage)

    def _interval_to_kucoin_str(self, interval: KlineInterval) -> str:
        """Convert `KlineInterval` to KuCoin-supported interval strings for WS.

        Supported: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 8hour, 12hour, 1day, 1week.
        """
        mapping = {
            KlineInterval.MINUTE_1: "1min",
            KlineInterval.MINUTE_3: "3min",
            KlineInterval.MINUTE_5: "5min",
            KlineInterval.MINUTE_15: "15min",
            KlineInterval.MINUTE_30: "30min",
            KlineInterval.HOUR_1: "1hour",
            KlineInterval.HOUR_2: "2hour",
            KlineInterval.HOUR_4: "4hour",
            KlineInterval.HOUR_6: "6hour",
            KlineInterval.HOUR_8: "8hour",
            KlineInterval.HOUR_12: "12hour",
            KlineInterval.DAY_1: "1day",
            KlineInterval.WEEK_1: "1week",
        }
        val = mapping.get(interval)
        if not val:
            raise ValueError(f"Unsupported interval {interval} for KuCoin WS kline")
        return val

    def request_ticker(self, symbol: str) -> Ticker:
        raise NotImplementedError("Implement KuCoin ticker via KucoinApiClient")

    def request_all_tickers(self) -> Dict[str, Ticker]:
        raise NotImplementedError("Implement KuCoin all tickers via KucoinApiClient")

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        raise NotImplementedError("Implement KuCoin index klines via KucoinApiClient")

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

        # Interval mapping: spot uses string types; futures uses granularity (minutes)
        spot_type_map = {
            KlineInterval.MINUTE_1: "1min",
            KlineInterval.MINUTE_3: "3min",
            KlineInterval.MINUTE_5: "5min",
            KlineInterval.MINUTE_15: "15min",
            KlineInterval.MINUTE_30: "30min",
            KlineInterval.HOUR_1: "1hour",
            KlineInterval.HOUR_2: "2hour",
            KlineInterval.HOUR_4: "4hour",
            KlineInterval.HOUR_6: "6hour",
            KlineInterval.HOUR_8: "8hour",
            KlineInterval.HOUR_12: "12hour",
            KlineInterval.DAY_1: "1day",
            KlineInterval.WEEK_1: "1week",
            KlineInterval.MONTH_1: "1month",
        }

        futures_granularity_map = {
            KlineInterval.MINUTE_1: 1,
            KlineInterval.MINUTE_5: 5,
            KlineInterval.MINUTE_15: 15,
            KlineInterval.MINUTE_30: 30,
            KlineInterval.HOUR_1: 60,
            KlineInterval.HOUR_2: 120,
            KlineInterval.HOUR_4: 240,
            KlineInterval.HOUR_8: 480,
            KlineInterval.HOUR_12: 720,
            KlineInterval.DAY_1: 1440,
            KlineInterval.WEEK_1: 10080,
        }

        all_klines: list[Kline] = []

        # Resolve exchange-specific symbol id
        market_id = market.id

        end_bound = int(end_time) if end_time is not None else None
        next_start = int(start_time) if start_time is not None else None

        if self._account_type == KucoinAccountType.SPOT:
            type_str = spot_type_map.get(interval)
            if not type_str:
                raise ValueError(f"Unsupported interval {interval} for KuCoin spot")

            remaining = int(limit) if limit is not None else None
            while True:
                resp = self._api_client.get_api_v1_market_candles(
                    symbol=market_id,
                    type=type_str,
                    startAt=next_start,
                    endAt=end_bound,
                )
                entries = resp.data or []
                if not entries:
                    break

                for e in entries:
                    if isinstance(e, list):
                        t, o, c, h, l, v, _turnover = e
                        ts = int(t)
                    else:
                        ts = int(getattr(e, "time"))
                        o = getattr(e, "open")
                        c = getattr(e, "close")
                        h = getattr(e, "high")
                        l = getattr(e, "low")
                        v = getattr(e, "volume")

                    # Convert seconds to ms if needed
                    start_ms = ts * 1000 if ts < 10**12 else ts

                    k = Kline(
                        exchange=self._exchange_id,
                        symbol=symbol,
                        interval=interval,
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=float(v),
                        start=start_ms,
                        timestamp=self._clock.timestamp_ms(),
                        confirm=True,
                    )
                    all_klines.append(k)

                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            break

                if remaining is not None and remaining <= 0:
                    break

                # Advance paging window
                if entries:
                    last_ts = int(entries[-1][0] if isinstance(entries[-1], list) else entries[-1].time)
                    next_start = last_ts + 1
                else:
                    break

        elif self._account_type == KucoinAccountType.FUTURES:
            gran = futures_granularity_map.get(interval)
            if gran is None:
                raise ValueError(f"Unsupported interval {interval} for KuCoin futures")

            remaining = int(limit) if limit is not None else None
            while True:
                # Futures API expects seconds for from/to
                from_sec = None if next_start is None else (next_start // 1000)
                to_sec = None if end_bound is None else (end_bound // 1000)

                resp = self._api_client.get_fapi_v1_kline_query(
                    symbol=market_id,
                    granularity=gran,
                    from_=from_sec,
                    to=to_sec,
                )

                entries = resp.data or []
                if not entries:
                    break

                for e in entries:
                    if isinstance(e, list):
                        t, o, c, h, l, v, _turnover = e
                        ts = int(t)
                    else:
                        ts = int(getattr(e, "time"))
                        o = getattr(e, "open")
                        c = getattr(e, "close")
                        h = getattr(e, "high")
                        l = getattr(e, "low")
                        v = getattr(e, "volume")

                    start_ms = ts * 1000 if ts < 10**12 else ts

                    k = Kline(
                        exchange=self._exchange_id,
                        symbol=symbol,
                        interval=interval,
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=float(v),
                        start=start_ms,
                        timestamp=self._clock.timestamp_ms(),
                        confirm=True,
                    )
                    all_klines.append(k)

                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            break

                if remaining is not None and remaining <= 0:
                    break

                if entries:
                    last_ts = int(entries[-1][0] if isinstance(entries[-1], list) else entries[-1].time)
                    last_ms = last_ts * 1000 if last_ts < 10**12 else last_ts
                    next_start = last_ms + 1
                else:
                    break

        else:
            raise ValueError("Only SPOT and FUTURES are supported for KuCoin klines")

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
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.subscribe_trade(symbols)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.subscribe_futures_trade(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for trade subscription")

    async def unsubscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.unsubscribe_trade(symbols)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.unsubscribe_futures_trade(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for trade subscription")

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.subscribe_book_l1(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for bookl1 subscription")

    async def unsubscribe_bookl1(self, symbol: str | List[str]):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.unsubscribe_book_l1(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for bookl1 unsubscription")

    async def subscribe_bookl2(self, symbol: str | List[str]):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.subscribe_book_l5(symbols)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.subscribe_futures_book_l5(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for bookl2 subscription")

    async def unsubscribe_bookl2(self, symbol: str | List[str]):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.unsubscribe_book_l5(symbols)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.unsubscribe_futures_book_l5(symbols)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for bookl2 unsubscription")

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        interval_str = self._interval_to_kucoin_str(interval)
        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.subscribe_kline(symbols, interval_str)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.subscribe_futures_kline(symbols, interval_str)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for trade subscription")

    async def unsubscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        symbols: List[str] = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if not market:
                raise ValueError(f"Symbol {s} formated wrongly, or not supported")
            symbols.append(market.id)

        interval_str = self._interval_to_kucoin_str(interval)
        if self._account_type == KucoinAccountType.SPOT:
            await self._ws_client.unsubscribe_kline(symbols, interval_str)
        elif self._account_type == KucoinAccountType.FUTURES:
            await self._ws_client.unsubscribe_futures_kline(symbols, interval_str)
        else:
            raise ValueError(f"Account type {self._account_type} not supported for trade subscription")

    async def subscribe_funding_rate(self, symbol: str | List[str]):
        """Subscribe to the funding rate data"""
        raise NotImplementedError

    async def unsubscribe_funding_rate(self, symbol: str | List[str]):
        """Unsubscribe from the funding rate data"""
        raise NotImplementedError

    async def subscribe_index_price(self, symbol: str | List[str]):
        """Subscribe to the index price data"""
        raise NotImplementedError

    async def unsubscribe_index_price(self, symbol: str | List[str]):
        """Unsubscribe from the index price data"""
        raise NotImplementedError

    async def subscribe_mark_price(self, symbol: str | List[str]):
        """Subscribe to the mark price data"""
        raise NotImplementedError

    async def unsubscribe_mark_price(self, symbol: str | List[str]):
        """Unsubscribe from the mark price data"""
        raise NotImplementedError

    def _ws_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_general_decoder.decode(raw)
            subject = msg.get("subject")
            if subject in (KucoinWsEventType.SPOTTRADE.value, KucoinWsEventType.FUTURESTRADE.value):
                self._parse_trade(raw)
            elif subject == KucoinWsEventType.BOOK_L1.value:
                self._parse_spot_bookl1(raw)
            elif subject == KucoinWsEventType.BOOK_L2.value:
                self._parse_bookl2(raw)
            elif subject in (KucoinWsEventType.SPOTKLINE.value, KucoinWsEventType.FUTURESKLINE.value):
                self._parse_kline(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {str(e)}")
    
    def _parse_trade(self, raw: bytes) -> Trade:
        msg = self._ws_trade_decoder.decode(raw)
        data = msg.data

        symbol_id = data.symbol
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        side = OrderSide.BUY if (data.side or "").lower() == "buy" else OrderSide.SELL
        price = float(data.price)
        size = float(data.size)

        ts = int(data.ts)
        if ts > 10**13:  # nanoseconds
            ts_ms = ts // 1_000_000
        elif ts > 10**12:  # milliseconds
            ts_ms = ts
        else:  # seconds
            ts_ms = ts * 1000

        trade = Trade(
            exchange=self._exchange_id,
            symbol=symbol,
            price=price,
            size=size,
            timestamp=ts_ms,
            side=side,
        )
        self._msgbus.publish(topic="trade", msg=trade)

    def _parse_spot_bookl1(self, raw: bytes) -> BookL1:
        msg = self._ws_spot_book_l1_decoder.decode(raw)
        data = msg.data
        topic = msg.topic or ""
        symbol_id = topic.split(":", 1)[1] if ":" in topic else None
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        bid = float(data.bids[0]) if data.bids and len(data.bids) >= 1 else 0.0
        bid_size = float(data.bids[1]) if data.bids and len(data.bids) >= 2 else 0.0
        ask = float(data.asks[0]) if data.asks and len(data.asks) >= 1 else 0.0
        ask_size = float(data.asks[1]) if data.asks and len(data.asks) >= 2 else 0.0

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            timestamp=int(data.timestamp),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)
    
    def _parse_bookl2(self, raw: bytes):
        msg = self._ws_book_l2_decoder.decode(raw)
        data = msg.data
        topic = msg.topic or ""
        symbol_id = topic.split(":", 1)[1] if ":" in topic else None
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        bids = [BookOrderData(price=float(b[0]), size=float(b[1])) for b in (data.bids or [])]
        asks = [BookOrderData(price=float(a[0]), size=float(a[1])) for a in (data.asks or [])]

        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=int(data.timestamp),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_kline(self, raw: bytes) -> Kline:
        msg = self._ws_kline_decoder.decode(raw)
        data = msg.data

        # Resolve symbol id
        symbol_id = getattr(data, "symbol", None)
        if not symbol_id:
            topic = msg.topic or ""
            if ":" in topic:
                suffix = topic.split(":", 1)[1]
                symbol_id = suffix.split("_", 1)[0]
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        candles = data.candles
        if not candles or len(candles) < 6:
            return
        t = int(candles[0])
        start_ms = t * 1000 if t < 10**12 else t
        o = float(candles[1])
        c = float(candles[2])
        h = float(candles[3])
        l = float(candles[4])
        v = float(candles[5]) if len(candles) > 5 else 0.0

        # Parse interval from topic suffix
        interval_str = ""
        topic = msg.topic or ""
        if ":" in topic and "_" in topic:
            try:
                interval_str = topic.split(":", 1)[1].split("_", 1)[1]
            except Exception:
                interval_str = ""
        interval_map = {
            "1s": KlineInterval.SECOND_1,
            "1m": KlineInterval.MINUTE_1,
            "3m": KlineInterval.MINUTE_3,
            "5m": KlineInterval.MINUTE_5,
            "15m": KlineInterval.MINUTE_15,
            "30m": KlineInterval.MINUTE_30,
            "1h": KlineInterval.HOUR_1,
            "2h": KlineInterval.HOUR_2,
            "4h": KlineInterval.HOUR_4,
            "6h": KlineInterval.HOUR_6,
            "8h": KlineInterval.HOUR_8,
            "12h": KlineInterval.HOUR_12,
            "1d": KlineInterval.DAY_1,
            "1w": KlineInterval.WEEK_1,
            "1M": KlineInterval.MONTH_1,
            "1min": KlineInterval.MINUTE_1,
            "3min": KlineInterval.MINUTE_3,
            "5min": KlineInterval.MINUTE_5,
            "15min": KlineInterval.MINUTE_15,
            "30min": KlineInterval.MINUTE_30,
            "1hour": KlineInterval.HOUR_1,
            "2hour": KlineInterval.HOUR_2,
            "4hour": KlineInterval.HOUR_4,
            "6hour": KlineInterval.HOUR_6,
            "8hour": KlineInterval.HOUR_8,
            "12hour": KlineInterval.HOUR_12,
            "1day": KlineInterval.DAY_1,
            "1week": KlineInterval.WEEK_1,
            "1month": KlineInterval.MONTH_1,
        }
        interval = interval_map.get(interval_str, KlineInterval.MINUTE_1)

        ticker = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            start=start_ms,
            open=o,
            close=c,
            high=h,
            low=l,
            volume=v,
            timestamp=int(getattr(data, "time", self._clock.timestamp_ms())),
        )
        self._msgbus.publish(topic="kline", msg=ticker)


class KucoinPrivateConnector(PrivateConnector):
    _account_type: KucoinAccountType
    _api_client: KucoinApiClient
    _oms: KucoinOrderManagementSystem

    def __init__(
        self,
        account_type: KucoinAccountType,
        exchange: KuCoinExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret:
            raise ValueError("API key and secret are required for KuCoin private connector")

        api_client = KucoinApiClient(
            api_key=exchange.api_key,
            secret=exchange.secret,
            enable_rate_limit=enable_rate_limit,
            max_retries=kwargs.get("max_retries", 0),
            delay_initial_ms=kwargs.get("delay_initial_ms", 100),
            delay_max_ms=kwargs.get("delay_max_ms", 800),
            backoff_factor=kwargs.get("backoff_factor", 2),
        )

        setattr(api_client, "_passphrase", exchange.config.get("password"))

        oms = KucoinOrderManagementSystem(
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
        )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            api_client=api_client,
            task_manager=task_manager,
            oms=oms,
        )

    async def connect(self):
        if getattr(self._oms, "_ws_api_client", None):
            await self._oms._ws_api_client.connect()


import asyncio  # noqa
import argparse


def _interval_to_enum(interval_str: str) -> KlineInterval:
    """Map common interval strings to `KlineInterval`. Supports spot/futures aliases."""
    mapping = {
        "1s": KlineInterval.SECOND_1,
        "1m": KlineInterval.MINUTE_1,
        "1min": KlineInterval.MINUTE_1,
        "3m": KlineInterval.MINUTE_3,
        "3min": KlineInterval.MINUTE_3,
        "5m": KlineInterval.MINUTE_5,
        "5min": KlineInterval.MINUTE_5,
        "15m": KlineInterval.MINUTE_15,
        "15min": KlineInterval.MINUTE_15,
        "30m": KlineInterval.MINUTE_30,
        "30min": KlineInterval.MINUTE_30,
        "1h": KlineInterval.HOUR_1,
        "1hour": KlineInterval.HOUR_1,
        "2h": KlineInterval.HOUR_2,
        "2hour": KlineInterval.HOUR_2,
        "4h": KlineInterval.HOUR_4,
        "4hour": KlineInterval.HOUR_4,
        "6h": KlineInterval.HOUR_6,
        "6hour": KlineInterval.HOUR_6,
        "8h": KlineInterval.HOUR_8,
        "8hour": KlineInterval.HOUR_8,
        "12h": KlineInterval.HOUR_12,
        "12hour": KlineInterval.HOUR_12,
        "1d": KlineInterval.DAY_1,
        "1day": KlineInterval.DAY_1,
        "1w": KlineInterval.WEEK_1,
        "1week": KlineInterval.WEEK_1,
        "1M": KlineInterval.MONTH_1,
        "1month": KlineInterval.MONTH_1,
    }
    key = (interval_str or "").strip()
    return mapping.get(key, KlineInterval.MINUTE_1)


async def _main_kline_public(args: argparse.Namespace) -> None:
    """CLI runner to test public `subscribe_kline` via `KucoinPublicConnector`."""
    # Core components
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    # Use shared core MessageBus/Clock
    from nexustrader.core.nautilius_core import MessageBus, LiveClock
    from nautilus_trader.model.identifiers import TraderId

    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-KUCOIN"), clock=clock)

    # Exchange and market setup
    exchange = KuCoinExchangeManager()
    exchange.load_markets()
    # Account type
    account_type = KucoinAccountType.FUTURES if getattr(args, "futures", False) else KucoinAccountType.SPOT
    # Ensure input symbols exist in market maps for testing
    from types import SimpleNamespace
    for _sym in [s.upper() for s in getattr(args, "symbols", ["BTC-USDT"])]:
        if _sym not in exchange.market:
            exchange.market[_sym] = SimpleNamespace(
                id=_sym,
                symbol=_sym,
                spot=(account_type == KucoinAccountType.SPOT),
                future=(account_type == KucoinAccountType.FUTURES),
                linear=False,
                inverse=False,
                option=False,
            )
            # Map exchange symbol id to common symbol
            exchange.market_id[_sym] = _sym

    # Build base URL and public token if requested
    token: str | None = getattr(args, "token", None)
    base_url: str = args.url or ("wss://ws-api-futures.kucoin.com" if account_type == KucoinAccountType.FUTURES else "wss://ws-api-spot.kucoin.com")

    if getattr(args, "fetch_token", False):
        client = KucoinApiClient(clock=clock)
        fetched_url = await client.fetch_ws_url(
            futures=(account_type == KucoinAccountType.FUTURES),
            private=False,
        )
        # Parse token and base URL out of fetched URL when possible
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(fetched_url)
            qs = parse_qs(parsed.query)
            token = token or (qs.get("token", [None])[0])
            base_url = parsed._replace(query="", params="").geturl().rstrip("?")
        except Exception:
            base_url = fetched_url

    # Print incoming kline messages
    def _print_kline(k: Kline):
        try:
            print({
                "symbol": k.symbol,
                "interval": k.interval.value if hasattr(k.interval, "value") else str(k.interval),
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
                "start": k.start,
                "ts": k.timestamp,
            })
        except Exception as e:
            print("kline:", k, "error:", e)


    # Wire connector
    connector = KucoinPublicConnector(
        account_type=account_type,
        exchange=exchange,
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
        custom_url=base_url,
        token=token,
        handler=_print_kline,
    )

    msgbus.subscribe(topic="kline", handler=_print_kline)

    # Subscribe
    interval_enum = _interval_to_enum(args.interval)
    symbols = [s.upper() for s in args.symbols]
    await connector.subscribe_kline(symbols, interval_enum)

    try:
        await asyncio.sleep(args.duration)
    finally:
        # Best effort teardown
        try:
            await connector.unsubscribe_kline(symbols, interval_enum)
        except Exception:
            pass
        try:
            connector._ws_client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test KuCoin Public Connector subscribe_kline")
    parser.add_argument("--symbols", nargs="+", default=["BTC-USDT"], help="Symbols e.g. BTC-USDT ETH-USDT")
    parser.add_argument("--interval", default="1m", help="Interval e.g. 1m/5m/1h (spot aliases like 1min allowed)")
    parser.add_argument("--futures", action="store_true", help="Use futures public stream for klines")
    parser.add_argument("--fetch-token", action="store_true", help="Fetch a public WS token via bullet API")
    parser.add_argument("--token", default=None, help="Public WS token to append (optional)")
    parser.add_argument("--url", default=None, help="Custom WS base URL; overridden if --fetch-token is used")
    parser.add_argument("--duration", type=int, default=30, help="Run seconds before exit")

    args = parser.parse_args()
    asyncio.run(_main_kline_public(args))
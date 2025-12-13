import msgspec
from typing import Dict, List

from nexustrader.base import PublicConnector
from nexustrader.constants import KlineInterval
from nexustrader.schema import KlineList, Ticker
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager

from nexustrader.exchange.kucoin.exchange import KuCoinExchangeManager
from nexustrader.exchange.kucoin.websockets import KucoinWSClient
from nexustrader.exchange.kucoin.constants import KucoinAccountType, KucoinWsEventType, KucoinEnumParser
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient

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
        enable_rate_limit: bool = True,
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
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
                custom_url=custom_url,
            ),
            msgbus=msgbus,
            clock=clock,
            api_client=KucoinApiClient(enable_rate_limit=enable_rate_limit),
            task_manager=task_manager,
        )

        # Placeholder decoders if you add typed ws schemas later
        self._ws_general_decoder = msgspec.json.Decoder(object)

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
        raise NotImplementedError("Implement KuCoin klines via KucoinApiClient")


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

        interval_str = interval.value if hasattr(interval, 'value') else str(interval)
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

        interval_str = interval.value if hasattr(interval, 'value') else str(interval)
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
            match msg.data.subject:
                case KucoinWsEventType.SPOTTRADE:
                    self._parse_trade(raw)
                case KucoinWsEventType.FUTURESTRADE:
                    self._parse_trade(raw)
                case KucoinWsEventType.BOOK_L1:
                    self._parse_spot_bookl1(raw)
                case KucoinWsEventType.BOOK_L2:
                    self._parse_bookl2(raw)
                case KucoinWsEventType.SPOTKLINE:
                    self._parse_kline(raw)
                case KucoinWsEventType.FUTURESKLINE:
                    self._parse_kline(raw)
        except msgspec.DecodeError as e:
            res = self._ws_result_id_decoder.decode(raw)
            if res.id:
                return
            self._log.error(f"Error decoding message: {str(raw)} {str(e)}")
    
    def _parse_trade(self, raw: bytes) -> Trade:
        res = self._ws_trade_decoder.decode(raw).data

        id = res.s + self.market_type
        symbol = self._market_id[id]  # map exchange id to ccxt symbol

        trade = Trade(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.price),
            size=float(res.size),
            timestamp=res.time,
            side=OrderSide.SELL if res.m else OrderSide.BUY,
        )
        self._msgbus.publish(topic="trade", msg=trade)

    def _parse_spot_bookl1(self, raw: bytes) -> BookL1:
        res = self._ws_spot_book_l1_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=float(res.bids[0]),
            ask=float(res.asks[0]),
            bid_size=float(res.bids[1]),
            ask_size=float(res.asks[1]),
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)
    
    def _parse_bookl2(self, raw: bytes):
        res = self._ws_spot_depth_decoder.decode(raw)
        stream = res.stream
        id = stream.split("@")[0].upper() + self.market_type
        symbol = self._market_id[id]
        data = res.data
        bids = [b.parse_to_book_order_data() for b in data.bids]
        asks = [a.parse_to_book_order_data() for a in data.asks]
        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_kline(self, raw: bytes) -> Kline:
        res = self._ws_kline_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]
        interval = KucoinEnumParser.parse_kline_interval(res.k.i)
        ticker = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            start=res.candle[0],
            open=float(res.candle[1]),
            close=float(res.candle[2]),
            high=float(res.candle[3]),
            low=float(res.candle[4]),
            volume=float(res.candle[5]),
            timestamp=res.time,
        )
        self._msgbus.publish(topic="kline", msg=ticker)
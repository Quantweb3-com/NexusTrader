import msgspec
from typing import Dict, List
from nexustrader.constants import (
    KlineInterval,
    BookLevel,
)
from nexustrader.core.nautilius_core import (
    MessageBus,
    LiveClock,
)
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    KlineList,
    Ticker,
    BookL1,
    Trade,
    Kline,
)
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidMarket,
    HyperLiquidWsMessageGeneral,
    HyperLiquidWsBboMsg,
    HyperLiquidWsTradeMsg,
    HyperLiquidWsCandleMsg,
)
from nexustrader.exchange.hyperliquid.oms import HyperLiquidOrderManagementSystem
from nexustrader.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hyperliquid.websockets import HyperLiquidWSClient
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidEnumParser,
)
from nexustrader.exchange.hyperliquid.rest_api import HyperLiquidApiClient


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
    _market: Dict[str, HyperLiquidMarket]
    _oms: HyperLiquidOrderManagementSystem

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        exchange: HyperLiquidExchangeManager,
        cache: AsyncCache,
        registry: OrderRegistry,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
        **kwargs,
    ):
        if not exchange.api_key or not exchange.secret:
            raise ValueError(
                "API key and secret must be provided for private connector"
            )

        api_client = HyperLiquidApiClient(
            clock=clock,
            api_key=exchange.api_key,
            secret=exchange.secret,
            testnet=account_type.is_testnet,
            enable_rate_limit=enable_rate_limit,
        )

        oms = HyperLiquidOrderManagementSystem(
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
            max_slippage=kwargs.get("max_slippage", 0.02),
        )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            api_client=api_client,
            task_manager=task_manager,
            oms=oms,
        )

    async def connect(self):
        """Connect to the exchange"""
        await self._oms._ws_api_client.connect()
        await self._oms._ws_client.subscribe_order_updates()
        await self._oms._ws_client.subscribe_user_events()

import msgspec
import asyncio
from typing import Dict, List
from decimal import Decimal
from collections import defaultdict
from nexustrader.error import PositionModeError
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus, LiveClock, setup_nautilus_core
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    BookL1,
    Order,
    Trade,
    Position,
    Kline,
    BookL2,
    BookOrderData,
    FundingRate,
    IndexPrice,
    MarkPrice,
    KlineList,
    BatchOrderSubmit,
    Ticker,
)
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
from nexustrader.exchange.bitget.schema import (
    BitgetOrderCancelResponse,
    BitgetMarket,
    BitgetWsGeneralMsg,
    BitgetBooks1WsMsg,
    BitgetWsArgMsg,
    BitgetWsTradeWsMsg,
    BitgetWsCandleWsMsg,
)
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
from nexustrader.exchange.bitget.websockets import BitgetWSClient
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetKlineInterval,
    BitgetInstType,
    BitgetEnumParser,
)
from nexustrader.exchange.bitget.exchange import BitgetExchangeManager


class BitgetPublicConnector(PublicConnector):
    _inst_type_map = {
        BitgetInstType.SPOT: "spot",
        BitgetInstType.USDC_FUTURES: "linear",
        BitgetInstType.USDT_FUTURES: "linear",
        BitgetInstType.COIN_FUTURES: "inverse",
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
        self._ws_msg_general_decoder = msgspec.json.Decoder(BitgetWsGeneralMsg)
        self._ws_books1_decoder = msgspec.json.Decoder(BitgetBooks1WsMsg)
        self._ws_trade_decoder = msgspec.json.Decoder(BitgetWsTradeWsMsg)
        self._ws_candle_decoder = msgspec.json.Decoder(BitgetWsCandleWsMsg)

    def _get_inst_type(self, market: BitgetMarket):
        if market.spot:
            return "SPOT"
        elif market.linear:
            return "USDT-FUTURES" if market.quote == "USDT" else "USDC-FUTURES"
        elif market.inverse:
            return "COIN-FUTURES"

    def _inst_type_suffix(self, inst_type: BitgetInstType):
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
            elif msg.arg.channel == "books1":
                self._handle_books1_data(raw, msg.arg)
            elif msg.arg.channel == "trade":
                self._handle_trade_data(raw, msg.arg)
            elif "candle" in msg.arg.channel:
                self._handle_candle_data(raw, msg.arg)

            # print(f"Received WebSocket message: {raw}")
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_event_data(self, msg: BitgetWsGeneralMsg):
        if msg.event == "subscribe":
            arg = msg.arg
            subscribe_msg = f"{arg.instType.value}.{arg.channel}.{arg.instId}"
            self._log.debug(f"Subscribed to {subscribe_msg}")
        elif msg.event == "error":
            code = msg.code
            error_msg = msg.msg
            self._log.error(f"Subscribed error {code}: {error_msg}")

    def _handle_candle_data(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_candle_decoder.decode(raw)
        sym_id = f"{arg.instId}_{self._inst_type_suffix(arg.instType)}"
        symbol = self._market_id[sym_id]
        interval = BitgetEnumParser.parse_kline_interval(
            BitgetKlineInterval(arg.channel)
        )
        for data in msg.data:
            kline = Kline(
                exchange=self._exchange_id,
                symbol=symbol,
                open=float(data.open),
                high=float(data.high),
                low=float(data.low),
                close=float(data.close),
                volume=float(data.volome),
                quote_volume=float(data.quote_volume),
                start=int(data.start_time),
                timestamp=self._clock.timestamp_ms(),
                interval=interval,
                confirm=False,  # NOTE: need to handle confirm yourself
            )
            self._msgbus.publish(topic="kline", msg=kline)
            self._log.debug(f"Kline update: {str(kline)}")

    def _handle_trade_data(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_trade_decoder.decode(raw)
        sym_id = f"{arg.instId}_{self._inst_type_suffix(arg.instType)}"
        for data in msg.data:
            trade = Trade(
                exchange=self._exchange_id,
                symbol=self._market_id[sym_id],
                price=float(data.price),
                size=float(data.size),
                timestamp=int(data.ts),
            )
            self._msgbus.publish(topic="trade", msg=trade)
            self._log.debug(f"Trade update: {str(trade)}")

    def _handle_books1_data(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_books1_decoder.decode(raw)
        sym_id = f"{arg.instId}_{self._inst_type_suffix(arg.instType)}"
        symbol = self._market_id[sym_id]
        for data in msg.data:
            bids = data.bids[0]
            asks = data.asks[0]
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
            self._log.debug(f"BookL1 update: {str(bookl1)}")

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        symbol = symbol if isinstance(symbol, list) else [symbol]
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(f"Symbol {sym} not found in market data.")
            symbols.append(market.id)
            inst_type = self._get_inst_type(market)
        await self._ws_client.subscribe_depth(symbols, inst_type, "books1")

    async def subscribe_trade(self, symbol):
        symbols = []
        symbol = symbol if isinstance(symbol, list) else [symbol]
        for sym in symbol:
            market = self._market.get(sym)
            if not market:
                raise ValueError(f"Symbol {sym} not found in market data.")
            symbols.append(market.id)
            inst_type = self._get_inst_type(market)
        await self._ws_client.subscribe_trade(symbols, inst_type)

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
        await self._ws_client.subscribe_candlesticks(
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
    _ws_client: BitgetWSClient
    _account_type: BitgetAccountType
    _market: Dict[str, BitgetMarket]
    _market_id: Dict[str, str]
    _api_client: BitgetApiClient

















async def main():
    exchange = BitgetExchangeManager()
    logguard, msgbus, clock = setup_nautilus_core("test-001", level_stdout="DEBUG")
    task_manager = TaskManager(
        loop=asyncio.get_event_loop(),
    )
    public_connector = BitgetPublicConnector(
        account_type=BitgetAccountType.LIVE,
        exchange=exchange,
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )
    await public_connector.subscribe_kline(
        "BTCUSDT-PERP.BITGET", interval=KlineInterval.MINUTE_1
    )
    await task_manager.wait()


if __name__ == "__main__":
    asyncio.run(main())

import msgspec

# import asyncio
from typing import Dict, List
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    # BookL2,
    # BookOrderData,
    # FundingRate,
    # IndexPrice,
    # MarkPrice,
    KlineList,
    Ticker,
)
from nexustrader.constants import (
    KlineInterval,
    BookLevel,
)
from nexustrader.exchange.bitget.schema import (
    BitgetMarket,
    BitgetWsUtaGeneralMsg,
    BitgetWsUtaArgMsg,
    BitgetBooks1WsMsg,
    BitgetWsTradeWsMsg,
    BitgetWsCandleWsMsg,
)
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
from nexustrader.exchange.bitget.websockets import BitgetWSClient
from nexustrader.exchange.bitget.oms import BitgetOrderManagementSystem
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetKlineInterval,
    BitgetUtaInstType,
    BitgetEnumParser,
    BitgetInstType,
)
from nexustrader.exchange.bitget.exchange import BitgetExchangeManager


class BitgetPublicConnector(PublicConnector):
    _uta_inst_type_map = {
        BitgetUtaInstType.SPOT: "spot",
        BitgetUtaInstType.USDC_FUTURES: "linear",
        BitgetUtaInstType.USDT_FUTURES: "linear",
        BitgetUtaInstType.COIN_FUTURES: "inverse",
    }
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

    def _uta_inst_type_suffix(self, inst_type: BitgetUtaInstType):
        return self._uta_inst_type_map[inst_type]

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
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol is not available: {symbol}")

        if market.spot:
            category = "SPOT"
        elif market.linear:
            category = "USDT-FUTURES" if market.quote == "USDT" else "USDC-FUTURES"
        elif market.inverse:
            category = "COIN-FUTURES"

        res = self._api_client.get_api_v3_market_tickers(
            category=category,
            symbol=symbol,
        )

        ticker_response = res.data[0]

        ticker = Ticker(
            exchange=self._exchange_id,
            symbol=symbol,
            last_price=float(ticker_response.lastPrice),
            timestamp=self._clock.timestamp_ms(),
            volume=float(ticker_response.volume24h),
            volumeCcy=float(ticker_response.turnover24h),
        )

        return ticker

    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        all_tickers: Dict[str, Ticker] = {}
        for category in ["SPOT", "USDT-FUTURES", "COIN-FUTURES", "USDC-FUTURES"]:
            res = self._api_client.get_api_v3_market_tickers(
                category=category,
            )

            for ticker_res in res.data:
                sym_id = ticker_res.symbol
                symbol = self._market_id.get(
                    f"{sym_id}_{self._inst_type_suffix(ticker_res.category)}"
                )

                if not symbol:
                    continue

                all_tickers[symbol] = Ticker(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    last_price=float(ticker_res.lastPrice),
                    timestamp=self._clock.timestamp_ms(),
                    volume=float(ticker_res.volume24h),
                    volumeCcy=float(ticker_res.turnover24h),
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
        sym_id = f"{arg.symbol}_{self._uta_inst_type_suffix(arg.instType)}"
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
        sym_id = f"{arg.symbol}_{self._uta_inst_type_suffix(arg.instType)}"
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
        sym_id = f"{arg.symbol}_{self._uta_inst_type_suffix(arg.instType)}"
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
    _account_type: BitgetAccountType
    _market: Dict[str, BitgetMarket]
    _api_client: BitgetApiClient
    _oms: BitgetOrderManagementSystem

    def __init__(
        self,
        account_type: BitgetAccountType,
        exchange: BitgetExchangeManager,
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
                "ApiKey, Secret and Passphrase must be provided for private connector."
            )

        api_client = BitgetApiClient(
            clock=clock,
            api_key=exchange.api_key,
            secret=exchange.secret,
            passphrase=exchange.passphrase,
            testnet=account_type.is_testnet,
            enable_rate_limit=enable_rate_limit,
            **kwargs,
        )

        oms = BitgetOrderManagementSystem(
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
            max_slippage=kwargs.get("max_slippage", 0.02),
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
        if self._account_type.is_uta:
            await self._oms._ws_client.subscribe_v3_order()
            await self._oms._ws_client.subscribe_v3_position()
            await self._oms._ws_client.subscribe_v3_account()
        elif self._account_type.is_future:
            await self._oms._ws_client.subscribe_orders(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
            await self._oms._ws_client.subscribe_positions(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
            await self._oms._ws_client.subscribe_account(
                inst_types=["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]
            )
        elif self._account_type.is_spot:
            await self._oms._ws_client.subscribe_orders(inst_types=["SPOT"])
            await self._oms._ws_client.subscribe_account(inst_types=["SPOT"])


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

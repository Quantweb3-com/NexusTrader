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
from nexustrader.exchange.bitget.schema import BitgetOrderCancelResponse, BitgetMarket
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
from nexustrader.exchange.bitget.websockets import BitgetWSClient
from nexustrader.exchange.bitget.constants import BitgetAccountType, BitgetKlineInterval
from nexustrader.exchange.bitget.exchange import BitgetExchangeManager


class BitgetPublicConnector(PublicConnector):
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
    
    def _get_inst_type(self, market: BitgetMarket):
        prefix = "S" if self._testnet else ""
        
        if market.spot:
            return "SPOT"
        elif market.linear:
            suffix = "USDT-FUTURES" if market.quote == "USDT" else "USDC-FUTURES"
            return f"{prefix}{suffix}"
        elif market.inverse:
            return f"{prefix}COIN-FUTURES"


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
        print(f"Received WebSocket message: {raw}")


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
        raise NotImplementedError

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        """Subscribe to the kline data"""
        raise NotImplementedError

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



async def main():
    exchange = BitgetExchangeManager()
    logguard, msgbus, clock = setup_nautilus_core(
        "test-001",
        level_stdout="DEBUG"
    )
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
    await public_connector.subscribe_bookl1("BTCUSDT-PERP.BITGET")
    await task_manager.wait()

if __name__ == "__main__":
    asyncio.run(main())

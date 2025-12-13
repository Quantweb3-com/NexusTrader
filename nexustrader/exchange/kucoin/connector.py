import msgspec
from typing import Dict, List

from nexustrader.base import PublicConnector
from nexustrader.constants import KlineInterval
from nexustrader.schema import KlineList, Ticker
from nexustrader.core.nautilius_core import MessageBus, LiveClock
from nexustrader.core.entity import TaskManager

from nexustrader.exchange.kucoin.exchange import KuCoinExchangeManager
from nexustrader.exchange.kucoin.websockets import KucoinWSClient
from nexustrader.exchange.kucoin.constants import KucoinAccountType
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient


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

    # ----- Requests (REST) -----
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

    def _ws_msg_handler(self, msg: bytes):
 
        try:
            data = msgspec.json.decode(msg)
        except Exception:
            data = {"raw": msg}
        self._msgbus.publish("kucoin.ws", data)

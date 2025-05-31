from typing import Callable, List
from typing import Any

from nexustrader.base import WSClient
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceKlineInterval,
)
from nexustrader.core.entity import TaskManager


class BinanceWSClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        ws_suffix: str = "/ws",
        custom_url: str | None = None,
    ):
        self._account_type = account_type
        url = account_type.ws_url

        if ws_suffix not in ["/ws", "/stream"]:
            raise ValueError(f"Invalid ws_suffix: {ws_suffix}")

        url += ws_suffix

        if custom_url is not None:
            url = custom_url

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            enable_auto_ping=False,
        )

    def _send_payload(self, params: List[str], chunk_size: int = 50):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "method": "SUBSCRIBE",
                "params": chunk,
                "id": self._clock.timestamp_ms(),
            }
            self._send(payload)

    async def _subscribe(self, params: List[str]):
        params = [param for param in params if param not in self._subscriptions]

        for param in params:
            self._subscriptions.append(param)
            self._log.debug(f"Subscribing to {param}...")

        await self.connect()
        self._send_payload(params)

    async def subscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_user_data_stream(self, listen_key: str):
        await self._subscribe([listen_key])

    async def subscribe_kline(
        self,
        symbols: List[str],
        interval: BinanceKlineInterval,
    ):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@kline_{interval.value}" for symbol in symbols]
        await self._subscribe(params)

    async def _resubscribe(self):
        self._send_payload(self._subscriptions)

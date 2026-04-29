import asyncio
import random
from datetime import datetime
from typing import Callable, List
from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter


from nexustrader.base import WSClient
from nexustrader.core.log import SpdLog
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
            limiter=AsyncLimiter(max_rate=2, time_period=1),
            handler=handler,
            task_manager=task_manager,
            enable_auto_ping=False,
        )

    async def _send_payload(self, params: List[str], chunk_size: int = 50):
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
            await self._send(payload)

    async def _subscribe(self, params: List[str]):
        params = [param for param in params if param not in self._subscriptions]

        for param in params:
            self._subscriptions.append(param)
            self._log.debug(f"Subscribing to {param}...")

        await self.connect()
        await self._send_payload(params)

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
        await self._send_payload(self._subscriptions)


class BinanceKlineDirectWSClient:
    def __init__(
        self,
        account_type: BinanceAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        custom_url: str | None = None,
        batch_size: int = 50,
        reconnect_delay_sec: float = 5.0,
        receive_timeout_sec: float = 90.0,
    ):
        self._account_type = account_type
        self._handler = handler
        self._task_manager = task_manager
        self._base_url = self._make_stream_base_url(custom_url or account_type.ws_url)
        self._batch_size = max(int(batch_size), 1)
        self._reconnect_delay_sec = max(float(reconnect_delay_sec), 1.0)
        self._receive_timeout_sec = max(float(receive_timeout_sec), 15.0)
        self._subscriptions: set[str] = set()
        self._tasks: list[asyncio.Task] = []
        self._task_id = 0
        self._closed = False
        self._last_message_at: datetime | None = None
        self._reconnect_count = 0
        self._log = SpdLog.get_logger(type(self).__name__, level="DEBUG", flush=True)

    @staticmethod
    def _make_stream_base_url(url: str) -> str:
        url = url.rstrip("/")
        if "?streams=" in url:
            return url.split("?streams=", 1)[0] + "?streams="
        if url.endswith("/stream"):
            return url + "?streams="
        if url.endswith("/ws"):
            return url[:-3] + "/stream?streams="
        return url + "/stream?streams="

    @staticmethod
    def _chunk_params(params: list[str], chunk_size: int) -> list[list[str]]:
        return [params[i : i + chunk_size] for i in range(0, len(params), chunk_size)]

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
        params = [param for param in params if param not in self._subscriptions]
        if not params:
            return

        self._closed = False
        for param in params:
            self._subscriptions.add(param)
            self._log.debug(f"Subscribing to {param} via direct combined stream...")

        shards = self._chunk_params(params, self._batch_size)
        for shard in shards:
            self._task_id += 1
            task = self._task_manager.create_task(
                self._run_shard(shard),
                name=f"binance-kline-direct-{self._task_id}",
            )
            self._tasks.append(task)

    async def _run_shard(self, params: list[str]):
        attempt = 0
        while not self._closed:
            try:
                await self._consume_shard(params)
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._reconnect_count += 1
                delay = self._reconnect_delay_sec * (2 ** min(attempt, 5))
                delay += random.uniform(0, 1.0)
                self._log.warn(
                    f"Binance kline stream reconnecting in {delay:.1f}s: {exc}"
                )
                attempt += 1
                await asyncio.sleep(delay)

    async def _consume_shard(self, params: list[str]):
        url = self._base_url + "/".join(params)
        timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.ws_connect(
                url,
                heartbeat=20.0,
                receive_timeout=self._receive_timeout_sec,
            ) as ws:
                self._log.debug(
                    f"Connected Binance kline direct stream with {len(params)} streams"
                )
                async for message in ws:
                    if self._closed:
                        break
                    if message.type == aiohttp.WSMsgType.TEXT:
                        self._last_message_at = datetime.now()
                        raw = (
                            message.data.encode()
                            if isinstance(message.data, str)
                            else message.data
                        )
                        self._handler(raw)
                    elif message.type in (
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        raise ConnectionError(
                            f"websocket closed: type={message.type} "
                            f"exception={ws.exception()!r}"
                        )
                if not self._closed:
                    raise ConnectionError("websocket closed")

    def disconnect(self):
        self._closed = True
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

    def get_health(self) -> dict:
        return {
            "enabled": True,
            "tracked_streams": len(self._subscriptions),
            "tasks": len(self._tasks),
            "batch_size": self._batch_size,
            "base_url": self._base_url,
            "last_message_at": self._last_message_at,
            "reconnect_count": self._reconnect_count,
        }

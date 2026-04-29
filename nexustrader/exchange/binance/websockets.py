import asyncio
import random
from datetime import datetime

from typing import Callable, List, Dict
from typing import Any
from urllib.parse import urlencode
import aiohttp
from nexustrader.base import WSClient
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceKlineInterval,
    BinanceRateLimiter,
)
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import hmac_signature, LiveClock, Logger


class BinanceWSClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
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
            clock=clock,
            enable_auto_ping=False,
        )

    def _send_payload(
        self, params: List[str], method: str = "SUBSCRIBE", chunk_size: int = 50
    ):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "method": method,
                "params": chunk,
                "id": self._clock.timestamp_ms(),
            }
            self._send(payload)

    async def _subscribe(self, params: List[str]):
        params = [param for param in params if param not in self._subscriptions]

        if not params:
            return

        for param in params:
            self._subscriptions.append(param)
            self._log.debug(f"Subscribing to {param}...")

        await self.connect()

        batch_size = 50
        total = len(params)
        for i in range(0, total, batch_size):
            chunk = params[i : i + batch_size]
            self._send_payload(chunk, method="SUBSCRIBE")
            if i + batch_size < total:
                self._log.info(
                    f"Subscribed batch {i // batch_size + 1} "
                    f"({len(chunk)}/{total} topics), waiting before next batch..."
                )
                await asyncio.sleep(0.5)

    async def _unsubscribe(self, params: List[str]):
        params = [param for param in params if param in self._subscriptions]

        if not params:
            return

        for param in params:
            self._subscriptions.remove(param)
            self._log.debug(f"Unsubscribing from {param}...")

        await self.connect()
        self._send_payload(params, method="UNSUBSCRIBE")

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

    async def unsubscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_user_data_stream(self, listen_key: str):
        await self._unsubscribe([listen_key])

    async def unsubscribe_kline(
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
        await self._unsubscribe(params)

    async def _resubscribe(self):
        batch_size = 50
        total = len(self._subscriptions)
        for i in range(0, total, batch_size):
            chunk = self._subscriptions[i : i + batch_size]
            self._send_payload(chunk)
            if i + batch_size < total:
                self._log.info(
                    f"Resubscribed batch {i // batch_size + 1} "
                    f"({len(chunk)}/{total} topics), waiting before next batch..."
                )
                await asyncio.sleep(0.5)


class BinanceWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._secret = secret
        self._limiter = BinanceRateLimiter(enable_rate_limit)

        url = account_type.ws_order_url

        if not url:
            raise ValueError(f"WebSocket URL not supported for {account_type}")

        self._user_data_subscribed = False
        self._uds_subscribe_event: asyncio.Event | None = None

        super().__init__(
            url=url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    def _generate_signature_v2(self, query: str) -> str:
        signature = hmac_signature(self._secret, query)
        return signature

    def _send_payload(
        self,
        id: str,
        method: str,
        params: Dict[str, Any],
        required_ts: bool = True,
        auth: bool = True,
    ):
        if required_ts:
            params["timestamp"] = self._clock.timestamp_ms()

        if auth:
            params["apiKey"] = self._api_key
            query = urlencode(sorted(params.items()))
            signature = self._generate_signature_v2(query)
            params["signature"] = signature

        payload = {
            "method": method,
            "id": id,
            "params": params,
        }
        self._send_or_raise(payload)

    async def subscribe_user_data_stream_signature(self):
        """Subscribe to user data stream via signature-based auth.

        Replaces the deprecated listenKey mechanism for Spot accounts.
        See: https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/user-data-stream-requests
        """
        self._uds_subscribe_event = asyncio.Event()
        self._send_payload(
            id=f"uds_{self._clock.timestamp_ms()}",
            method="userDataStream.subscribe.signature",
            params={},
            required_ts=True,
            auth=True,
        )
        self._user_data_subscribed = True
        self._log.info("Subscribed to user data stream via signature")
        try:
            await asyncio.wait_for(self._uds_subscribe_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._log.warning("Binance UDS subscribe response timeout (5s), proceeding anyway")

    def notify_uds_subscribed(self):
        if self._uds_subscribe_event is not None:
            self._uds_subscribe_event.set()

    async def spot_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.api_order_limit(cost=1)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def spot_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.api_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def usdm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.fapi_order_limit(cost=0)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def usdm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.fapi_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def coinm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter.dapi_order_limit(cost=0)
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def coinm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter.dapi_order_limit(cost=1)
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def _resubscribe(self):
        if self._user_data_subscribed:
            self._uds_subscribe_event = None
            await self.subscribe_user_data_stream_signature()


import asyncio  # noqa


async def main():
    from nexustrader.constants import settings
    from nexustrader.core.entity import TaskManager
    from nexustrader.core.nautilius_core import LiveClock, setup_nautilus_core, UUID4

    # API_KEY = settings.BINANCE.SPOT.TESTNET.API_KEY
    # SECRET = settings.BINANCE.SPOT.TESTNET.SECRET

    API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
    SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET

    log_guard = setup_nautilus_core(  # noqa
        trader_id="bnc-test",
        level_stdout="DEBUG",
    )

    task_manager = TaskManager(
        loop=asyncio.get_event_loop(),
    )

    ws_api_client = BinanceWSApiClient(
        account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
        api_key=API_KEY,
        secret=SECRET,
        handler=lambda msg: print(msg),
        task_manager=task_manager,
        clock=LiveClock(),
        enable_rate_limit=True,
    )

    await ws_api_client.connect()

    await ws_api_client.usdm_new_order(
        id=UUID4().value,
        symbol="BTCUSDT",
        side="BUY",
        type="LIMIT",
        quantity="0.003",
        price="120000",
        # timeInForce="GTC",
    )

    # await ws_api_client.usdm_cancel_order(
    #     id="aa510a1f-7240-4368-8cc0-ba577483a734",
    #     symbol="BTCUSDT",
    #     orderId=5594834544,  # Replace with a valid order ID
    # )

    # await ws_api_client.spot_new_order(
    #     id=UUID4().value,
    #     symbol="BTCUSDT",
    #     side="BUY",
    #     type="LIMIT",
    #     quantity="0.001",
    #     price="80000",
    #     timeInForce="GTC",
    # )
    # await ws_api_client.spot_cancel_open_orders(
    #     id="20dbbfdb-fc47-4abf-bb0f-bc0cd117c29a",
    #     symbol="BTCUSDT",
    # )

    await task_manager.wait()


if __name__ == "__main__":
    asyncio.run(main())


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
        url = custom_url or account_type.ws_url
        if custom_url is None and account_type.is_future:
            url = f"{url.rstrip('/')}/market"
        self._base_url = self._make_stream_base_url(url)
        self._batch_size = max(int(batch_size), 1)
        self._reconnect_delay_sec = max(float(reconnect_delay_sec), 1.0)
        self._receive_timeout_sec = max(float(receive_timeout_sec), 15.0)
        self._subscriptions: set[str] = set()
        self._tasks: list[asyncio.Task] = []
        self._task_id = 0
        self._closed = False
        self._last_message_at: datetime | None = None
        self._reconnect_count = 0
        self._log = Logger(name=type(self).__name__)

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

        for shard in self._chunk_params(params, self._batch_size):
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
                self._log.warning(
                    f"Binance kline stream reconnecting in {delay:.1f}s: {exc}"
                )
                attempt += 1
                await asyncio.sleep(delay)

    async def _consume_shard(self, params: list[str]):
        url = self._base_url + "/".join(params)
        timeout = aiohttp.ClientTimeout(total=None)
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=True,
        ) as session:
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

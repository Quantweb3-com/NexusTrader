import msgspec
import asyncio

from typing import Any, Callable, List

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, hmac_signature
from nexustrader.exchange.bybit.constants import (
    BybitAccountType,
    BybitKlineInterval,
    BybitRateLimiter,
)


class BybitWSClient(WSClient):
    def __init__(
        self,
        account_type: BybitAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str = None,
        secret: str = None,
        custom_url: str = None,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._secret = secret
        self._authed = False
        if self.is_private:
            url = account_type.ws_private_url
        else:
            url = account_type.ws_public_url
        if custom_url:
            url = custom_url
        # Bybit: do not exceed 500 requests per 5 minutes
        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            specific_ping_msg=msgspec.json.encode({"op": "ping"}),
            auto_ping_strategy="ping_when_idle",
        )

    @property
    def is_private(self):
        return self._api_key is not None or self._secret is not None

    def _generate_signature(self):
        expires = self._clock.timestamp_ms() + 1_000
        signature = hmac_signature(self._secret, f"GET/realtime{expires}")
        return signature, expires

    def _get_auth_payload(self):
        signature, expires = self._generate_signature()
        return {"op": "auth", "args": [self._api_key, expires, signature]}

    async def _auth(self):
        if not self._authed:
            self._send(self._get_auth_payload())
            self._authed = True
            await asyncio.sleep(5)

    def _send_payload(self, params: List[str], chunk_size: int = 100):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {"op": "subscribe", "args": chunk}
            self._send(payload)

    async def _subscribe(self, topics: List[str], auth: bool = False):
        topics = [topic for topic in topics if topic not in self._subscriptions]

        for topic in topics:
            self._subscriptions.append(topic)
            self._log.debug(f"Subscribing to {topic}...")

        await self.connect()
        if auth:
            await self._auth()
        if not topics:
            return
        self._send_payload(topics)

    async def _unsubscribe(self, topics: List[str]):
        topics = [topic for topic in topics if topic in self._subscriptions]

        for topic in topics:
            self._subscriptions.remove(topic)
            self._log.debug(f"Unsubscribing from {topic}...")

        await self.connect()
        payload = {"op": "unsubscribe", "args": topics}
        if not topics:
            return
        self._send(payload)

    async def subscribe_order_book(self, symbols: List[str], depth: int):
        """subscribe to orderbook"""
        topics = [f"orderbook.{depth}.{symbol}" for symbol in symbols]
        await self._subscribe(topics)

    async def subscribe_trade(self, symbols: List[str]):
        """subscribe to trade"""
        topics = [f"publicTrade.{symbol}" for symbol in symbols]
        await self._subscribe(topics)

    async def subscribe_ticker(self, symbols: List[str]):
        """subscribe to ticker"""
        topics = [f"tickers.{symbol}" for symbol in symbols]
        await self._subscribe(topics)

    async def subscribe_kline(self, symbols: List[str], interval: BybitKlineInterval):
        """subscribe to kline"""
        topics = [f"kline.{interval.value}.{symbol}" for symbol in symbols]
        await self._subscribe(topics)

    async def unsubscribe_order_book(self, symbols: List[str], depth: int):
        """unsubscribe from orderbook"""
        topics = [f"orderbook.{depth}.{symbol}" for symbol in symbols]
        await self._unsubscribe(topics)

    async def unsubscribe_trade(self, symbols: List[str]):
        """unsubscribe from trade"""
        topics = [f"publicTrade.{symbol}" for symbol in symbols]
        await self._unsubscribe(topics)

    async def unsubscribe_ticker(self, symbols: List[str]):
        """unsubscribe from ticker"""
        topics = [f"tickers.{symbol}" for symbol in symbols]
        await self._unsubscribe(topics)

    async def unsubscribe_kline(self, symbols: List[str], interval: BybitKlineInterval):
        """unsubscribe from kline"""
        topics = [f"kline.{interval.value}.{symbol}" for symbol in symbols]
        await self._unsubscribe(topics)

    async def _resubscribe(self):
        if self.is_private:
            self._authed = False
            await self._auth()
        self._send_payload(self._subscriptions)

    async def subscribe_order(self, topic: str = "order"):
        """subscribe to order"""
        await self._subscribe([topic], auth=True)

    async def subscribe_position(self, topic: str = "position"):
        """subscribe to position"""
        await self._subscribe([topic], auth=True)

    async def subscribe_wallet(self, topic: str = "wallet"):
        """subscribe to wallet"""
        await self._subscribe([topic], auth=True)


class BybitWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BybitAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._api_key = api_key
        self._secret = secret
        self._account_type = account_type
        self._authed = False

        url = account_type.ws_api_url
        self._limiter = BybitRateLimiter(
            enable_rate_limit=enable_rate_limit,
        )

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            specific_ping_msg=msgspec.json.encode({"op": "ping"}),
        )

    def _generate_signature(self):
        expires = self._clock.timestamp_ms() + 1_000
        signature = hmac_signature(self._secret, f"GET/realtime{expires}")
        return signature, expires

    def _get_auth_payload(self):
        signature, expires = self._generate_signature()
        return {"op": "auth", "args": [self._api_key, expires, signature]}

    async def _auth(self):
        if not self._authed:
            self._send(self._get_auth_payload())
            self._authed = True
            await asyncio.sleep(5)

    def _submit(self, reqId: str, op: str, args: list[dict]):
        payload = {
            "reqId": reqId,
            "header": {
                "X-BAPI-TIMESTAMP": self._clock.timestamp_ms(),
            },
            "op": op,
            "args": args,
        }
        self._send(payload)

    async def create_order(
        self,
        id: str,
        symbol: str,
        side: str,
        orderType: str,
        qty: str,
        category: str,
        **kwargs,
    ):
        arg = {
            "symbol": symbol,
            "side": side,
            "orderType": orderType,
            "qty": qty,
            "category": category,
            **kwargs,
        }
        op = "order.create"
        if category == "spot":
            cost = 1
        else:
            cost = 2
        await self._limiter("ws/order").limit(key=op, cost=cost)
        self._submit(reqId=f"n{id}", op=op, args=[arg])

    async def cancel_order(
        self, id: str, symbol: str, orderLinkId: str, category: str, **kwargs
    ):
        arg = {
            "symbol": symbol,
            "orderLinkId": orderLinkId,
            "category": category,
            **kwargs,
        }
        op = "order.cancel"
        if category == "spot":
            cost = 1
        else:
            cost = 2
        await self._limiter("ws/order").limit(key=op, cost=cost)
        self._submit(reqId=f"c{id}", op=op, args=[arg])

    async def connect(self):
        await super().connect()
        await self._auth()

    async def _resubscribe(self):
        self._authed = False
        await self._auth()


import asyncio  # noqa


async def main():
    from nexustrader.constants import settings
    from nexustrader.core.entity import TaskManager
    from nexustrader.core.nautilius_core import LiveClock, setup_nautilus_core, UUID4

    BYBIT_API_KEY = settings.BYBIT.ACCOUNT1.API_KEY
    BYBIT_SECRET = settings.BYBIT.ACCOUNT1.SECRET

    log_guard = setup_nautilus_core(  # noqa
        trader_id="bnc-test",
        level_stdout="DEBUG",
    )

    task_manager = TaskManager(
        loop=asyncio.get_event_loop(),
    )

    ws_api_client = BybitWSApiClient(
        account_type=BybitAccountType.UNIFIED_TESTNET,
        api_key=BYBIT_API_KEY,
        secret=BYBIT_SECRET,
        handler=lambda msg: print(msg),
        task_manager=task_manager,
        clock=LiveClock(),
        enable_rate_limit=True,
    )

    await ws_api_client.connect()
    # await ws_api_client.create_order(
    #     id=UUID4().value,
    #     symbol="BTCUSDT",
    #     side="Buy",
    #     orderType="Market",
    #     qty="0.001",
    #     category="linear",
    # )
    await ws_api_client.cancel_order(
        id="4ae064b8-7b08-4ba4-a9d9-3022da13d8d5",
        orderId="7ed63377-d375-4bc7-b6d1-dc9f47c37ca4",
        symbol="BTCUSDT",
        category="linear",
    )
    await task_manager.wait()


if __name__ == "__main__":
    asyncio.run(main())

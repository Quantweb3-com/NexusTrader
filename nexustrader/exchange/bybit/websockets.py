import hmac
import msgspec
import asyncio

from typing import Any, Callable, List

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.exchange.bybit.constants import BybitAccountType, BybitKlineInterval


class BybitWSClient(WSClient):
    def __init__(
        self,
        account_type: BybitAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
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
        signature = str(
            hmac.new(
                bytes(self._secret, "utf-8"),
                bytes(f"GET/realtime{expires}", "utf-8"),
                digestmod="sha256",
            ).hexdigest()
        )
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
        self._send_payload(topics)

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

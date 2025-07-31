import hmac
import base64
import asyncio

from typing import Any, Callable, List, Dict

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.bitget.constants import BitgetAccountType, BitgetKlineInterval


class BitgetWSClient(WSClient):
    def __init__(
        self,
        account_type: BitgetAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
        custom_url: str | None = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._account_type = account_type
        self._authed = False

        if custom_url:
            url = custom_url
        elif self.is_private:
            url = f"{account_type.stream_url}/private"
        else:
            url = f"{account_type.stream_url}/public"

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            ping_idle_timeout=30,
            ping_reply_timeout=5,
        )

    @property
    def is_private(self):
        return (
            self._api_key is not None
            or self._secret is not None
            or self._passphrase is not None
        )

    def _get_auth_payload(self):
        timestamp = self._clock.timestamp()
        message = timestamp + "GET" + "/user/verify"

        # Create HMAC-SHA256 signature
        mac = hmac.new(
            bytes(self._secret, encoding="utf8"),
            bytes(message, encoding="utf-8"),
            digestmod="sha256",
        )

        # Get the digest and encode with base64
        signature = base64.b64encode(mac.digest()).decode("utf-8")

        # Form the login payload
        payload = {
            "op": "login",
            "args": [
                {
                    "apiKey": self._api_key,
                    "passphrase": self._passphrase,  # If required
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ],
        }

        return payload

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

    async def _subscribe(self, params: List[Dict[str, Any]], auth: bool = False):
        params = [param for param in params if param not in self._subscriptions]

        for param in params:
            self._subscriptions.append(param)
            formatted_param = ".".join(param.values())
            self._log.debug(f"Subscribing to {formatted_param}...")

        await self.connect()
        if auth:
            await self._auth()
        self._send_payload(params)

    async def subscribe_depth(self, symbols: List[str], inst_type: str, channel: str):
        if channel not in ["books1", "books5", "books15"]:
            raise ValueError(f"Invalid channel: {channel}")

        params = [
            {"instType": inst_type, "channel": channel, "instId": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_candlesticks(
        self, symbols: List[str], inst_type: str, interval: BitgetKlineInterval
    ):
        params = [
            {"instType": inst_type, "channel": interval.value, "instId": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_trade(self, symbols: List[str], inst_type: str):
        params = [
            {"instType": inst_type, "channel": "trade", "instId": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_ticker(self, symbols: List[str], inst_type: str):
        params = [
            {"instType": inst_type, "channel": "ticker", "instId": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_account(self, inst_types: List[str] | str):
        if isinstance(inst_types, str):
            inst_types = [inst_types]
        params = [
            {"instType": inst_type, "channel": "account", "coin": "default"}
            for inst_type in inst_types
        ]
        await self._subscribe(params, auth=True)

    async def subscribe_position(self, inst_types: List[str] | str):
        if isinstance(inst_types, str):
            inst_types = [inst_types]
        params = [
            {"instType": inst_type, "channel": "position", "instId": "default"}
            for inst_type in inst_types
        ]
        await self._subscribe(params, auth=True)

    async def subscribe_orders(self, inst_types: List[str] | str):
        if isinstance(inst_types, str):
            inst_types = [inst_types]
        params = [
            {"instType": inst_type, "channel": "orders", "instId": "default"}
            for inst_type in inst_types
        ]
        await self._subscribe(params, auth=True)

    async def _resubscribe(self):
        if self.is_private:
            self._authed = False
            await self._auth()
        self._send_payload(self._subscriptions)

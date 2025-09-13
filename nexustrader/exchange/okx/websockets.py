import base64
import asyncio

from typing import Literal, Any, Callable, Dict, List

from nexustrader.base import WSClient
from nexustrader.exchange.okx.constants import (
    OkxAccountType,
    OkxKlineInterval,
    OkxRateLimiter,
)
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, hmac_signature


class OkxWSClient(WSClient):
    def __init__(
        self,
        account_type: OkxAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
        business_url: bool = False,
        custom_url: str | None = None,
    ):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._account_type = account_type
        self._authed = False
        self._business_url = business_url
        if custom_url:
            url = custom_url
        elif self.is_private:
            if not all([self._api_key, self._passphrase, self._secret]):
                raise ValueError("API Key, Passphrase, or Secret is missing.")
            url = f"{account_type.stream_url}/v5/private"
        else:
            endpoint = "business" if business_url else "public"
            url = f"{account_type.stream_url}/v5/{endpoint}"

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            ping_idle_timeout=5,
            ping_reply_timeout=2,
        )

    @property
    def is_private(self):
        return (
            self._api_key is not None
            or self._secret is not None
            or self._passphrase is not None
        )

    def _get_auth_payload(self):
        timestamp = int(self._clock.timestamp())
        message = str(timestamp) + "GET" + "/users/self/verify"
        digest = bytes.fromhex(hmac_signature(self._secret, message))
        sign = base64.b64encode(digest)

        arg = {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": timestamp,
            "sign": sign.decode("utf-8"),
        }
        payload = {"op": "login", "args": [arg]}
        return payload

    async def _auth(self):
        if not self._authed:
            self._send(self._get_auth_payload())
            self._authed = True
            await asyncio.sleep(5)

    def _send_payload(self, params: List[Dict[str, Any]], chunk_size: int = 100):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "op": "subscribe",
                "args": chunk,
            }
            self._send(payload)

    async def _subscribe(self, params: List[Dict[str, Any]], auth: bool = False):
        params = [param for param in params if param not in self._subscriptions]

        for param in params:
            self._subscriptions.append(param)
            self._log.debug(f"Subscribing to {param}...")

        await self.connect()
        if auth:
            await self._auth()

        self._send_payload(params)

    async def subscribe_funding_rate(self, symbols: List[str]):
        params = [{"channel": "funding-rate", "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_index_price(self, symbols: List[str]):
        params = [{"channel": "index-tickers", "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_mark_price(self, symbols: List[str]):
        params = [{"channel": "mark-price", "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_order_book(
        self,
        symbols: List[str],
        channel: Literal[
            "books", "books5", "bbo-tbt", "books-l2-tbt", "books50-l2-tbt"
        ],
    ):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-order-book-channel
        """
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_trade(self, symbols: List[str]):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-all-trades-channel
        """
        params = [{"channel": "trades", "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_candlesticks(
        self,
        symbols: List[str],
        interval: OkxKlineInterval,
    ):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-market-data-ws-candlesticks-channel
        """
        if not self._business_url:
            raise ValueError("candlesticks are only supported on business url")
        channel = interval.value
        params = [{"channel": channel, "instId": symbol} for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_account(self):
        params = {"channel": "account"}
        await self._subscribe([params], auth=True)

    async def subscribe_account_position(self):
        params = {"channel": "balance_and_position"}
        await self._subscribe([params], auth=True)

    async def subscribe_positions(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "positions", "instType": inst_type}
        await self._subscribe([params], auth=True)

    async def subscribe_orders(
        self, inst_type: Literal["MARGIN", "SWAP", "FUTURES", "OPTION", "ANY"] = "ANY"
    ):
        params = {"channel": "orders", "instType": inst_type}
        await self._subscribe([params], auth=True)

    async def subscribe_fills(self):
        params = {"channel": "fills"}
        await self._subscribe([params], auth=True)

    async def _resubscribe(self):
        if self.is_private:
            self._authed = False
            await self._auth()
        self._send_payload(self._subscriptions)


class OkxWSApiClient(WSClient):
    def __init__(
        self,
        account_type: OkxAccountType,
        api_key: str,
        secret: str,
        passphrase: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._account_type = account_type
        self._authed = False

        url = f"{account_type.stream_url}/v5/private"
        self._limiter = OkxRateLimiter(enable_rate_limit=enable_rate_limit)

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            ping_idle_timeout=5,
            ping_reply_timeout=2,
        )

    def _get_auth_payload(self):
        timestamp = int(self._clock.timestamp())
        message = str(timestamp) + "GET" + "/users/self/verify"
        digest = bytes.fromhex(hmac_signature(self._secret, message))
        sign = base64.b64encode(digest)
        arg = {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": timestamp,
            "sign": sign.decode("utf-8"),
        }
        payload = {"op": "login", "args": [arg]}
        return payload

    async def connect(self):
        await super().connect()
        await self._auth()

    async def _auth(self):
        if not self._authed:
            self._send(self._get_auth_payload())
            self._authed = True
            await asyncio.sleep(5)

    async def _resubscribe(self):
        self._authed = False
        await self._auth()

    def _submit(self, id: str, op: str, params: Dict[str, Any]):
        payload = {
            "id": id,
            "op": op,
            "args": [params],
        }
        self._send(payload)

    async def place_order(
        self,
        id: str,
        instId: str,
        tdMode: str,
        side: str,
        ordType: str,
        sz: str,
        **kwargs,
    ):
        params = {
            "instId": instId,
            "tdMode": tdMode,
            "side": side,
            "ordType": ordType,
            "sz": sz,
            **kwargs,
        }
        await self._limiter("/ws/order").limit("order", cost=1)
        self._submit(id, "order", params)

    async def cancel_order(self, id: str, instId: str, clOrdId: str):
        params = {
            "instId": instId,
            "clOrdId": clOrdId,
        }
        await self._limiter("/ws/cancel").limit("cancel", cost=1)
        self._submit(id, "cancel-order", params)


# import asyncio  # noqa


# async def main():
#     from nexustrader.constants import settings
#     from nexustrader.core.entity import TaskManager
#     from nexustrader.core.nautilius_core import LiveClock, setup_nautilus_core, UUID4

#     OKX_API_KEY = settings.OKX.DEMO_1.API_KEY
#     OKX_SECRET = settings.OKX.DEMO_1.SECRET
#     OKX_PASSPHRASE = settings.OKX.DEMO_1.PASSPHRASE

#     log_guard = setup_nautilus_core(  # noqa
#         trader_id="bnc-test",
#         level_stdout="DEBUG",
#     )

#     task_manager = TaskManager(
#         loop=asyncio.get_event_loop(),
#     )

#     ws_api_client = OkxWSApiClient(
#         account_type=OkxAccountType.DEMO,
#         api_key=OKX_API_KEY,
#         secret=OKX_SECRET,
#         passphrase=OKX_PASSPHRASE,
#         handler=lambda msg: print(msg),
#         task_manager=task_manager,
#         clock=LiveClock(),
#         enable_rate_limit=True,
#     )

#     await ws_api_client.connect()
#     # await ws_api_client.subscribe_orders()

#     # await ws_api_client.place_order(
#     #     id=strip_uuid_hyphens(UUID4().value),
#     #     instId="BTC-USDT-SWAP",
#     #     tdMode="cross",
#     #     side="buy",
#     #     ordType="limit",
#     #     sz="0.1",
#     #     px="100000"
#     #     # timeInForce="GTC",
#     # )

#     await ws_api_client.cancel_order(
#         id="ffab98098c664e7c847290192015089d",
#         instId="BTC-USDT-SWAP",
#         ordId="2791773453976276992",
#     )

#     await task_manager.wait()


# if __name__ == "__main__":
#     asyncio.run(main())

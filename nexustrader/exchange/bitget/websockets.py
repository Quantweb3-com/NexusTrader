import hmac
import base64
import asyncio

from uuid import UUID
from typing import Any, Callable, List, Dict

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetKlineInterval,
    BitgetRateLimiter,
)


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
            auto_ping_strategy="ping_periodically",
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
        timestamp = self._clock.timestamp_ms()
        message = f"{timestamp}GET/user/verify"

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

    async def subscribe_positions(self, inst_types: List[str] | str):
        if isinstance(inst_types, str):
            inst_types = [inst_types]
        params = [
            {"instType": inst_type, "channel": "positions", "instId": "default"}
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

    ############ UTA subscribe ###########
    ### Better Performance with v3 API ###

    async def subscribe_depth_v3(self, symbols: List[str], inst_type: str, topic: str):
        if topic not in ["books1", "books5", "books15"]:
            raise ValueError(f"Invalid channel: {topic}")

        params = [
            {"instType": inst_type, "topic": topic, "symbol": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_trades_v3(self, symbols: List[str], inst_type: str):
        params = [
            {"instType": inst_type, "topic": "publicTrade", "symbol": symbol}
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def subscribe_candlestick_v3(
        self, symbols: List[str], inst_type: str, interval: BitgetKlineInterval
    ):
        params = [
            {
                "instType": inst_type,
                "topic": "kline",
                "symbol": symbol,
                "interval": interval.value,
            }
            for symbol in symbols
        ]
        await self._subscribe(params)

    async def _resubscribe(self):
        if self.is_private:
            self._authed = False
            await self._auth()
        self._send_payload(self._subscriptions)

    async def subscribe_v3_order(self):
        params = [{"instType": "UTA", "topic": "order"}]
        await self._subscribe(params, auth=True)

    async def subscribe_v3_position(self):
        params = [{"instType": "UTA", "topic": "position"}]
        await self._subscribe(params, auth=True)

    async def subscribe_v3_account(self):
        params = [{"instType": "UTA", "topic": "account"}]
        await self._subscribe(params, auth=True)


class BitgetWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BitgetAccountType,
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

        # Use V2 WebSocket API for trading
        url = f"{account_type.stream_url}/private"

        self._limiter = BitgetRateLimiter(
            enable_rate_limit=enable_rate_limit,
        )

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            specific_ping_msg=b"ping",
            auto_ping_strategy="ping_periodically",
            ping_idle_timeout=30,
            ping_reply_timeout=5,
        )

    def _get_auth_payload(self):
        timestamp = self._clock.timestamp_ms()
        message = f"{timestamp}GET/user/verify"

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
                    "passphrase": self._passphrase,
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

    def _submit(
        self, id: str, instType: str, instId: str, channel: str, params: Dict[str, Any]
    ):
        payload = {
            "op": "trade",
            "args": [
                {
                    "id": id,
                    "instType": instType,
                    "instId": instId,
                    "channel": channel,
                    "params": params,
                }
            ],
        }
        self._send(payload)

    def _uta_submit(
        self, id: str, topic: str, category: str, args: List[Dict[str, Any]]
    ):
        payload = {
            "op": "trade",
            "id": id,
            "topic": topic,
            "category": category,
            "args": args,
        }
        self._send(payload)

    async def spot_place_order(
        self,
        id: str,
        instId: str,
        orderType: str,
        side: str,
        size: str,
        force: str,
        **kwargs,
    ):
        params = {
            "orderType": orderType,
            "side": side,
            "size": size,
            "force": force,
            **kwargs,
        }

        await self._limiter("/api/v2/spot/trade/place-order").limit(
            key="spot_place_order"
        )
        self._submit(
            id=id, instType="SPOT", instId=instId, channel="place-order", params=params
        )

    async def spot_cancel_order(
        self,
        id: str,
        instId: str,
        orderId: str,
        **kwargs,
    ):
        params = {
            "orderId": orderId,
            **kwargs,
        }

        await self._limiter("/api/v2/spot/trade/cancel-order").limit(
            key="spot_cancel_order"
        )
        self._submit(
            id=id, instType="SPOT", instId=instId, channel="cancel-order", params=params
        )

    async def future_place_order(
        self,
        id: str,
        instId: str,
        orderType: str,
        side: str,
        size: str,
        force: str,
        marginCoin: str,
        marginMode: str,
        instType: str,
        **kwargs,
    ):
        params = {
            "orderType": orderType,
            "side": side,
            "size": size,
            "force": force,
            "marginCoin": marginCoin,
            "marginMode": marginMode,
            **kwargs,
        }

        await self._limiter("/api/v2/mix/order/place-order").limit(
            key="future_place_order"
        )
        self._submit(
            id=id,
            instType=instType,
            instId=instId,
            channel="place-order",
            params=params,
        )

    async def future_cancel_order(
        self,
        id: str,
        instId: str,
        orderId: str,
        instType: str,
        **kwargs,
    ):
        params = {
            "orderId": orderId,
            **kwargs,
        }

        await self._limiter("/api/v2/mix/order/cancel-order").limit(
            key="future_cancel_order"
        )
        self._submit(
            id=id,
            instType=instType,
            instId=instId,
            channel="cancel-order",
            params=params,
        )

    async def uta_place_order(
        self,
        id: str,
        category: str,
        symbol: str,
        orderType: str,
        qty: str,
        price: str,
        side: str,
        **kwargs,
    ):
        args = [
            {
                "orderType": orderType,
                "price": price,
                "qty": qty,
                "side": side,
                "symbol": symbol,
                **kwargs,
            }
        ]

        await self._limiter("/api/v3/trade/place-order").limit(key="uta_place_order")
        self._uta_submit(id=id, topic="place-order", category=category, args=args)

    async def uta_cancel_order(
        self,
        id: str,
        orderId: str,
        **kwargs,
    ):
        args = [
            {
                "orderId": orderId,
                **kwargs,
            }
        ]

        await self._limiter("/api/v3/trade/cancel-order").limit(key="uta_cancel_order")
        self._uta_submit(
            id=id,
            topic="cancel-order",
            category="",  # No category specified in UTA cancel order
            args=args,
        )

    async def connect(self):
        await super().connect()
        await self._auth()

    async def _resubscribe(self):
        self._authed = False
        await self._auth()


async def main():
    from nexustrader.constants import settings
    from nexustrader.core.entity import TaskManager
    from nexustrader.core.nautilius_core import setup_nautilus_core, UUID4

    API_KEY = settings.BITGET.DEMO1.API_KEY
    SECRET = settings.BITGET.DEMO1.SECRET
    PASSPHRASE = settings.BITGET.DEMO1.PASSPHRASE

    log_guard, _, clock = setup_nautilus_core(  # noqa
        trader_id="bnc-test",
        level_stdout="DEBUG",
    )

    task_manager = TaskManager(
        loop=asyncio.get_event_loop(),
    )

    ws_api_client = BitgetWSApiClient(
        account_type=BitgetAccountType.UTA_DEMO,
        api_key=API_KEY,
        secret=SECRET,
        passphrase=PASSPHRASE,
        handler=lambda msg: print(msg),
        task_manager=task_manager,
        clock=clock,
        enable_rate_limit=True,
    )

    await ws_api_client.connect()
    # await ws_api_client.spot_place_order(
    #     id=UUID4().value,
    #     instId="BTCUSDT",
    #     orderType="limit",
    #     side="buy",
    #     size="0.001",
    #     price="116881",
    #     force="gtc",
    # )

    # await ws_api_client.spot_cancel_order(
    #     id="9ee1e7d2-99a1-4ff5-82f7-473f02ff38e7",
    #     instId="BTCUSDT",
    #     orderId="1344423929063153665",
    # )

    # await ws_api_client.uta_place_order(
    #     id=UUID4().value,
    #     category="spot",  # SPOT MARGIN USDT-FUTURES COIN-FUTURES USDC-FUTURES
    #     symbol="BTCUSDT",
    #     orderType="limit",
    #     qty="0.001",
    #     price="110536",
    #     side="buy",
    # )

    # await ws_api_client.uta_cancel_order(
    #     id="3c14b801-ecc0-47f9-8126-56604d9f4c33",
    #     instId="BTCUSDT",
    #     orderId="1344515561982640128",
    # )

    await task_manager.wait()

    # {
    #     "event": "trade",
    #     "arg": [
    #         {
    #             "id": "30862609-4cb0-45cb-8562-992aaf232ee8",
    #             "instType": "SPOT",
    #             "channel": "place-order",
    #             "instId": "BTCUSDT",
    #             "params": {
    #                 "orderId": "1344419561630867456",
    #                 "clientOid": "0021c683-5e7e-416e-8dbb-dd34a0c3f97c",
    #             },
    #         }
    #     ],
    #     "code": 0,
    #     "msg": "Success",
    #     "ts": 1756260522296,
    # }

    # {
    #     "event": "error",
    #     "arg": [
    #         {
    #             "id": "1c6dbaae-4599-4371-9517-f800bc2f0dfb",
    #             "instType": "SPOT",
    #             "channel": "place-order",
    #             "instId": "BTCUSDT",
    #             "params": {
    #                 "orderType": "limit",
    #                 "side": "buy",
    #                 "force": "gtc",
    #                 "price": "80000",
    #                 "size": "0.000001",
    #             },
    #         }
    #     ],
    #     "code": 43027,
    #     "msg": "The minimum order value 1 is not met",
    #     "ts": 1756260596285,
    # }

    # {
    #     "event": "trade",
    #     "arg": [
    #         {
    #             "id": "30862609-4cb0-45cb-8562-992aaf232ee8",
    #             "instType": "SPOT",
    #             "channel": "cancel-order",
    #             "instId": "BTCUSDT",
    #             "params": {"orderId": "1344419561630867456"},
    #         }
    #     ],
    #     "code": 0,
    #     "msg": "Success",
    #     "ts": 1756260769404,
    # }

    # {
    #     "event": "error",
    #     "arg": [
    #         {
    #             "id": "9ee1e7d2-99a1-4ff5-82f7-473f02ff38e7",
    #             "instType": "SPOT",
    #             "channel": "cancel-order",
    #             "instId": "BTCUSDT",
    #             "params": {"orderId": "1344423929063153665"},
    #         }
    #     ],
    #     "code": 43001,
    #     "msg": "The order does not exist",
    #     "ts": 1756261603661,
    # }

    ##### UTA ACCOUNT #####

    # {
    #     "event": "error",
    #     "id": "bb63695d-b11f-4c6d-8166-460c612dc252",
    #     "code": "41101",
    #     "msg": "Param category=SPOT error",
    # }

    # {
    #     "event": "error",
    #     "id": "401822f1-4014-4bf0-af07-723fcbe391d4",
    #     "code": "25206",
    #     "msg": "BTC/USDT trading price cannot exceed 5%",
    # }

    # {
    #     "event": "trade",
    #     "id": "90ab565b-f863-4377-b275-08020b6c0536",
    #     "category": "spot",
    #     "topic": "place-order",
    #     "args": [
    #         {
    #             "symbol": "BTCUSDT",
    #             "orderId": "1344507887740108800",
    #             "clientOid": "1344507887740108801",
    #             "cTime": "1756281580862",
    #         }
    #     ],
    #     "code": "0",
    #     "msg": "Success",
    #     "ts": "1756281580865",
    # }

    # {
    #     "event": "error",
    #     "id": "90ab565b-f863-4377-b275-08020b6c0536",
    #     "code": "25204",
    #     "msg": "Order does not exist",
    # }

    # {
    #     "event": "trade",
    #     "id": "3c14b801-ecc0-47f9-8126-56604d9f4c33",
    #     "topic": "cancel-order",
    #     "args": [
    #         {"orderId": "1344515561982640128", "clientOid": "1344515561982640129"}
    #     ],
    #     "code": "0",
    #     "msg": "Success",
    #     "ts": "1756283452147",
    # }


if __name__ == "__main__":
    asyncio.run(main())

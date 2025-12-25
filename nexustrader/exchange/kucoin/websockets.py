from typing import Any, Callable, List, Literal, Dict

from nexustrader.base.ws_client import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.kucoin.constants import KucoinAccountType


class KucoinWSClient(WSClient):
    def __init__(
        self,
        account_type: KucoinAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        custom_url: str | None = None,
    ) -> None:
        self._account_type = account_type

        url = custom_url or account_type.stream_url
        if not url:
            raise ValueError(f"WebSocket URL not supported for {account_type}")

        super().__init__(
            url=url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    async def _subscribe(self, topics: List[dict[str, str]]) -> None:
        if not topics:
            return

        new_topics: List[dict[str, str]] = []
        for t in topics:
            key = f"{t['topic']}|{t.get('symbol', '')}"
            if key in self._subscriptions:
                continue
            self._subscriptions.append(key)
            new_topics.append(t)

        if not new_topics:
            return

        await self.connect()

        payload = {
            "id": str(self._clock.timestamp_ms()),
            "type": "subscribe",
            "topic": new_topics[0]["topic"] + ":"
            + ",".join({tp["symbol"] for tp in new_topics}),
            "response": True,
        }
        self._send(payload)

    async def _resubscribe(self) -> None:
        """Resubscribe to all previously subscribed topics after reconnect.

        Groups stored subscription keys ("topic|symbol") by topic and reissues
        a single subscribe payload per topic with all symbols.
        """
        if not self._subscriptions:
            return

        grouped: dict[str, set[str]] = {}
        for key in self._subscriptions:
            try:
                topic, symbol = key.split("|", 1)
            except ValueError:
                # Skip malformed keys
                continue
            grouped.setdefault(topic, set()).add(symbol)

        ts = str(self._clock.timestamp_ms())
        for topic, symbols in grouped.items():
            if not symbols:
                continue
            payload = {
                "id": ts,
                "type": "subscribe",
                "topic": topic + ":" + ",".join(symbols),
                "response": True,
            }
            self._send(payload)

    async def _unsubscribe(self, topics: List[dict[str, str]]) -> None:
        if not topics:
            return

        remove_topics: List[dict[str, str]] = []
        for t in topics:
            key = f"{t['topic']}|{t.get('symbol', '')}"
            if key not in self._subscriptions:
                continue
            self._subscriptions.remove(key)
            remove_topics.append(t)

        if not remove_topics:
            return

        await self.connect()

        payload = {
            "id": str(self._clock.timestamp_ms()),
            "type": "unsubscribe",
            "topic": remove_topics[0]["topic"] + ":"
            + ",".join({tp["symbol"] for tp in remove_topics}),
            "response": True,
        }
        self._send(payload)

    async def _manage_subscription(
        self,
        action: str,
        symbols: List[str],
        *,
        topic: str,
        symbol_builder: Callable[[str], str] | None = None,
    ) -> None:

        if not symbols:
            return

        symbols = [s.upper() for s in symbols]

        if symbol_builder is not None:
            built_symbols = [symbol_builder(s) for s in symbols]
        else:
            built_symbols = symbols

        topics = [{"symbol": s, "topic": topic} for s in built_symbols]

        if action == "subscribe":
            await self._subscribe(topics)
        else:
            await self._unsubscribe(topics)

    async def _manage_private_subscription(self, action: str, topic: str) -> None:

        await self.connect()

        payload = {
            "id": str(self._clock.timestamp_ms()),
            "type": action,
            "topic": topic,
            "privateChannel": True,
            "response": True,
        }
        self._send(payload)

    async def subscribe_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/market/match",
        )

    async def unsubscribe_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/market/match",
        )

    async def subscribe_kline(
        self,
        symbols: List[str],
        interval: str,
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/market/candles",
            symbol_builder=lambda s: f"{s}_{interval}",
        )

    async def unsubscribe_kline(
        self,
        symbols: List[str],
        interval: str,
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/market/candles",
            symbol_builder=lambda s: f"{s}_{interval}",
        )

    async def subscribe_futures_kline(
        self,
        symbols: List[str],
        interval: str,
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/contractMarket/limitCandle",
            symbol_builder=lambda s: f"{s}_{interval}",
        )

    async def unsubscribe_futures_kline(
        self,
        symbols: List[str],
        interval: str,
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/contractMarket/limitCandle",
            symbol_builder=lambda s: f"{s}_{interval}",
        )

    async def subscribe_futures_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/contractMarket/execution",
        )

    async def unsubscribe_futures_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/contractMarket/execution",
        )

    async def subscribe_book_l1(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level1",
        )

    async def unsubscribe_book_l1(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/spotMarket/level1",
        )

    async def subscribe_book_l5(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level2Depth5",
        )

    async def unsubscribe_book_l5(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/spotMarket/level2Depth5",
        )

    async def subscribe_futures_book_l5(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/contractMarket/level2Depth5",
            require_futures=True,
        )

    async def unsubscribe_futures_book_l5(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/contractMarket/level2Depth5",
            require_futures=True,
        )

    async def subscribe_book_l50(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level2Depth50",
        )

    async def unsubscribe_book_l50(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/spotMarket/level2Depth50",
        )

    async def subscribe_futures_book_l50(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/contractMarket/level2Depth50",
        )

    async def unsubscribe_futures_book_l50(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/contractMarket/level2Depth50",
        )

    async def subscribe_book_incremental(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/market/level2",
        )

    async def unsubscribe_book_incremental(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/market/level2",
        )

    async def subscribe_futures_book_incremental(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/contractMarket/level2",
        )

    async def unsubscribe_futures_book_incremental(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/contractMarket/level2",
        )


    async def subscribe_balance(self) -> None:
        await self._manage_private_subscription("subscribe", "/account/balance")

    async def unsubscribe_balance(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/account/balance")

    async def subscribe_futures_balance(self) -> None:
        await self._manage_private_subscription("subscribe", "/contractAccount/wallet")

    async def unsubscribe_futures_balance(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/contractAccount/wallet")

    async def subscribe_order_v2(self) -> None:
        await self._manage_private_subscription("subscribe", "/spotMarket/tradeOrdersV2")

    async def unsubscribe_order_v2(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/spotMarket/tradeOrdersV2")

    async def subscribe_order_v1(self) -> None:
        await self._manage_private_subscription("subscribe", "/spotMarket/tradeOrders")

    async def unsubscribe_order_v1(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/spotMarket/tradeOrders")
        
    async def subscribe_futures_positions(self) -> None:
        await self._manage_private_subscription("subscribe", "/contract/positionAll")

    async def unsubscribe_futures_positions(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/contract/positionAll")

    async def subscribe_futures_orders(self) -> None:
        await self._manage_private_subscription("subscribe", "/contractMarket/tradeOrders")

    async def unsubscribe_futures_orders(self) -> None:
        await self._manage_private_subscription("unsubscribe", "/contractMarket/tradeOrders")

class KucoinWSApiClient(WSClient):
    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        *,
        url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        ws_url = url or "wss://wsapi.kucoin.com/v1/private"

        super().__init__(
            url=ws_url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    async def connect(self) -> None:
        await super().connect()
        ts = self._clock.timestamp_ms()
        # Basic login frame following op-style convention
        login_args: Dict[str, Any] = {
            "apiKey": self._api_key,
            "passphrase": self._passphrase,
            "timestamp": ts,
            "sign": self._kucoin_ws_signature(str(ts)),
        }
        payload = {"id": str(ts), "op": "login", "args": login_args}
        self._send(payload)

    def _kucoin_ws_signature(self, query: str) -> str:
        import hmac
        import hashlib
        import base64

        digest = hmac.new(
            self._secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    async def add_order(
        self,
        id: str,
        op: Literal["futures.order", "spot.order"],
        *,
        price: str,
        quantity: float | int,
        side: str,
        symbol: str,
        timeInForce: str,
        timestamp: int,
        type: str,
    ) -> None:
        
        args: Dict[str, Any] = {
            "price": price,
            "quantity": quantity,
            "side": side,
            "symbol": symbol,
            "timeInForce": timeInForce,
            "timestamp": timestamp,
            "type": type,
        }

        payload = {"id": id, "op": op, "args": args}
        self._send(payload)

    async def spot_add_order(
        self,
        id: str,
        *,
        price: str,
        quantity: float | int,
        side: str,
        symbol: str,
        timeInForce: str,
        timestamp: int,
        type: str,
    ) -> None:
        
        await self.add_order(
            id,
            op="spot.order",
            price=price,
            quantity=quantity,
            side=side,
            symbol=symbol,
            timeInForce=timeInForce,
            timestamp=timestamp,
            type=type,
        )

    async def futures_add_order(
        self,
        id: str,
        *,
        price: str,
        quantity: float | int,
        side: str,
        symbol: str,
        timeInForce: str,
        timestamp: int,
        type: str,
    ) -> None:
        
        await self.add_order(
            id,
            op="futures.order",
            price=price,
            quantity=quantity,
            side=side,
            symbol=symbol,
            timeInForce=timeInForce,
            timestamp=timestamp,
            type=type,
        )

    async def cancel_order(
        self,
        id: str,
        *,
        op: Literal["spot.cancel", "futures.cancel"],
        symbol: str | None = None,
        clientOid: str | None = None,
        orderId: str | None = None,
    ) -> None:
        args: Dict[str, Any] = {
            "symbol": symbol,
            "clientOid": clientOid,
            "orderId": orderId,
        }
        args = {k: v for k, v in args.items() if v is not None}

        payload = {"id": id, "op": op, "args": args}
        self._send(payload)

    async def spot_cancel_order(
        self,
        id: str,
        *,
        symbol: str | None = None,
        clientOid: str | None = None,
        orderId: str | None = None,
    ) -> None:
        await self.cancel_order(id, op="spot.cancel", symbol=symbol, clientOid=clientOid, orderId=orderId)

    async def futures_cancel_order(
        self,
        id: str,
        *,
        symbol: str | None = None,
        clientOid: str | None = None,
        orderId: str | None = None,
    ) -> None:
        await self.cancel_order(id, op="futures.cancel", symbol=symbol, clientOid=clientOid, orderId=orderId)


import asyncio  # noqa
import argparse
import msgspec

from nexustrader.exchange.kucoin.rest_api import KucoinApiClient


async def _fetch_ws_url(clock: LiveClock, *, futures: bool, private: bool, api_key: str | None, secret: str | None, passphrase: str | None) -> str:
    """Fetch KuCoin WS endpoint + token via bullet API and compose ws url."""
    account = KucoinAccountType.FUTURES if futures else KucoinAccountType.SPOT
    base_url = account.base_url

    client = KucoinApiClient(clock=clock, api_key=api_key if private else None, secret=secret if private else None)
    if private and passphrase:
        setattr(client, "_passphrase", passphrase)

    endpoint = "/api/v1/bullet-private" if private else "/api/v1/bullet-public"
    raw = await client._fetch("POST", base_url, endpoint, payload={}, signed=private, response_type=None)
    dec = msgspec.json.Decoder(type=dict)
    data = dec.decode(raw).get("data", {})
    token = data.get("token")
    servers = data.get("instanceServers") or []
    if not token or not servers:
        raise RuntimeError("Failed to fetch KuCoin WS token or servers")
    url = servers[0].get("endpoint")
    if not url:
        raise RuntimeError("Invalid WS server endpoint from KuCoin response")
    connect_id = str(clock.timestamp_ms())
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}&connectId={connect_id}"


async def _main_trade(args: argparse.Namespace) -> None:
    """CLI runner to test subscribing to spot public trade channel.

    Mirrors the style of rest_api.py's main: parses args, runs, prints results.
    """
    from nexustrader.core.entity import TaskManager
    from nexustrader.core.nautilius_core import LiveClock
    import msgspec

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()

    decoder = msgspec.json.Decoder(object)

    def handler(raw: bytes):
        try:
            msg = decoder.decode(raw)
        except Exception:
            print(raw)
            return
        try:
            data = msg.get("data", {})
            topic = msg.get("topic")
            # Try to print compact trade info if available
            price = data.get("price") or data.get("dealPrice")
            size = data.get("size") or data.get("quantity") or data.get("dealQuantity")
            symbol = data.get("symbol") or (topic.split(":", 1)[1] if topic and ":" in topic else None)
            time_ = data.get("time") or data.get("ts")
            side = data.get("side")
            if topic and topic.startswith("/market/match"):
                print({
                    "symbol": symbol,
                    "price": price,
                    "size": size,
                    "side": side,
                    "ts": time_,
                })
            else:
                print({"topic": topic, "data": data})
        except Exception:
            print(msg)

    # Minimal dummy account type for constructor
    # Compose WS URL with token if provided or requested to fetch
    futures = getattr(args, "futures", False)
    ws_url: str | None = None

    if args.token:
        base = args.url or ("wss://ws-api-futures.kucoin.com" if futures else "wss://ws-api-spot.kucoin.com")
        sep = "&" if "?" in base else "?"
        ws_url = f"{base}{sep}token={args.token}&connectId={clock.timestamp_ms()}"
    elif args.fetch_token:
        ws_url = await _fetch_ws_url(
            clock,
            futures=futures,
            private=args.private,
            api_key=args.api_key,
            secret=args.secret,
            passphrase=args.passphrase,
        )
    else:
        # Raw URL without token (may be rejected by server if token required)
        ws_url = args.url or ("wss://ws-api-futures.kucoin.com" if futures else "wss://ws-api-spot.kucoin.com")

    class _DummyAccount:
        stream_url = ws_url

    client = KucoinWSClient(
        account_type=_DummyAccount(),
        handler=handler,
        task_manager=task_manager,
        clock=clock,
        custom_url=ws_url,
    )

    symbols = [s.upper() for s in args.symbols]
    if getattr(args, "futures", False):
        await client.subscribe_futures_trade(symbols)
    else:
        await client.subscribe_trade(symbols)

    try:
        await asyncio.sleep(args.duration)
    finally:
        client.disconnect()


# Removed old kline test runner to keep CLI focused


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test KuCoin WS subscriptions")
    subparsers = parser.add_subparsers(dest="mode", required=False)

    p_trade = subparsers.add_parser("trade", help="Subscribe to trades (spot or futures)")
    p_trade.add_argument("--symbols", nargs="+", default=["BTC-USDT"], help="Symbols e.g. BTC-USDT ETH-USDT")
    p_trade.add_argument("--futures", action="store_true", help="Use futures trade stream")
    # Token options
    p_trade.add_argument("--token", default=None, help="Use an explicit WS token (skips fetching)")
    p_trade.add_argument("--fetch-token", action="store_true", help="Fetch a WS token via bullet API")
    p_trade.add_argument("--private", action="store_true", help="Fetch private WS token; requires API credentials")
    p_trade.add_argument("--api-key", default=None, help="KuCoin API key for private token")
    p_trade.add_argument("--secret", default=None, help="KuCoin API secret for private token")
    p_trade.add_argument("--passphrase", default=None, help="KuCoin API passphrase for private token")
    # URL and duration
    p_trade.add_argument("--url", default=None, help="Custom WS base URL; overridden if --fetch-token is used")
    p_trade.add_argument("--duration", type=int, default=30, help="Run seconds before exit")

    # (kline subcommand removed)

    # Private subscriptions: orders/balance/positions via bullet-private token
    p_priv = subparsers.add_parser("private", help="Subscribe to private streams (orders/balance/positions)")
    p_priv.add_argument("--futures", action="store_true", help="Use futures private streams")
    p_priv.add_argument("--orders", action="store_true", help="Subscribe to private order updates")
    p_priv.add_argument("--balance", action="store_true", help="Subscribe to private balance updates")
    p_priv.add_argument("--positions", action="store_true", help="Subscribe to private positions (futures only)")
    # Token options
    p_priv.add_argument("--token", default=None, help="Explicit private WS token; skips fetching")
    p_priv.add_argument("--url", default=None, help="Custom WS base URL (used with --token)")
    # Credentials for fetching bullet-private token
    p_priv.add_argument("--api-key", default=None, help="KuCoin API key")
    p_priv.add_argument("--secret", default=None, help="KuCoin API secret")
    p_priv.add_argument("--passphrase", default=None, help="KuCoin API passphrase")
    p_priv.add_argument("--duration", type=int, default=30, help="Run seconds before exit")

    args = parser.parse_args()
    mode = args.mode or "trade"
    if mode == "trade":
        asyncio.run(_main_trade(args))
    else:
        # Dispatch based on selected mode (private only)
        if mode == "private":
            async def _main_private(args: argparse.Namespace) -> None:
                from nexustrader.core.entity import TaskManager
                from nexustrader.core.nautilius_core import LiveClock
                import msgspec

                loop = asyncio.get_event_loop()
                task_manager = TaskManager(loop=loop)
                clock = LiveClock()

                decoder = msgspec.json.Decoder(object)

                def handler(raw: bytes):
                    try:
                        msg = decoder.decode(raw)
                    except Exception:
                        print(raw)
                        return
                    topic = msg.get("topic") or msg.get("subject")
                    data = msg.get("data")
                    print({"topic": topic, "data": data})

                futures = getattr(args, "futures", False)

                # Build WS URL: either use explicit token with base, or fetch private token
                if args.token:
                    base = args.url or ("wss://ws-api-futures.kucoin.com" if futures else "wss://ws-api-spot.kucoin.com")
                    sep = "&" if "?" in base else "?"
                    ws_url = f"{base}{sep}token={args.token}&connectId={clock.timestamp_ms()}"
                else:
                    # Ensure credentials provided
                    if not (args.api_key and args.secret and args.passphrase):
                        raise RuntimeError("Private token fetch requires --api-key, --secret, and --passphrase")
                    ws_url = await _fetch_ws_url(
                        clock,
                        futures=futures,
                        private=True,
                        api_key=args.api_key,
                        secret=args.secret,
                        passphrase=args.passphrase,
                    )

                class _DummyAccount:
                    stream_url = ws_url

                client = KucoinWSClient(
                    account_type=_DummyAccount(),
                    handler=handler,
                    task_manager=task_manager,
                    clock=clock,
                    custom_url=ws_url,
                )

                # Subscribe to selected private topics
                any_selected = False
                if futures:
                    if getattr(args, "orders", False):
                        await client.subscribe_futures_orders(); any_selected = True
                    if getattr(args, "positions", False):
                        await client.subscribe_futures_positions(); any_selected = True
                    if getattr(args, "balance", False):
                        await client.subscribe_futures_balance(); any_selected = True
                    if not any_selected:
                        await client.subscribe_futures_orders()
                else:
                    if getattr(args, "orders", False):
                        await client.subscribe_order_v2(); any_selected = True
                    if getattr(args, "balance", False):
                        await client.subscribe_balance(); any_selected = True
                    if not any_selected:
                        await client.subscribe_order_v2()

                try:
                    await asyncio.sleep(args.duration)
                finally:
                    client.disconnect()

            asyncio.run(_main_private(args))
        else:
            parser.print_help()


from typing import Any, Callable, List, Literal, Dict

from nexustrader.base.ws_client import WSClient
from picows import WSMsgType
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, hmac_signature
from urllib.parse import quote
import base64
import msgspec
import json
from nexustrader.exchange.kucoin.constants import KucoinAccountType
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient
import websocket
class KucoinWSClient(WSClient):
    def __init__(
        self,
        account_type: KucoinAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        custom_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._account_type = account_type

        url = custom_url or account_type.stream_url
        if not url:
            raise ValueError(f"WebSocket URL not supported for {account_type}")

        if token:
            sep = "&" if "?" in url else "?"
            connect_id = str(clock.timestamp_ms())
            url = f"{url}{sep}token={token}&connectId={connect_id}"

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
        if not self._subscriptions:
            return

        grouped: dict[str, set[str]] = {}
        for key in self._subscriptions:
            try:
                topic, symbol = key.split("|", 1)
            except ValueError:
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

    async def subscribe_spot_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/market/match",
        )

    async def unsubscribe_spot_trade(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/market/match",
        )

    async def subscribe_spot_kline(
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

    async def unsubscribe_spot_kline(
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

    async def subscribe_spot_book_l1(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level1",
        )

    async def unsubscribe_spot_book_l1(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "unsubscribe",
            symbols,
            topic="/spotMarket/level1",
        )

    async def subscribe_spot_book_l5(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level2Depth5",
        )

    async def unsubscribe_spot_book_l5(
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

    async def subscribe_spot_book_l50(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/spotMarket/level2Depth50",
        )

    async def unsubscribe_spot_book_l50(
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

    async def subscribe_spot_book_incremental(
        self,
        symbols: List[str],
    ) -> None:
        await self._manage_subscription(
            "subscribe",
            symbols,
            topic="/market/level2",
        )

    async def unsubscribe_spot_book_incremental(
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



class KucoinWSApiClient(WSClient):
    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        use_futures: bool = False,
        api_key_version: int = 2,
    ) -> None:
        self._api_key = api_key
        self._secret = secret
        self._passphrase = passphrase
        self._private_subscriptions: set[str] = set()
        self._api_key_version = api_key_version
        self._use_futures = use_futures
        self._user_handler = handler
        self._decoder = msgspec.json.Decoder(type=dict)
        self._session_verified = False
        self._welcome_received = False
        self._ws = None 
        self._balance_wsclient = None

        ws_url = "wss://wsapi.kucoin.com"

        super().__init__(
            url=ws_url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    @staticmethod
    def _wsapi_sign(message: str, secret: str) -> str:
        hex_digest = hmac_signature(secret, message)
        return base64.b64encode(bytes.fromhex(hex_digest)).decode("utf-8")

    async def connect(self) -> None:
        timestamp = str(self._clock.timestamp_ms())
        url_path = f"apikey={self._api_key}&timestamp={timestamp}"
        sign_value = quote(self._wsapi_sign(f"{self._api_key}{timestamp}", self._secret))
        passphrase_sign = quote(self._wsapi_sign(self._passphrase, self._secret))
        ws_url = f"wss://wsapi.kucoin.com/v1/private?{url_path}&sign={sign_value}&passphrase={passphrase_sign}"

        self._url = ws_url
        ws = websocket.create_connection(ws_url)
        print(f"Connected to WebSocket server: {ws_url}")
        auth_response = ws.recv()
        print(f"Received session message: {auth_response}")
        session_info = self._wsapi_sign(auth_response, self._secret)
        ws.send(session_info)
        welcome_msg = ws.recv()
        print(f"Received session message: {welcome_msg}")
        self._ws = ws

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
        clientOid: str | None = None,
        reduceOnly: bool | None = None,
        leverage: str | None = None,
        marginMode: str | None = None,
    ) -> None:
        if not self._ws:
            self._ws = await self.connect()    
        args: Dict[str, Any] = {
            "price": price,
            "size": quantity,
            "side": side,
            "symbol": symbol,
            "timeInForce": timeInForce,
            "timestamp": timestamp,
            "type": type,
            "clientOid": clientOid or id,
        }
        if reduceOnly is not None and op == "futures.order":
            args["reduceOnly"] = reduceOnly
        if leverage is not None and op == "futures.order":
            args["leverage"] = leverage
        if marginMode is not None and op == "futures.order":
            args["marginMode"] = marginMode

        payload = {"id": id, "op": op, "args": args}

        self._ws.send(json.dumps(payload, ensure_ascii=False))
        raw = self._ws.recv()
        try:
            print(raw)
            return json.loads(raw)
        except Exception:
            return {"raw": raw}

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
        clientOid: str | None = None,
        reduceOnly: bool | None = None,
    ) -> None:
        
        return await self.add_order(
            id,
            op="spot.order",
            price=price,
            quantity=quantity,
            side=side,
            symbol=symbol,
            timeInForce=timeInForce,
            timestamp=timestamp,
            type=type,
            clientOid=clientOid,
            reduceOnly=reduceOnly,
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
        clientOid: str | None = None,
        reduceOnly: bool | None = None,
        leverage: str | None = None,
        marginMode: str | None = None,
    ) -> None:
        
        return await self.add_order(
            id,
            op="futures.order",
            price=price,
            quantity=quantity,
            side=side,
            symbol=symbol,
            timeInForce=timeInForce,
            timestamp=timestamp,
            type=type,
            clientOid=clientOid,
            reduceOnly=reduceOnly,
            leverage=leverage,
            marginMode=marginMode,
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
        if not self._ws:
            self._ws = await self.connect() 
        args: Dict[str, Any] = {
            "symbol": symbol,
            "clientOid": clientOid,
            "orderId": orderId,
        }
        args = {k: v for k, v in args.items() if v is not None}

        payload = {"id": id, "op": op, "args": args}
        
        self._ws.send(json.dumps(payload, ensure_ascii=False))
        raw = self._ws.recv()
        try:
            print(raw)
            return json.loads(raw)
        except Exception:
            return {"raw": raw}

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

        if action == "subscribe":
            self._private_subscriptions.add(topic)
        elif action == "unsubscribe":
            self._private_subscriptions.discard(topic)

    async def _resubscribe(self) -> None:
        if not self._private_subscriptions:
            return
        await self.connect()
        ts = str(self._clock.timestamp_ms())
        for topic in list(self._private_subscriptions):
            payload = {
                "id": ts,
                "type": "subscribe",
                "topic": topic,
                "privateChannel": True,
                "response": True,
            }
            self._send(payload)


import asyncio
import argparse
import msgspec

from nexustrader.exchange.kucoin.rest_api import KucoinApiClient

async def _main_trade(args: argparse.Namespace) -> None:
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()

    decoder = msgspec.json.Decoder(type=dict)

    def handler(raw: bytes):
        try:
            msg = decoder.decode(raw)
            data = msg.get("data", {})
            topic = msg.get("topic", "")
            if topic.startswith("/market/match"):
                price = data.get("price") or data.get("dealPrice")
                size = data.get("size") or data.get("quantity") or data.get("dealQuantity")
                symbol = data.get("symbol")
                ts = data.get("time") or data.get("ts")
                side = data.get("side")
                print({"symbol": symbol, "price": price, "size": size, "side": side, "ts": ts})
        except Exception:
            print(raw)

    api_client = KucoinApiClient(clock=clock)
    ws_url = await api_client.fetch_ws_url(futures=False, private=False)

    class _DummyAccount:
        stream_url = ws_url

    client = KucoinWSClient(
        account_type=_DummyAccount(),
        handler=handler,
        task_manager=task_manager,
        clock=clock,
        custom_url=ws_url,
        token=None,
    )

    symbols = [s.upper() for s in getattr(args, "symbols", ["BTC-USDT"])]
    await client.subscribe_spot_trade(symbols)
    await asyncio.sleep(5)
    await client.unsubscribe_spot_trade(symbols) 
    client.disconnect()
       
async def _main_futures_book_l50() -> None:
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()

    decoder = msgspec.json.Decoder(type=dict)

    def handler(raw: bytes):
        try:
            msg = decoder.decode(raw)
            topic = msg.get("topic", "")
            data = msg.get("data", {})
            if topic.startswith("/contractMarket/level2Depth50"):
                bids = data.get("bids") or []
                asks = data.get("asks") or []
                print({"topic": topic, "bids": len(bids), "asks": len(asks)})
        except Exception:
            print(raw)

    api_client = KucoinApiClient(clock=clock)
    ws_url = await api_client.fetch_ws_url(futures=True, private=False)

    class _DummyFutures:
        stream_url = ws_url

    client = KucoinWSClient(
        account_type=_DummyFutures(),
        handler=handler,
        task_manager=task_manager,
        clock=clock,
        custom_url=ws_url,
        token=None,
    )

    symbols = ["XBTUSDTM"]
    await client.subscribe_futures_book_l50(symbols)
    await asyncio.sleep(2)
    await client.unsubscribe_futures_book_l50(symbols)

    client.disconnect()

async def _main_private_subscription(args: argparse.Namespace) -> None:
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()

    dec = msgspec.json.Decoder(type=dict)

    def handler(raw: bytes):
        try:
            msg = dec.decode(raw)
            print(msg)
        except Exception:
            print(raw)

    API_KEY = args.api_key
    SECRET = args.secret
    PASSPHRASE = args.passphrase

    client = KucoinWSApiClient(
        api_key=API_KEY,
        secret=SECRET,
        passphrase=PASSPHRASE,
        handler=handler,
        task_manager=task_manager,
        clock=clock,
        use_futures=False,
    )

    await client.subscribe_spot_balance()
    await asyncio.sleep(5)
    await client.unsubscribe_spot_balance()

    client.disconnect()

async def _main_futures_order_ws(args: argparse.Namespace) -> None:
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()

    dec = msgspec.json.Decoder(type=dict)

    def handler(raw: bytes):
        try:
            msg = dec.decode(raw)
            print(msg)
        except Exception:
            print(raw)

    API_KEY = args.api_key
    SECRET = args.secret
    PASSPHRASE = args.passphrase

    client = KucoinWSApiClient(
        api_key=API_KEY,
        secret=SECRET,
        passphrase=PASSPHRASE,
        handler=handler,
        task_manager=task_manager,
        clock=clock,
        use_futures=True,
    )

    ts = clock.timestamp_ms()
    order_id = f"order-{ts}"
    symbol = "XBTUSDTM"

    # await client.futures_add_order(
    #     id=order_id,
    #     price="1",
    #     quantity=1,
    #     side="buy",
    #     symbol=symbol,
    #     timeInForce="GTC",
    #     timestamp=ts,
    #     type="limit",
    #     leverage="1",
    #     marginMode="CROSS",
    # )

    # Give a moment for server to process
    await asyncio.sleep(2)

    # Cancel all open orders for the symbol
    await client.futures_cancel_order(id=f"cancel-{ts}", symbol=symbol, )

    # Wait briefly to receive cancellation events
    await asyncio.sleep(3)

    client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KuCoin WS tests: spot trades, futures book L50, private balance")
    parser.add_argument("--api-key", required=True, help="KuCoin API key (private test)")
    parser.add_argument("--secret", required=True, help="KuCoin API secret (private test)")
    parser.add_argument("--passphrase", required=True, help="KuCoin API passphrase (private test)")
    _args = parser.parse_args()

    async def _main_all():
        args = argparse.Namespace(
            symbols=["BTC-USDT"],
            duration=30,
        )
        #await _main_trade(args)
        #await _main_futures_book_l50()
        #await _main_private_subscription(_args)
        await _main_futures_order_ws(_args)

    asyncio.run(_main_all())
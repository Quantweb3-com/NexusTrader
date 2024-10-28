import asyncio
import time
import ssl
import certifi
import orjson
import msgspec
import aiohttp
import aiosonic
import ccxt.pro as ccxtpro
import aiosonic.exceptions as aiosonic_exceptions

from abc import ABC, abstractmethod
from typing import Dict, List, Any
from typing import Callable, Literal
from collections import defaultdict
from decimal import Decimal
from urllib.parse import urlparse


from asynciolimiter import Limiter
from ccxt.base.errors import RequestTimeout
from aiohttp.client_exceptions import ClientResponseError, ClientError


from tradebot.log import SpdLog
from tradebot.exceptions import OrderError, ExchangeResponseError
from picows import (
    ws_connect,
    WSFrame,
    WSTransport,
    WSListener,
    WSMsgType,
)


class ExchangeManager(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key", None)
        self.secret = config.get("secret", None)
        self.exchange_id = config.get("exchange_id", None)
        self.api = self._init_exchange()
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )
        self.market = None
        self.market_id = None

        if not self.api_key or not self.secret:
            self._log.warn(
                "API Key and Secret not provided, So some features related to trading will not work"
            )

    def _init_exchange(self) -> ccxtpro.Exchange:
        try:
            exchange_class = getattr(ccxtpro, self.config["exchange_id"])
        except AttributeError:
            raise AttributeError(
                f"Exchange {self.config['exchange_id']} is not supported"
            )

        api = exchange_class(self.config)
        api.set_sandbox_mode(
            self.config.get("sandbox", False)
        )  # Set sandbox mode if demo trade is enabled
        return api

    async def load_markets(self):
        self.market = await self.api.load_markets()
        return self.market

    async def close(self):
        await self.api.close()


class AccountManager(ABC):
    pass


class OrderManager(ABC):
    def __init__(self, exchange: ExchangeManager):
        self._exchange = exchange
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )

    @abstractmethod
    async def handle_request_timeout(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        pass

    async def place_limit_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: Decimal,
        price: Decimal,
        handle_timeout: bool = True,
        **params,
    ) -> Dict[str, Any]:
        try:
            res = await self._exchange.api.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=price,
                params=params,
            )
            return res
        except RequestTimeout:
            if handle_timeout:
                return await self.handle_request_timeout(
                    "place_limit_order",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": price,
                        **params,
                    },
                )
            else:
                return OrderError(
                    "Request Timeout",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": price,
                        **params,
                    },
                )
        except Exception as e:
            return OrderError(
                e,
                {
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    **params,
                },
            )

    async def place_limit_order_ws(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: Decimal,
        price: Decimal,
        handle_timeout: bool = True,
        **params,
    ) -> Dict[str, Any]:
        try:
            res = await self._exchange.api.create_order_ws(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=price,
                params=params,
            )
            return res
        except RequestTimeout:
            if handle_timeout:
                return await self.handle_request_timeout(
                    "place_limit_order_ws",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": price,
                        **params,
                    },
                )
            else:
                return OrderError(
                    "Request Timeout",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": price,
                        **params,
                    },
                )
        except Exception as e:
            return OrderError(
                e,
                {
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    **params,
                },
            )

    async def place_market_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: Decimal,
        handle_timeout: bool = True,
        **params,
    ) -> Dict[str, Any]:
        try:
            res = await self._exchange.api.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=params,
            )
            return res
        except RequestTimeout:
            if handle_timeout:
                return await self.handle_request_timeout(
                    "place_market_order",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": None,
                        **params,
                    },
                )
            else:
                return OrderError(
                    "Request Timeout",
                    {"symbol": symbol, "side": side, "amount": amount, **params},
                )
        except Exception as e:
            return OrderError(
                e, {"symbol": symbol, "side": side, "amount": amount, **params}
            )

    async def place_market_order_ws(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: Decimal,
        handle_timeout: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            res = await self._exchange.api.create_order_ws(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=kwargs,
            )
            return res
        except RequestTimeout:
            if handle_timeout:
                return await self.handle_request_timeout(
                    "place_market_order_ws",
                    {
                        "symbol": symbol,
                        "side": side,
                        "amount": amount,
                        "price": None,
                        **kwargs,
                    },
                )
            else:
                return OrderError(
                    "Request Timeout",
                    {"symbol": symbol, "side": side, "amount": amount, **kwargs},
                )
        except Exception as e:
            return OrderError(
                e, {"symbol": symbol, "side": side, "amount": amount, **kwargs}
            )

    async def cancel_order(
        self, id: str, symbol: str, handle_timeout: bool = True, **params
    ) -> Dict[str, Any]:  # 修改此行
        try:
            res = await self._exchange.api.cancel_order(id, symbol, params=params)
            return res
        except RequestTimeout:
            if handle_timeout:
                return await self.handle_request_timeout(
                    "cancel_order", {"id": id, "symbol": symbol, **params}
                )
            else:
                return OrderError(
                    "Request Timeout", {"id": id, "symbol": symbol, **params}
                )
        except Exception as e:
            return OrderError(e, {"id": id, "symbol": symbol, **params})

    async def cancel_order_ws(
        self, id: str, symbol: str, handle_timeout: bool = True, **params
    ) -> Dict[str, Any]:  # 修改此行
        try:
            res = await self._exchange.api.cancel_order_ws(id, symbol, params=params)
            return res
        except RequestTimeout:
            if handle_timeout:
                res = await self.handle_request_timeout(
                    "cancel_order_ws", {"id": id, "symbol": symbol, **params}
                )
                return res
            else:
                return OrderError(
                    "Request Timeout", {"id": id, "symbol": symbol, **params}
                )
        except Exception as e:
            return OrderError(e, {"id": id, **params})


# archive
class WebsocketManager(ABC):
    def __init__(
        self,
        base_url: str,
        ping_interval: int = 5,
        ping_timeout: int = 5,
        close_timeout: int = 1,
        max_queue: int = 12,
    ):
        self._base_url = base_url
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._close_timeout = close_timeout
        self._max_queue = max_queue

        self._tasks: List[asyncio.Task] = []
        self._subscripions = defaultdict(asyncio.Queue)
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )

    async def _consume(
        self, subscription_id: str, callback: Callable[..., Any] = None, *args, **kwargs
    ):
        while True:
            msg = await self._subscripions[subscription_id].get()
            if asyncio.iscoroutinefunction(callback):
                await callback(msg, *args, **kwargs)
            else:
                callback(msg, *args, **kwargs)
            self._subscripions[subscription_id].task_done()

    @abstractmethod
    async def _subscribe(self, symbol: str, typ: str, channel: str, queue_id: str):
        pass

    async def close(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._log.info("All WebSocket connections closed.")


class WSClient(WSListener):
    def __init__(self, logger):
        self._log = logger
        self.msg_queue = asyncio.Queue()

    def on_ws_connected(self, transport: WSTransport):
        self._log.info("Connected to Websocket...")

    def on_ws_disconnected(self, transport: WSTransport):
        self._log.info("Disconnected from Websocket.")

    def on_ws_frame(self, transport: WSTransport, frame: WSFrame):
        if frame.msg_type == WSMsgType.PING:
            transport.send_pong(frame.get_payload_as_bytes())
            return
        msg = orjson.loads(frame.get_payload_as_bytes())
        # msg = self._decoder.decode(frame.get_payload_as_bytes())
        self.msg_queue.put_nowait(msg)


class WSManager(ABC):
    def __init__(self, url: str, limiter: Limiter, handler: Callable[..., Any]):
        self._url = url
        self._reconnect_interval = 0.2  # Reconnection interval in seconds
        self._ping_idle_timeout = 2
        self._ping_reply_timeout = 1
        self._listener = None
        self._transport = None
        self._subscriptions = {}
        self._limiter = limiter
        self._msg_handler_task = None
        self._connection_handler_task = None
        # self._encoder = msgspec.json.Encoder()
        self._callback = handler
        self._log = SpdLog.get_logger(type(self).__name__, level="INFO", flush=True)

    @property
    def connected(self):
        return self._transport and self._listener

    async def _connect(self):
        WSClientFactory = lambda: WSClient(self._log)  # noqa: E731
        self._transport, self._listener = await ws_connect(
            WSClientFactory,
            self._url,
            enable_auto_ping=True,
            auto_ping_idle_timeout=self._ping_idle_timeout,
            auto_ping_reply_timeout=self._ping_reply_timeout,
        )

    async def connect(self):
        if not self.connected:
            await self._connect()
            self._msg_handler_task = asyncio.create_task(
                self._msg_handler(self._listener.msg_queue)
            )
            self._connection_handler_task = asyncio.create_task(
                self._connection_handler()
            )

    async def _connection_handler(self):
        while True:
            try:
                if not self.connected:
                    await self._connect()
                    self._msg_handler_task = asyncio.create_task(
                        self._msg_handler(self._listener.msg_queue)
                    )
                    await self._resubscribe()
                await self._transport.wait_disconnected()
            except Exception as e:
                self._log.error(f"Connection error: {e}")
            finally:
                self._log.info("Websocket reconnecting...")
                if self._msg_handler_task:
                    self._msg_handler_task.cancel()
                self._transport, self._listener = None, None
                await asyncio.sleep(self._reconnect_interval)

    def _send(self, payload: dict):
        self._transport.send(WSMsgType.TEXT, orjson.dumps(payload))

    async def _msg_handler(self, queue: asyncio.Queue):
        while True:
            msg = await queue.get()
            # TODO: handle different event types of messages
            self._callback(msg)
            queue.task_done()

    def disconnect(self):
        if self.connected:
            self._transport.disconnect()

    @abstractmethod
    async def _resubscribe(self):
        pass


class RestApi2:
    def __init__(self, **client_kwargs):
        self._client = None
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )
        self._client_kwargs = client_kwargs
        self.init_client()

    def init_client(self):
        if self._client is None:
            timeouts = aiosonic.timeout.Timeouts(request_timeout=10)
            tcp_connector = aiosonic.connectors.TCPConnector(timeouts=timeouts)
            self._client = aiosonic.HTTPClient(connector=tcp_connector, **self._client_kwargs)

    async def request(self, method: str, url: str, **kwargs) -> Any:
        try:
            response = await self._client.request(url=url, method=method, json_serializer=orjson.dumps, **kwargs)
            if response.ok:
                return await response.json()
        except aiosonic_exceptions.RequestTimeout:
            self._log.error(f"Request Timeout for URL: {url}, kwargs: {kwargs}")
            raise
        except Exception as e:
            self._log.error(f"Exception: {str(e)} for URL: {url}, kwargs: {kwargs}")
            raise


class RestApi:
    def __init__(self, **client_kwargs):
        self._session = None
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )
        self._client_kwargs = client_kwargs
        self._loop = asyncio.get_event_loop()
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        

    def init_session(self):
        if self._session is None:
            tcp_connector = aiohttp.TCPConnector(ssl=self._ssl_context, loop=self._loop, enable_cleanup_closed=True)
            self._session = aiohttp.ClientSession(loop=self._loop ,connector=tcp_connector, json_serialize=orjson.dumps, **self._client_kwargs)

    async def close_session(self):
        if self._session:
            await self._session.close()

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Any:
        if "application/json" in response.headers.get("Content-Type", ""):
            return await response.json()
        else:
            return await response.text()

    async def request(self, method: str, url: str, **kwargs) -> Any:
        """
        Perform an HTTP request without using async context managers.

        :param method: HTTP method (GET, POST, PUT, DELETE, etc.).
        :param url: The URL for the request. If base_url is set, this can be a relative path.
        :param kwargs: Additional arguments for the request (e.g., params, json, data).
        :return: The parsed JSON response or raw text based on response headers.
        :raises: ClientResponseError, ClientError, Exception
        """
        if self._session is None:
            self.init_session()

        try:
            response = await self._session.request(method, url, **kwargs)
            data = await self._parse_response(response)
            response.raise_for_status()

            self._log.debug(
                f"Request {method} {url} succeeded with status {response.status}, kwargs: {kwargs}"
            )
            return data

        except ClientResponseError as e:
            self._log.error(
                f"ClientResponseError: {str(e)} for URL: {url}, kwargs: {kwargs}"
            )
            raise ExchangeResponseError(e.message, data, method, url) from None
        except ClientError as e:
            self._log.error(f"ClientError: {str(e)} for URL: {url}, kwargs: {kwargs}")
            raise
        except asyncio.TimeoutError:
            self._log.error(f"RequestTimeout for URL: {url}, kwargs: {kwargs}")
            raise
        except Exception as e:
            self._log.error(f"Exception: {str(e)} for URL: {url}, kwargs: {kwargs}")
            raise

    async def get(self, url: str, **kwargs) -> Any:
        """
        Perform an HTTP GET request.

        :param url: The URL for the GET request.
        :param kwargs: Additional arguments for the request.
        :return: The response data.
        """
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Any:
        """
        Perform an HTTP POST request.

        :param url: The URL for the POST request.
        :param kwargs: Additional arguments for the request.
        :return: The response data.
        """
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> Any:
        """
        Perform an HTTP PUT request.

        :param url: The URL for the PUT request.
        :param kwargs: Additional arguments for the request.
        :return: The response data.
        """
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Any:
        """
        Perform an HTTP DELETE request.

        :param url: The URL for the DELETE request.
        :param kwargs: Additional arguments for the request.
        :return: The response data.
        """
        return await self.request("DELETE", url, **kwargs)


class Clock:
    def __init__(self, tick_size: float = 1.0):
        """
        :param tick_size_s: Time interval of each tick in seconds (supports sub-second precision).
        """
        self._tick_size = tick_size  # Tick size in seconds
        self._current_tick = (time.time() // self._tick_size) * self._tick_size
        self._tick_callbacks: List[Callable[[float], None]] = []
        self._started = False
        self._log = SpdLog.get_logger(type(self).__name__, level="INFO", flush=True)

    @property
    def tick_size(self) -> float:
        return self._tick_size

    @property
    def current_timestamp(self) -> float:
        return int(self._current_tick)  # Timestamp in seconds

    def add_tick_callback(self, callback: Callable[[float], None]):
        """
        Register a callback to be called on each tick.
        :param callback: Function to be called with current_tick as argument.
        """
        self._tick_callbacks.append(callback)

    async def run(self):
        if self._started:
            raise RuntimeError("Clock is already running.")
        self._started = True
        while True:
            now = time.time()
            next_tick_time = self._current_tick + self._tick_size
            sleep_duration = next_tick_time - now
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)
            else:
                # If we're behind schedule, skip to the next tick to prevent drift
                next_tick_time = now
            self._current_tick = next_tick_time
            for callback in self._tick_callbacks:
                try:
                    callback(self.current_timestamp)
                except Exception:
                    self._log.error("Error in tick callback.")


class PublicConnector(ABC):
    def __init__(
        self,
        account_type,
        market: Dict[str, Any],
        market_id: Dict[str, Any],
        exchange_id: str,
    ):
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )
        self._account_type = account_type
        self._market = market
        self._market_id = market_id
        self._exchange_id = exchange_id
    
    @property
    def account_type(self):
        return self._account_type
    
    @abstractmethod
    async def subscribe_trade(self, symbol: str):
        pass
    
    @abstractmethod
    async def subscribe_bookl1(self, symbol: str):
        pass
    
    @abstractmethod
    async def subscribe_kline(self, symbol: str, interval: str):
        pass

class PrivateConnector(ABC):
    def __init__(
        self,
        account_type,
        market: Dict[str, Any],
        market_id: Dict[str, Any],
        exchange_id: str,
    ):
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="INFO", flush=True
        )
        self._account_type = account_type
        self._market = market
        self._market_id = market_id
        self._exchange_id = exchange_id
        
    
    @abstractmethod
    async def connect(self):
        pass
    
    @abstractmethod
    async def disconnect(self):
        pass

import base64
from decimal import Decimal
import hmac
import hashlib
import json
import time


import requests
import asyncio
import aiohttp


from collections import defaultdict
from typing import Any, Dict, List
from typing import Literal, Callable, Optional
from urllib.parse import urljoin

import orjson
import aiohttp
import websockets
import ccxt.pro as ccxtpro


from asynciolimiter import Limiter
from websockets.asyncio import client


from tradebot.types import BookL1, Trade, Kline, MarkPrice, FundingRate, IndexPrice
from tradebot.constants import IntervalType, UrlType
from tradebot.constants import Url, EventType, BinanceAccountType, BinanceEndpointsType
from tradebot.constants import STREAM_URLS, BASE_URLS, BINANCE_ENDPOINTS
from tradebot.exceptions import OrderError
from tradebot.entity import EventSystem, Order
from tradebot.base import (
    ExchangeManager,
    OrderManager,
    AccountManager,
    WebsocketManager,
    WSManager,
    RestApi,
)


class BinanceRestApi(RestApi):
    def __init__(self, api_key: str, secret: str, account_type: BinanceAccountType, **kwargs):
        self._api_key = api_key
        self._secret = secret
        self._account_type = account_type
        self._base_url = BASE_URLS[account_type]
        super().__init__(headers=self._get_headers(), **kwargs)
        
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
        }
        if self._api_key:
            headers["X-MBX-APIKEY"] = self._api_key
        return headers
    
    def _generate_signature(self, query: str) -> str:
        signature = hmac.new(self._secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature

    async def _fetch(self, method: str, endpoint: str, params: Dict[str, Any] = {}, data: Dict[str, Any] = {}) -> Any:
        url = urljoin(self._base_url, endpoint)
        
        data["timestamp"] = time.time_ns() // 1_000_000
        query = "&".join([f"{k}={v}" for k, v in data.items()])
        
        signature = self._generate_signature(query)
        params["signature"] = signature
        
        return await self._request(method, url, params=params, data=data)
    
    async def start_user_data_stream(self) -> Dict[str, Any]:
        endpoint = self._generate_endpoint(BinanceEndpointsType.USER_DATA_STREAM)
        return await self._fetch("POST", endpoint)

    async def keep_alive_user_data_stream(self, listen_key: str) -> Dict[str, Any]:
        endpoint = self._generate_endpoint(BinanceEndpointsType.USER_DATA_STREAM)
        return await self._fetch("PUT", endpoint, params={"listenKey": listen_key})
    
    async def new_order(self, symbol: str, side: str, type: str, **kwargs):
        endpoint = self._generate_endpoint(BinanceEndpointsType.TRADING)
        
        endpoint = f"{endpoint}/order"
        
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs
        }
        
        return await self._fetch("POST", endpoint, data=params)
    
    def test3(self):
        print("test")
    
    def _generate_endpoint(self, endpoint_type: BinanceEndpointsType) -> str:
        return BINANCE_ENDPOINTS[endpoint_type][self._account_type]
    
    


        


class BinanceExchangeManager(ExchangeManager):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.market_id = None

    async def load_markets(self):
        await super().load_markets()
        self._get_market_id()

    def _get_market_id(self):
        self.market_id = {}
        if not self.market:
            raise ValueError(
                "Market data not loaded, please call `load_markets()` first"
            )
        for _, v in self.market.items():
            if v["subType"] == "linear":
                self.market_id[f"{v['id']}_swap"] = v
            elif v["type"] == "spot":
                self.market_id[f"{v['id']}_spot"] = v
            else:
                self.market_id[v["id"]] = v


class BinanceOrderManager(OrderManager):
    def __init__(self, exchange: BinanceExchangeManager):
        super().__init__(exchange)
        self.exchange_id = exchange.config["exchange_id"]

    async def handle_request_timeout(self, method: str, params: Dict[str, Any]):
        symbol = params["symbol"]
        current_time = time.time_ns() // 1_000_000
        orders = await self.fetch_orders(symbol, since=current_time - 1000 * 5)

        if not in_orders(orders, method, params):
            match method:
                case "place_limit_order":
                    return await self.retry_place_limit_order(params)
                case "place_market_order":
                    return await self.retry_place_market_order(params)
                case "cancel_order":
                    return await self.retry_cancel_order(params)

    async def place_limit_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: Decimal,
        price: float,
        **params,
    ) -> Order:
        res = await super().place_limit_order(symbol, side, amount, price, **params)
        if isinstance(res, OrderError):
            self._log.error(str(res))
            return Order(
                raw={},
                success=False,
                exchange=self.exchange_id,
                id=None,
                client_order_id=None,
                timestamp=time.time_ns() // 1_000_000,
                symbol=symbol,
                type="limit",
                side=side,
                status="failed",
                price=price,
                amount=amount,
            )
        return parse_ccxt_order(res, self.exchange_id)

    async def place_market_order(
        self, symbol: str, side: Literal["buy", "sell"], amount: Decimal, **params
    ) -> Order:
        res = await super().place_market_order(symbol, side, amount, **params)
        if isinstance(res, OrderError):
            self._log.error(str(res))
            return Order(
                raw={},
                success=False,
                exchange=self.exchange_id,
                id=None,
                client_order_id=None,
                timestamp=time.time_ns() // 1_000_000,
                symbol=symbol,
                type="market",
                side=side,
                status="failed",
                amount=amount,
            )
        return parse_ccxt_order(res, self.exchange_id)

    async def cancel_order(self, id: str, symbol: str, **params) -> Order:
        res = await super().cancel_order(id, symbol, **params)
        if isinstance(res, OrderError):
            self._log.error(str(res))
            return Order(
                raw={},
                success=False,
                exchange=self.exchange_id,
                id=id,
                client_order_id=None,
                timestamp=time.time_ns() // 1_000_000,
                symbol=symbol,
                type=None,
                side=None,
                status="failed",
                amount=None,
            )
        return parse_ccxt_order(res, self.exchange_id)

    async def fetch_orders(
        self, symbol: str, since: int = None, limit: int = None
    ) -> List[Order]:
        res = await self._exchange.api.fetch_orders(
            symbol=symbol, since=since, limit=limit
        )
        return [parse_ccxt_order(order, self.exchange_id) for order in res]

    async def _create_order(self, symbol, type, side, amount, price, **params):
        res = await self._exchange.api.create_order(
            symbol=symbol,
            type=type,
            side=side,
            amount=amount,
            price=price,
            params=params,
        )
        return parse_ccxt_order(res, self._exchange.config["exchange_id"])

    async def retry_place_limit_order(
        self, params: Dict[str, Any], max_retry: int = 3, interval: int = 3
    ):
        params["handle_timeout"] = False
        for i in range(max_retry):
            res = await super().place_limit_order(**params)

            if not isinstance(res, OrderError):
                return res

            if i == max_retry - 1:
                return Order(
                    raw={},
                    success=False,
                    exchange=self.exchange_id,
                    id=params.get("id", None),
                    client_order_id="",
                    timestamp=time.time_ns() // 1_000_000,
                    symbol=params.get("symbol", None),
                    type="limit",
                    side=params["side"],
                    price=params.get("price", None),
                    amount=params.get("amount", None),
                    status="failed",
                )

            self._log.warn(
                f"Order placement failed, attempting retry {i+1} of {max_retry}: {str(res)}"
            )
            await asyncio.sleep(interval)

    async def retry_place_market_order(
        self, params: Dict[str, Any], max_retry: int = 3, interval: int = 3
    ):
        params["handle_timeout"] = False
        for i in range(max_retry):
            res = await super().place_market_order(**params)

            if not isinstance(res, OrderError):
                return res

            if i == max_retry - 1:
                return Order(
                    raw={},
                    success=False,
                    exchange=self.exchange_id,
                    id=params.get("id", None),
                    client_order_id="",
                    timestamp=time.time_ns() // 1_000_000,
                    symbol=params.get("symbol", None),
                    type="market",
                    side=params.get("side", None),
                    amount=params.get("amount", None),
                    status="failed",
                )

            self._log.warn(
                f"Order placement failed, attempting retry {i+1} of {max_retry}: {str(res)}"
            )
            await asyncio.sleep(interval)

    async def retry_cancel_order(
        self, params: Dict[str, Any], max_retry: int = 3, interval: int = 3
    ):
        params["handle_timeout"] = False
        for i in range(max_retry):
            res = await super().cancel_order(**params)

            if not isinstance(res, OrderError):
                return res

            if i == max_retry - 1:
                return Order(
                    raw={},
                    success=False,
                    exchange=self._exchange.config["exchange_id"],
                    id=params.get("id", None),
                    client_order_id="",
                    timestamp=time.time_ns() // 1_000_000,
                    symbol=params.get("symbol", None),
                    type=params.get("type", None),
                    side=params.get("side", None),
                    status="failed",
                    amount=params.get("amount", None),
                )

            self._log.warn(
                f"Order cancellation failed, attempting retry {i+1} of {max_retry}: {str(res)}"
            )
            await asyncio.sleep(interval)


class BinanceAccountManager(AccountManager):
    pass


class BinanceWSManager(WSManager):
    def __init__(
        self,
        account_type: BinanceAccountType,
        exchange: BinanceExchangeManager,
    ):
        url = STREAM_URLS[account_type]
        super().__init__(url, limiter=Limiter(3 / 1))
        self._get_market_type(account_type)
        self._api_key = exchange.api_key
        self._secret = exchange.secret
        self._market_id = exchange.market_id
        self._exchange_id = exchange.exchange_id
        self._account_type = account_type
        self._rest_api = BinanceRestApi(self._api_key, self._secret, account_type)

    def _get_market_type(self, account_type: BinanceAccountType):
        if (
            account_type == BinanceAccountType.SPOT
            or account_type == BinanceAccountType.SPOT_TESTNET
        ):
            self._market_type = "_spot"
        elif (
            account_type == BinanceAccountType.USD_M_FUTURE
            or account_type == BinanceAccountType.USD_M_FUTURE_TESTNET
        ):
            self._market_type = "_swap"
        else:
            self._market_type = ""

    async def subscribe_kline(self, symbol: str, interval: IntervalType):
        subscription_id = f"kline.{symbol}.{interval}"
        if subscription_id not in self._subscriptions:
            await self._limiter.wait()
            id = time.time_ns() // 1_000_000
            payload = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@kline_{interval}"],
                "id": id,
            }
            self._subscriptions[subscription_id] = payload
            self._send(payload)
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_book_ticker(self, symbol):
        subscription_id = f"book_ticker.{symbol}"
        if subscription_id not in self._subscriptions:
            await self._limiter.wait()
            id = time.time_ns() // 1_000_000
            payload = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@bookTicker"],
                "id": id,
            }
            self._subscriptions[subscription_id] = payload
            self._send(payload)
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_trade(self, symbol):
        subscription_id = f"trade.{symbol}"
        if subscription_id not in self._subscriptions:
            await self._limiter.wait()
            id = time.time_ns() // 1_000_000
            payload = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@trade"],
                "id": id,
            }
            self._subscriptions[subscription_id] = payload
            self._send(payload)
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_mark_price(self, symbol, interval: Literal["1s", "3s"] = "1s"):
        if self._market_type == "_spot":
            raise ValueError("Spot market doesn't have mark price")
        subscription_id = f"mark_price.{symbol}"
        if subscription_id not in self._subscriptions:
            await self._limiter.wait()
            id = time.time_ns() // 1_000_000
            payload = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@markPrice@{interval}"],
                "id": id,
            }
            self._subscriptions[subscription_id] = payload
            self._send(payload)
        else:
            self._log.info(f"Already subscribed to {subscription_id}")
    
    async def subscribe_user_data_stream(self):
        subscription_id = f"user_data_stream.{self._account_type}"
        if subscription_id not in self._subscriptions:
            await self._limiter.wait()
            listen_key = await self._get_listen_key()
            id = time.time_ns() // 1_000_000
            payload = {
                "method": "SUBSCRIBE",
                "params": [listen_key],
                "id": id,
            }
            self._subscriptions[subscription_id] = payload
            self._send(payload)
        else:
            self._log.info(f"Already subscribed to {subscription_id}")
    
    
    async def _get_listen_key(self):
        try:
            res = await self._rest_api.start_user_data_stream()
            return res["listenKey"]
        except Exception as e:
            self._log.error(f"Failed to get listen key: {str(e)}")
            return None
        
        

    def _callback(self, msg):
        # self._log.info(str(msg))
        if "e" in msg:
            match msg["e"]:
                case "trade":
                    self._parse_trade(msg)
                case "bookTicker":
                    self._parse_book_ticker(msg)
                case "kline":
                    self._parse_kline(msg)
                case "markPriceUpdate":
                    self._parse_mark_price(msg)

        elif "u" in msg:
            self._parse_book_ticker(
                msg
            )  # spot book ticker doesn't have "e" key. FUCK BINANCE

    def _parse_kline(self, res: Dict[str, Any]) -> Kline:
        """
        {
            "e": "kline",     // Event type
            "E": 1672515782136,   // Event time
            "s": "BNBBTC",    // Symbol
            "k": {
                "t": 123400000, // Kline start time
                "T": 123460000, // Kline close time
                "s": "BNBBTC",  // Symbol
                "i": "1m",      // Interval
                "f": 100,       // First trade ID
                "L": 200,       // Last trade ID
                "o": "0.0010",  // Open price
                "c": "0.0020",  // Close price
                "h": "0.0025",  // High price
                "l": "0.0015",  // Low price
                "v": "1000",    // Base asset volume
                "n": 100,       // Number of trades
                "x": false,     // Is this kline closed?
                "q": "1.0000",  // Quote asset volume
                "V": "500",     // Taker buy base asset volume
                "Q": "0.500",   // Taker buy quote asset volume
                "B": "123456"   // Ignore
            }
        }
        """
        id = res["s"] + self._market_type
        market = self._market_id[id]

        ticker = Kline(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            interval=res["k"]["i"],
            open=float(res["k"]["o"]),
            high=float(res["k"]["h"]),
            low=float(res["k"]["l"]),
            close=float(res["k"]["c"]),
            volume=float(res["k"]["v"]),
            timestamp=res.get("E", time.time_ns() // 1_000_000),
        )
        EventSystem.emit(EventType.KLINE, ticker)

    def _parse_trade(self, res: Dict[str, Any]) -> Trade:
        """
        {
            "e": "trade",       // Event type
            "E": 1672515782136, // Event time
            "s": "BNBBTC",      // Symbol
            "t": 12345,         // Trade ID
            "p": "0.001",       // Price
            "q": "100",         // Quantity
            "T": 1672515782136, // Trade time
            "m": true,          // Is the buyer the market maker?
            "M": true           // Ignore
        }

        {
            "u":400900217,     // order book updateId
            "s":"BNBUSDT",     // symbol
            "b":"25.35190000", // best bid price
            "B":"31.21000000", // best bid qty
            "a":"25.36520000", // best ask price
            "A":"40.66000000"  // best ask qty
        }
        """
        id = res["s"] + self._market_type
        market = self._market_id[id]

        trade = Trade(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            price=float(res["p"]),
            size=float(res["q"]),
            timestamp=res.get("T", time.time_ns() // 1_000_000),
        )
        EventSystem.emit(EventType.TRADE, trade)

    def _parse_book_ticker(self, res: Dict[str, Any]) -> BookL1:
        """
        {
            "u":400900217,     // order book updateId
            "s":"BNBUSDT",     // symbol
            "b":"25.35190000", // best bid price
            "B":"31.21000000", // best bid qty
            "a":"25.36520000", // best ask price
            "A":"40.66000000"  // best ask qty
        }
        """
        id = res["s"] + self._market_type
        market = self._market_id[id]

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            bid=float(res["b"]),
            ask=float(res["a"]),
            bid_size=float(res["B"]),
            ask_size=float(res["A"]),
            timestamp=res.get("T", time.time_ns() // 1_000_000),
        )
        EventSystem.emit(EventType.BOOKL1, bookl1)

    def _parse_mark_price(self, res: Dict[str, Any]):
        """
         {
            "e": "markPriceUpdate",     // Event type
            "E": 1562305380000,         // Event time
            "s": "BTCUSDT",             // Symbol
            "p": "11794.15000000",      // Mark price
            "i": "11784.62659091",      // Index price
            "P": "11784.25641265",      // Estimated Settle Price, only useful in the last hour before the settlement starts
            "r": "0.00038167",          // Funding rate
            "T": 1562306400000          // Next funding time
        }
        """
        id = res["s"] + self._market_type
        market = self._market_id[id]

        mark_price = MarkPrice(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            price=float(res["p"]),
            timestamp=res.get("E", time.time_ns() // 1_000_000),
        )

        funding_rate = FundingRate(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            rate=float(res["r"]),
            timestamp=res.get("E", time.time_ns() // 1_000_000),
            next_funding_time=res.get("T", time.time_ns() // 1_000_000),
        )

        index_price = IndexPrice(
            exchange=self._exchange_id,
            symbol=market["symbol"],
            price=float(res["i"]),
            timestamp=res.get("E", time.time_ns() // 1_000_000),
        )

        EventSystem.emit(EventType.MARK_PRICE, mark_price)
        EventSystem.emit(EventType.FUNDING_RATE, funding_rate)
        EventSystem.emit(EventType.INDEX_PRICE, index_price)


class BinanceWebsocketManager(WebsocketManager):
    def __init__(self, url: UrlType, api_key: str = None, secret: str = None):
        super().__init__(
            base_url=url.STREAM_URL,
            ping_interval=5,
            ping_timeout=5,
            close_timeout=1,
            max_queue=12,
        )
        self._url = url
        self._api_key = api_key
        self._secret = secret
        self._session: aiohttp.ClientSession = None

    async def _subscribe(self, payload: Dict[str, Any], subscription_id: str):
        async for websocket in websockets.connect(
            uri=self._base_url,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
            close_timeout=self._close_timeout,
            max_queue=self._max_queue,
        ):
            try:
                payload = json.dumps(payload)
                await websocket.send(payload)
                async for msg in websocket:
                    msg = orjson.loads(msg)
                    await self._subscripions[subscription_id].put(msg)
            except websockets.ConnectionClosed:
                self._log.error("Connection closed, reconnecting...")

    async def subscribe_book_ticker(
        self, symbol: str, callback: Callable[..., Any] = None, *args, **kwargs
    ):
        subscription_id = f"book_ticker.{symbol}"
        id = int(time.time() * 1000)
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@bookTicker"],
            "id": id,
        }
        if subscription_id not in self._subscripions:
            self._tasks.append(
                asyncio.create_task(
                    self._consume(subscription_id, callback=callback, *args, **kwargs)
                )
            )
            self._tasks.append(
                asyncio.create_task(self._subscribe(payload, subscription_id))
            )
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_book_tickers(
        self, symbols: List[str], callback: Callable[..., Any] = None, *args, **kwargs
    ):
        for symbol in symbols:
            await self.subscribe_book_ticker(symbol, callback=callback, *args, **kwargs)

    async def subscribe_trade(
        self, symbol: str, callback: Callable[..., Any] = None, *args, **kwargs
    ):
        subscription_id = f"trade.{symbol}"
        id = int(time.time() * 1000)
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@trade"],
            "id": id,
        }
        if subscription_id not in self._subscripions:
            self._tasks.append(
                asyncio.create_task(
                    self._consume(subscription_id, callback=callback, *args, **kwargs)
                )
            )
            self._tasks.append(
                asyncio.create_task(self._subscribe(payload, subscription_id))
            )
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_trades(
        self, symbols: List[str], callback: Callable[..., Any] = None, *args, **kwargs
    ):
        for symbol in symbols:
            await self.subscribe_trade(symbol, callback=callback, *args, **kwargs)

    async def subscribe_agg_trade(
        self, symbol: str, callback: Callable[..., Any] = None, *args, **kwargs
    ):
        subscription_id = f"agg_trade.{symbol}"
        id = int(time.time() * 1000)
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@aggTrade"],
            "id": id,
        }
        if subscription_id not in self._subscripions:
            self._tasks.append(
                asyncio.create_task(
                    self._consume(subscription_id, callback=callback, *args, **kwargs)
                )
            )
            self._tasks.append(
                asyncio.create_task(self._subscribe(payload, subscription_id))
            )
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_agg_trades(
        self, symbols: List[str], callback: Callable[..., Any] = None, *args, **kwargs
    ):
        for symbol in symbols:
            await self.subscribe_agg_trade(symbol, callback=callback, *args, **kwargs)

    async def subscribe_kline(
        self,
        symbol: str,
        interval: IntervalType,
        callback: Callable[..., Any] = None,
        *args,
        **kwargs,
    ):
        subscription_id = f"kline.{symbol}.{interval}"
        id = int(time.time() * 1000)
        payload = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@kline_{interval}"],
            "id": id,
        }
        if subscription_id not in self._subscripions:
            self._tasks.append(
                asyncio.create_task(
                    self._consume(subscription_id, callback=callback, *args, **kwargs)
                )
            )
            self._tasks.append(
                asyncio.create_task(self._picows_subscribe(payload, subscription_id))
            )
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def subscribe_klines(
        self,
        symbols: List[str],
        interval: IntervalType,
        callback: Callable[..., Any] = None,
        *args,
        **kwargs,
    ):
        for symbol in symbols:
            await self.subscribe_kline(
                symbol, interval, callback=callback, *args, **kwargs
            )

    async def subscribe_user_data(
        self, callback: Callable[..., Any] = None, *args, **kwargs
    ):
        type = self._url.__name__.lower()
        subscription_id = f"user_data.{type}"

        listen_key = await self._get_listen_key()
        payload = {
            "method": "SUBSCRIBE",
            "params": [listen_key],
            "id": int(time.time() * 1000),
        }
        if subscription_id not in self._subscripions:
            self._tasks.append(
                asyncio.create_task(self._keep_alive_listen_key(listen_key))
            )
            self._tasks.append(
                asyncio.create_task(
                    self._consume(subscription_id, callback=callback, *args, **kwargs)
                )
            )
            self._tasks.append(
                asyncio.create_task(self._subscribe(payload, subscription_id))
            )
        else:
            self._log.info(f"Already subscribed to {subscription_id}")

    async def _get_listen_key(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"X-MBX-APIKEY": self._api_key}
            )
        try:
            async with self._session.post(self._url.BASE_URL) as response:
                data = await response.json()
                return data["listenKey"]
        except Exception as e:
            self._log.error(f"Failed to get listen key: {e}")
            return None

    async def _keep_alive_listen_key(self, listen_key: str):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"X-MBX-APIKEY": self._api_key}
            )
        base_url = self._url.BASE_URL
        type = self._url.__name__.lower()
        while True:
            try:
                self._log.info(f"Keep alive {type} listen key...")
                async with self._session.put(
                    f"{base_url}?listenKey={listen_key}"
                ) as response:
                    self._log.info(f"Keep alive listen key status: {response.status}")
                    if response.status != 200:
                        listen_key = await self._get_listen_key()
                    else:
                        data = await response.json()
                        self._log.info(
                            f"Keep alive {type} listen key: {data.get('listenKey', listen_key)}"
                        )
                    await asyncio.sleep(60 * 20)
            except asyncio.CancelledError:
                self._log.info(f"Cancelling keep alive task for {type} listen key")
                break
            except Exception as e:
                self._log.error(f"Error keeping alive {type} listen key: {e}")

    async def close(self):
        if self._session is not None:
            await self._session.close()
        await super().close()


def in_orders(orders: List[Order], method: str, params: Dict[str, Any]) -> bool:
    for order in orders:
        match method:
            case "place_limit_order":
                if (
                    order.symbol == params["symbol"]
                    and order.side == params["side"]
                    and order.amount == params["amount"]
                    and order.price == params["price"]
                    and order.type == "limit"
                ):
                    return True
            case "place_market_order":
                if (
                    order.symbol == params["symbol"]
                    and order.side == params["side"]
                    and order.amount == params["amount"]
                    and order.type == "market"
                ):
                    return True
            case "cancel_order":
                if (
                    order.symbol == params["symbol"]
                    and order.id == params["id"]
                    and order.status == "canceled"
                ):
                    return True


def parse_ccxt_order(res: Dict[str, Any], exchange: str) -> Order:
    raw = res.get("info", {})
    id = res.get("id", None)
    client_order_id = res.get("clientOrderId", None)
    timestamp = res.get("timestamp", None)
    symbol = res.get("symbol", None)
    type = res.get("type", None)  # market or limit
    side = res.get("side", None)  # buy or sell
    price = res.get("price", None)  # maybe empty for market order
    average = res.get("average", None)  # float everage filling price
    amount = res.get("amount", None)
    filled = res.get("filled", None)
    remaining = res.get("remaining", None)
    status = raw.get("status", None).lower()
    cost = res.get("cost", None)
    reduce_only = raw.get("reduceOnly", None)
    position_side = raw.get("positionSide", "").lower() or None  # long or short
    time_in_force = res.get("timeInForce", None)

    return Order(
        raw=raw,
        success=True,
        exchange=exchange,
        id=id,
        client_order_id=client_order_id,
        timestamp=timestamp,
        symbol=symbol,
        type=type,
        side=side,
        price=price,
        average=average,
        amount=amount,
        filled=filled,
        remaining=remaining,
        status=status,
        cost=cost,
        reduce_only=reduce_only,
        position_side=position_side,
        time_in_force=time_in_force,
    )


def parse_websocket_stream(
    event_data: Dict[str, Any],
    market_id: Dict[str, Any],
    market_type: Optional[Literal["spot", "swap"]] = None,
):
    event = event_data.get("e", None)
    match event:
        case "kline":
            """
            {
                'e': 'kline', 
                'E': 1727525244267, 
                's': 'BTCUSDT', 
                'k': {
                    't': 1727525220000, 
                    'T': 1727525279999, 
                    's': 'BTCUSDT', 
                    'i': '1m', 
                    'f': 5422081499, 
                    'L': 5422081624, 
                    'o': '65689.80', 
                    'c': '65689.70', 
                    'h': '65689.80', 
                    'l': '65689.70', 
                    'v': '9.027', 
                    'n': 126, 
                    'x': False, 
                    'q': '592981.58290', 
                    'V': '6.610', 
                    'Q': '434209.57800', 
                    'B': '0'
                }
            }
            """
            id = f"{event_data['s']}_{market_type}" if market_type else event_data["s"]
            market = market_id[id]
            event_data["s"] = market["symbol"]
            return event_data


def parse_user_data_stream(event_data: Dict[str, Any], market_id: Dict[str, Any]):
    event = event_data.get("e", None)
    match event:
        case "ORDER_TRADE_UPDATE":
            """
            {
                "e": "ORDER_TRADE_UPDATE", // Event type
                "T": 1727352962757,  // Transaction time
                "E": 1727352962762, // Event time
                "fs": "UM", // Event business unit. 'UM' for USDS-M futures and 'CM' for COIN-M futures
                "o": {
                    "s": "NOTUSDT", // Symbol
                    "c": "c-11WLU7VP1727352880uzcu2rj4ss0i", // Client order ID
                    "S": "SELL", // Side
                    "o": "LIMIT", // Order type
                    "f": "GTC", // Time in force
                    "q": "5488", // Original quantity
                    "p": "0.0084830", // Original price
                    "ap": "0", // Average price
                    "sp": "0", // Ignore
                    "x": "NEW", // Execution type
                    "X": "NEW", // Order status
                    "i": 4968510801, // Order ID
                    "l": "0", // Order last filled quantity
                    "z": "0", // Order filled accumulated quantity
                    "L": "0", // Last filled price
                    "n": "0", // Commission, will not be returned if no commission
                    "N": "USDT", // Commission asset, will not be returned if no commission
                    "T": 1727352962757, // Order trade time
                    "t": 0, // Trade ID
                    "b": "0", // Bids Notional
                    "a": "46.6067521", // Ask Notional
                    "m": false, // Is this trade the maker side?
                    "R": false, // Is this reduce only
                    "ps": "BOTH", // Position side
                    "rp": "0", // Realized profit of the trade
                    "V": "EXPIRE_NONE", // STP mode
                    "pm": "PM_NONE", 
                    "gtd": 0
                }
            }
            """
            if event_data := event_data.get("o", None):
                if (market := market_id.get(event_data["s"], None)) is None:
                    id = f"{event_data['s']}_swap"
                    market = market_id[id]

                if (type := event_data["o"].lower()) == "market":
                    cost = float(event_data.get("l", "0")) * float(
                        event_data.get("ap", "0")
                    )
                elif type == "limit":
                    price = float(event_data.get("ap", "0")) or float(
                        event_data.get("p", "0")
                    )  # if average price is 0 or empty, use price
                    cost = float(event_data.get("l", "0")) * price

                return Order(
                    raw=event_data,
                    success=True,
                    exchange="binance",
                    id=event_data.get("i", None),
                    client_order_id=event_data.get("c", None),
                    timestamp=event_data.get("T", None),
                    symbol=market["symbol"],
                    type=type,
                    side=event_data.get("S", "").lower(),
                    status=event_data.get("X", "").lower(),
                    price=event_data.get("p", None),
                    average=event_data.get("ap", None),
                    last_filled_price=event_data.get("L", None),
                    amount=event_data.get("q", None),
                    filled=event_data.get("z", None),
                    last_filled=event_data.get("l", None),
                    remaining=Decimal(event_data["q"]) - Decimal(event_data["z"]),
                    fee=event_data.get("n", None),
                    fee_currency=event_data.get("N", None),
                    cost=cost,
                    last_trade_timestamp=event_data.get("T", None),
                    reduce_only=event_data.get("R", None),
                    position_side=event_data.get("ps", "").lower(),
                    time_in_force=event_data.get("f", None),
                )

        case "ACCOUNT_UPDATE":
            """
            {
                "e": "ACCOUNT_UPDATE", 
                "T": 1727352914268, 
                "E": 1727352914274, 
                "fs": "UM", 
                "a": {
                    "B": [
                        {"a": "USDT", "wb": "0.07147421", "cw": "0.07147421", "bc": "0"}, 
                        {"a": "BNB", "wb": "0.01993701", "cw": "0.01993701", "bc": "0"}
                    ], 
                    "P": [
                        {
                            "s": "BOMEUSDT", 
                            "pa": "-2760", 
                            "ep": "0.00724500", 
                            "cr": "0", 
                            "up": "-0.00077280", 
                            "ps": "BOTH", 
                            "bep": 0.0072436959
                        }
                    ], 
                "m": "ORDER"
                }
            }
            """
            positions = []
            for position in event_data["a"]["P"]:
                if (market := market_id.get(position["s"], None)) is None:
                    id = f"{position['s']}_swap"
                    market = market_id[id]
                position["s"] = market["symbol"]
                positions.append(position)
            event_data["a"]["P"] = positions
            return event_data

        case "balanceUpdate":
            """
            {
                "e": "balanceUpdate", 
                "E": 1727320813969, 
                "a": "BNB", 
                "d": "-0.01000000", 
                "U": 1495297874797, 
                "T": 1727320813969
            }
            """
            return event_data

        case "executionReport":
            """
            {
                "e": "executionReport", // Event type
                "E": 1727353057267, // Event time
                "s": "ORDIUSDT", // Symbol
                "c": "c-11WLU7VP2rj4ss0i", // Client order ID 
                "S": "BUY", // Side
                "o": "MARKET", // Order type
                "f": "GTC", // Time in force
                "q": "0.50000000", // Order quantity
                "p": "0.00000000", // Order price
                "P": "0.00000000", // Stop price
                "g": -1, // Order list id
                "x": "TRADE", // Execution type
                "X": "PARTIALLY_FILLED", // Order status
                "i": 2233880350, // Order ID
                "l": "0.17000000", // last executed quantity
                "z": "0.17000000", // Cumulative filled quantity
                "L": "36.88000000", // Last executed price
                "n": "0.00000216", // Commission amount
                "N": "BNB", // Commission asset
                "T": 1727353057266, // Transaction time
                "t": 105069149, // Trade ID
                "w": false, // Is the order on the book?
                "m": false, // Is this trade the maker side?
                "O": 1727353057266, // Order creation time
                "Z": "6.26960000", // Cumulative quote asset transacted quantity
                "Y": "6.26960000", // Last quote asset transacted quantity (i.e. lastPrice * lastQty)
                "V": "EXPIRE_MAKER", // Self trade prevention Mode
                "I": 1495839281094 // Ignore
            }
            
            # Example of an execution report event for a partially filled market buy order
            {
                "e": "executionReport", // Event type
                "E": 1727353057267, // Event time
                "s": "ORDIUSDT", // Symbol
                "c": "c-11WLU7VP2rj4ss0i", // Client order ID 
                "S": "BUY", // Side
                "o": "MARKET", // Order type
                "f": "GTC", // Time in force
                "q": "0.50000000", // Order quantity
                "p": "0.00000000", // Order price
                "P": "0.00000000", // Stop price
                "g": -1, // Order list id
                "x": "TRADE", // Execution type
                "X": "PARTIALLY_FILLED", // Order status
                "i": 2233880350, // Order ID
                "l": "0.17000000", // last executed quantity
                "z": "0.34000000", // Cumulative filled quantity
                "L": "36.88000000", // Last executed price
                "n": "0.00000216", // Commission amount
                "N": "BNB", // Commission asset
                "T": 1727353057266, // Transaction time
                "t": 105069150, // Trade ID
                "w": false, // Is the order on the book?
                "m": false, // Is this trade the maker side?
                "O": 1727353057266, // Order creation time
                "Z": "12.53920000", // Cumulative quote asset transacted quantity
                "Y": "6.26960000", // Last quote asset transacted quantity (i.e. lastPrice * lastQty)
                "V": "EXPIRE_MAKER", // Self trade prevention Mode
                "I": 1495839281094 // Ignore
            }
            
            """
            id = f"{event_data['s']}_spot"
            market = market_id[id]

            return Order(
                raw=event_data,
                success=True,
                exchange="binance",
                id=event_data.get("i", None),
                client_order_id=event_data.get("c", None),
                timestamp=event_data.get("T", None),
                symbol=market["symbol"],
                type=event_data.get("o", "").lower(),
                side=event_data.get("S", "").lower(),
                status=event_data.get("X", "").lower(),
                price=event_data.get("p", None),
                average=event_data.get("ap", None),
                last_filled_price=event_data.get("L", None),
                amount=event_data.get("q", None),
                filled=event_data.get("z", None),
                last_filled=event_data.get("l", None),
                remaining=Decimal(event_data.get("q", "0"))
                - Decimal(event_data.get("z", "0")),
                fee=event_data.get("n", None),
                fee_currency=event_data.get("N", None),
                cost=event_data.get("Y", None),
                last_trade_timestamp=event_data.get("T", None),
                time_in_force=event_data.get("f", None),
            )

        case "outboundAccountPosition":
            """
            {
                "e": "outboundAccountPosition", 
                "E": 1727353873873, 
                "u": 1727353873873, 
                "U": 1495859325408, 
                "B": [
                    {
                        "a": "BNB", 
                        "f": 
                        "0.09971173", 
                        "l": 
                        "0.00000000"
                    }, 
                    {
                        "a": "USDT", 
                        "f": "6426.31521496", 
                        "l": "0.00000000"
                    }, 
                    {"a": 
                    "AVAX", 
                    "f": "3.00000000", 
                    "l": "0.00000000"
                    }
                ]
            }
            """
            return event_data

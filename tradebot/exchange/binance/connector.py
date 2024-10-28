import time
import asyncio
from typing import Dict, Any
from typing import Literal
from decimal import Decimal
from tradebot.base import PublicConnector, PrivateConnector
from tradebot.entity import EventSystem
from tradebot.constants import EventType, OrderStatus
from tradebot.types import Order
from tradebot.types import BookL1, Trade, Kline, MarkPrice, FundingRate, IndexPrice
from tradebot.exchange.binance.rest_api import BinanceRestApi, BinanceApiClient
from tradebot.exchange.binance.constants import BinanceAccountType
from tradebot.exchange.binance.websockets import BinanceWSClient


class BinancePublicConnector(PublicConnector):
    def __init__(
        self,
        account_type: BinanceAccountType,
        market: Dict[str, Any],
        market_id: Dict[str, Any],
    ):
        if not (account_type.is_spot or account_type.is_future):
            raise ValueError(
                f"BinanceAccountType.{account_type.value} is not supported for Binance Public Connector"
            )

        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            exchange_id="binance",
        )

        self._ws_client = BinanceWSClient(
            account_type=account_type, handler=self._ws_msg_handler
        )

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"

    async def subscribe_trade(self, symbol: str):
        market = self._market.get(symbol, None)
        symbol = market["id"] if market else symbol
        await self._ws_client.subscribe_trade(symbol)

    async def subscribe_bookl1(self, symbol: str):
        market = self._market.get(symbol, None)
        symbol = market["id"] if market else symbol
        await self._ws_client.subscribe_book_ticker(symbol)

    async def subscribe_kline(self, symbol: str, interval: str):
        market = self._market.get(symbol, None)
        symbol = market["id"] if market else symbol
        await self._ws_client.subscribe_kline(symbol, interval)

    def _ws_msg_handler(self, msg):
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
            # spot book ticker doesn't have "e" key. FUCK BINANCE
            self._parse_book_ticker(msg)

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
        id = res["s"] + self.market_type
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
        id = res["s"] + self.market_type
        market = self._market_id[id]  # map exchange id to ccxt symbol

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
        id = res["s"] + self.market_type
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
        id = res["s"] + self.market_type
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

    def disconnect(self):
        self._ws_client.disconnect()


class BinancePrivateConnector(PrivateConnector):
    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str,
        secret: str,
        market: Dict[str, Any],
        market_id: Dict[str, Any],
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            exchange_id="binance",
        )
        
        self._api_client = BinanceApiClient(
            api_key=api_key, secret=secret, testnet=account_type.is_testnet
        )
        
        self._ws_client = BinanceWSClient(
            account_type=account_type, handler=self._ws_msg_handler
        )
        
    @property
    def account_type(self) -> BinanceAccountType:
        return self._account_type    
    
    @property
    def market_type(self):
        if self.account_type.is_spot:
            return "_spot"
        elif self.account_type.is_linear:
            return "_linear"
        elif self.account_type.is_inverse:
            return "_inverse"

    
    async def _start_user_data_stream(self):
        if self.account_type.is_spot:
            res = await self._api_client.post_api_v3_user_data_stream()
        elif self.account_type.is_margin:
            res = await self._api_client.post_sapi_v1_user_data_stream()
        elif self.account_type.is_linear:
            res = await self._api_client.post_fapi_v1_listen_key()
        elif self.account_type.is_inverse:
            res = await self._api_client.post_dapi_v1_listen_key()
        elif self.account_type.is_portfolio_margin:
            res = await self._api_client.post_papi_v1_listen_key()
        return res.get("listenKey", None)
    
    async def _keep_alive_listen_key(self, listen_key: str):
        if self.account_type.is_spot:
            await self._api_client.put_api_v3_user_data_stream(listen_key)
        elif self.account_type.is_margin:
            await self._api_client.put_sapi_v1_user_data_stream(listen_key)
        elif self.account_type.is_linear:
            await self._api_client.put_fapi_v1_listen_key()
        elif self.account_type.is_inverse:
            await self._api_client.put_dapi_v1_listen_key()
        elif self.account_type.is_portfolio_margin:
            await self._api_client.put_papi_v1_listen_key()
        
        
    async def _keep_alive_user_data_stream(
        self, listen_key: str, interval: int = 20, max_retry: int = 3
    ):
        retry_count = 0
        while retry_count < max_retry:
            await asyncio.sleep(60 * interval)
            try:
                await self._keep_alive_listen_key(listen_key)
                retry_count = 0  # Reset retry count on successful keep-alive
            except Exception as e:
                self._log.error(f"Failed to keep alive listen key: {str(e)}")
                retry_count += 1
                if retry_count < max_retry:
                    await asyncio.sleep(5)
                else:
                    self._log.error(
                        f"Max retries ({max_retry}) reached. Stopping keep-alive attempts."
                    )
                    break

    async def connect(self):
        self._api_client.init_session()
        listen_key = await self._start_user_data_stream()
        if listen_key:
            asyncio.create_task(self._keep_alive_user_data_stream(listen_key))
            await self._ws_client.subscribe_user_data_stream(listen_key)

    def _ws_msg_handler(self, msg):
        if "e" in msg:
            match msg["e"]:
                case "ORDER_TRADE_UPDATE":
                    self._parse_order_trade_update(msg)
                case "executionReport":
                    self._parse_execution_report(msg)

    def _parse_order_trade_update(self, res: Dict[str, Any]) -> Order:
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
        event_data = res["o"]
        event_unit = res.get("fs", "")

        # Only portfolio margin has "UM" and "CM" event business unit
        if event_unit == "UM":
            id = event_data["s"] + "_linear"
            market = self._market_id[id]
        elif event_unit == "CM":
            id = event_data["s"] + "_inverse"
            market = self._market_id[id]
        else:
            id = event_data["s"] + self.market_type
            market = self._market_id[id]

        # we use the last filled quantity to calculate the cost, instead of the accumulated filled quantity
        if (type := event_data["o"].lower()) == "market":
            cost = float(event_data.get("l", "0")) * float(event_data.get("ap", "0"))
        elif type == "limit":
            price = float(event_data.get("ap", "0")) or float(
                event_data.get("p", "0")
            )  # if average price is 0 or empty, use price
            cost = float(event_data.get("l", "0")) * price

        order = Order(
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
            price=float(event_data.get("p", None)),
            average=float(event_data.get("ap", None)),
            last_filled_price=float(event_data.get("L", None)),
            amount=Decimal(event_data.get("q", None)),
            filled=Decimal(event_data.get("z", None)),
            last_filled=Decimal(event_data.get("l", None)),
            remaining=Decimal(event_data["q"]) - Decimal(event_data["z"]),
            fee=float(event_data.get("n", None)),
            fee_currency=event_data.get("N", None),
            cost=cost,
            last_trade_timestamp=event_data.get("T", None),
            reduce_only=event_data.get("R", None),
            position_side=event_data.get("ps", "").lower(),
            time_in_force=event_data.get("f", None),
        )
        # order status can be "new", "partially_filled", "filled", "canceled", "expired", "failed"
        self._emit_order(order)

    def _parse_execution_report(self, event_data: Dict[str, Any]) -> Order:
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
        id = event_data["s"] + self.market_type
        market = self._market_id[id]
        order = Order(
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
            price=float(event_data.get("p", None)),
            average=float(event_data.get("ap", None)),
            last_filled_price=float(event_data.get("L", None)),
            amount=Decimal(event_data.get("q", None)),
            filled=Decimal(event_data.get("z", None)),
            last_filled=float(event_data.get("l", None)),
            remaining=Decimal(event_data.get("q", "0"))
            - Decimal(event_data.get("z", "0")),
            fee=float(event_data.get("n", None)),
            fee_currency=event_data.get("N", None),
            cost=float(event_data.get("Y", None)),
            last_trade_timestamp=event_data.get("T", None),
            time_in_force=event_data.get("f", None),
        )
        self._emit_order(order)

    def _emit_order(self, order: Order):
        match order.status:
            case "new":
                EventSystem.emit(OrderStatus.NEW, order)
            case "partially_filled":
                EventSystem.emit(OrderStatus.PARTIALLY_FILLED, order)
            case "filled":
                EventSystem.emit(OrderStatus.FILLED, order)
            case "canceled":
                EventSystem.emit(OrderStatus.CANCELED, order)
            case "expired":
                EventSystem.emit(OrderStatus.EXPIRED, order)
            case "failed":
                EventSystem.emit(OrderStatus.FAILED, order)
    
    async def create_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        amount: Decimal,
        price: float = None,
        **kwargs
    ):
        market = self._market.get(symbol) or self._market_id.get(symbol + self.market_type)
        if not market:
            raise ValueError(f"Symbol {symbol} is not supported")
        symbol = market["id"]
        
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": type.upper(),
            "quantity": amount,
            **kwargs,
        }
        
        if type == "limit":
            params.update({
                "price": price,
                "timeInForce": kwargs.get("timeInForce", "GTC")
            })
            
        if self.account_type.is_spot:
            if not market["spot"]:
                raise ValueError(f"BinanceAccountType.{self.account_type.value} is not supported for {symbol}")
            res = await self._api_client.post_api_v3_order(**params)
        elif self.account_type.is_isolated_margin_or_margin:
            if not market["margin"]:
                raise ValueError(f"BinanceAccountType.{self.account_type.value} is not supported for {symbol}")
            res = await self._api_client.post_sapi_v1_margin_order(**params)
        elif self.account_type.is_linear:
            if not market["linear"]:
                raise ValueError(f"BinanceAccountType.{self.account_type.value} is not supported for {symbol}")
            res = await self._api_client.post_fapi_v1_order(**params)
        elif self.account_type.is_inverse:
            if not market["inverse"]:
                raise ValueError(f"BinanceAccountType.{self.account_type.value} is not supported for {symbol}")
            res = await self._api_client.post_dapi_v1_order(**params)
        elif self.account_type.is_portfolio_margin:
            if market["margin"]:
                res = await self._api_client.post_papi_v1_margin_order(**params)
            elif market["linear"]:
                res = await self._api_client.post_papi_v1_um_order(**params)
            elif market["inverse"]:
                res = await self._api_client.post_papi_v1_cm_order(**params)
        return res
    
    async def disconnect(self):
        # await self._api_client.close_session()
        self._ws_client.disconnect()
    
    

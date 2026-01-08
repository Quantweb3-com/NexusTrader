import msgspec
from decimal import Decimal
from typing import Dict, List, Any

from nexustrader.base.oms import OrderManagementSystem
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.kucoin.constants import KucoinAccountType,KUCOIN_INTERVAL_MAP
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient
from nexustrader.exchange.kucoin.websockets import KucoinWSClient, KucoinWSApiClient
from nexustrader.schema import Order, Position, BatchOrderSubmit
from nexustrader.schema import Kline, BookL1, BookL2, Trade, BookOrderData, Balance
from nexustrader.constants import KlineInterval
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    PositionSide,
)

class KucoinOrderManagementSystem(OrderManagementSystem):
    _account_type: KucoinAccountType
    _api_client: KucoinApiClient
    _ws_client: KucoinWSClient

    def __init__(
        self,
        account_type: KucoinAccountType,
        api_key: str | None,
        secret: str | None,
        market: Dict[str, Any],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: KucoinApiClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager,
        ws_client: KucoinWSClient | None = None,
    ):
        # Allow injecting a custom KucoinWSClient; otherwise create a default one.
        _ws_client = ws_client or KucoinWSClient(
            account_type=account_type,
            handler=self._ws_msg_handler,
            task_manager=task_manager,
            clock=clock,
        )

        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=_ws_client,
            exchange_id=exchange_id,
            clock=clock,
            msgbus=msgbus,
        )

        # Optional WS API client for placing/canceling via WS
        self._ws_api_client = None
        if api_key and secret:
            self._ws_api_client = KucoinWSApiClient(
                api_key=api_key,
                secret=secret,
                passphrase=getattr(api_client, "_passphrase", ""),
                handler=self._ws_api_msg_handler,
                task_manager=task_manager,
                clock=clock,
            )

        # WS decoders for routing public channel messages
        self._ws_general_decoder = msgspec.json.Decoder(dict)
        from nexustrader.exchange.kucoin.schema import (
            KucoinWsTradeMessage,
            KucoinWsSpotBook1Message,
            KucoinWsBook2Message,
            KucoinWsKlinesMessage,
        )
        self._ws_trade_decoder = msgspec.json.Decoder(KucoinWsTradeMessage)
        self._ws_spot_book_l1_decoder = msgspec.json.Decoder(KucoinWsSpotBook1Message)
        self._ws_book_l2_decoder = msgspec.json.Decoder(KucoinWsBook2Message)
        self._ws_kline_decoder = msgspec.json.Decoder(KucoinWsKlinesMessage)



    def _ws_msg_handler(self, raw: bytes):
        """Handle KuCoin WS messages by subject/channel and publish normalized data.

        Routes messages to trade, bookl1/2, and kline parsers similar to other exchanges.
        """
        try:
            msg = self._ws_general_decoder.decode(raw)
            subject = msg.get("subject")
            if subject in ("trade.l3match", "match"):
                self._parse_trade(raw)
            elif subject == "level1":
                self._parse_spot_bookl1(raw)
            elif subject == "level2":
                self._parse_bookl2(raw)
            elif subject in ("trade.candles.update", "candle.stick"):
                self._parse_kline(raw)
            else:
                # Unhandled, keep minimal log for debugging
                pass
        except Exception as e:
            self._log.debug(f"KuCoin WS msg decode error: {e}; raw: {raw}")

    def _parse_trade(self, raw: bytes) -> None:
        msg = self._ws_trade_decoder.decode(raw)
        data = msg.data

        symbol_id = data.symbol
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        side = OrderSide.BUY if (data.side or "").lower() == "buy" else OrderSide.SELL
        price = float(data.price)
        size = float(data.size)

        ts = int(data.ts)
        if ts > 10**13:  # nanoseconds
            ts_ms = ts // 1_000_000
        elif ts > 10**12:  # milliseconds
            ts_ms = ts
        else:  # seconds
            ts_ms = ts * 1000

        trade = Trade(
            exchange=self._exchange_id,
            symbol=symbol,
            price=price,
            size=size,
            timestamp=ts_ms,
            side=side,
        )
        print(trade)
        self._msgbus.publish(topic="trade", msg=trade)

    def _parse_spot_bookl1(self, raw: bytes) -> None:
        msg = self._ws_spot_book_l1_decoder.decode(raw)
        data = msg.data
        topic = msg.topic or ""
        symbol_id = topic.split(":", 1)[1] if ":" in topic else None
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        bid = float(data.bids[0]) if data.bids and len(data.bids) >= 1 else 0.0
        bid_size = float(data.bids[1]) if data.bids and len(data.bids) >= 2 else 0.0
        ask = float(data.asks[0]) if data.asks and len(data.asks) >= 1 else 0.0
        ask_size = float(data.asks[1]) if data.asks and len(data.asks) >= 2 else 0.0

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            timestamp=int(data.timestamp),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _parse_bookl2(self, raw: bytes) -> None:
        msg = self._ws_book_l2_decoder.decode(raw)
        data = msg.data
        topic = msg.topic or ""
        symbol_id = topic.split(":", 1)[1] if ":" in topic else None
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        bids = [BookOrderData(price=float(b[0]), size=float(b[1])) for b in (data.bids or [])]
        asks = [BookOrderData(price=float(a[0]), size=float(a[1])) for a in (data.asks or [])]

        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=int(data.timestamp),
        )
        print(bookl2)
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_kline(self, raw: bytes) -> None:
        msg = self._ws_kline_decoder.decode(raw)
        data = msg.data

        # Resolve symbol id
        symbol_id = getattr(data, "symbol", None)
        if not symbol_id:
            topic = msg.topic or ""
            if ":" in topic:
                try:
                    suffix = topic.split(":", 1)[1]
                    symbol_id = suffix.split("_", 1)[0]
                except Exception:
                    symbol_id = None
        if not symbol_id:
            return
        symbol = self._market_id.get(symbol_id)
        if not symbol:
            return

        candles = data.candles
        if not candles or len(candles) < 6:
            return
        t = int(candles[0])
        start_ms = t * 1000 if t < 10**12 else t
        o = float(candles[1])
        c = float(candles[2])
        h = float(candles[3])
        l = float(candles[4])
        v = float(candles[5]) if len(candles) > 5 else 0.0

        # Parse interval from topic suffix
        interval_str = ""
        topic = msg.topic or ""
        if ":" in topic and "_" in topic:
            try:
                interval_str = topic.split(":", 1)[1].split("_", 1)[1]
            except Exception:
                interval_str = ""
        interval = KUCOIN_INTERVAL_MAP.get(interval_str, KlineInterval.MINUTE_1)
        ticker = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            start=start_ms,
            open=o,
            close=c,
            high=h,
            low=l,
            volume=v,
            timestamp=int(getattr(data, "time", self._clock.timestamp_ms())),
            confirm=False,
        )
        self._msgbus.publish(topic="kline", msg=ticker)

    def _ws_api_msg_handler(self, raw: bytes):
        try:
            msg = msgspec.json.decode(raw)
        except Exception:
            self._log.debug(f"KuCoin WS API raw: {raw}")
            return

        # Correlate by our client-provided id (we pass oid as id),
        # fallback to clientOid in data if present
        oid = msg.get("id")
        data = msg.get("data") or {}
        if not oid:
            oid = data.get("clientOid") or data.get("oid")
        if not oid:
            self._log.debug(f"KuCoin WS API uncorrelated msg: {msg}")
            return

        tmp_order = self._registry.get_tmp_order(str(oid))
        if not tmp_order:
            self._log.debug(f"KuCoin WS API no tmp order for oid={oid}")
            return

        op = (msg.get("op") or "").lower()
        is_new = op.endswith(".order")
        is_cancel = op.endswith(".cancel")

        success = False
        code = msg.get("code")
        eid = data.get("orderId")
        success = (code == "200000") or (eid is not None)
        
        ts = self._clock.timestamp_ms()

        try:
            if is_new:
                if success:
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        oid=tmp_order.oid,
                        eid=eid or tmp_order.eid,
                        status=OrderStatus.PENDING,
                        side=tmp_order.side,
                        timestamp=ts,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self.order_status_update(order)
                else:
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        oid=tmp_order.oid,
                        status=OrderStatus.FAILED,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        timestamp=ts,
                        side=tmp_order.side,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self.order_status_update(order)
            elif is_cancel:
                if success:
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        oid=tmp_order.oid,
                        eid=eid or tmp_order.eid,
                        status=OrderStatus.CANCELING,
                        amount=tmp_order.amount,
                        side=tmp_order.side,
                        timestamp=ts,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self.order_status_update(order)
                else:
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        oid=tmp_order.oid,
                        status=OrderStatus.CANCEL_FAILED,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        side=tmp_order.side,
                        timestamp=ts,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self.order_status_update(order)
            else:
                # 非下单/撤单的 WS API 回包（如登录/订阅 ACK），略过
                self._log.debug(f"KuCoin WS API non-order op: {op}")
        except Exception as e:
            self._log.error(f"Error handling WS API order feedback: {e} msg={msg}")

    def _init_account_balance(self):
        try:
            if self._account_type == KucoinAccountType.SPOT:
                res = self._api_client.get_api_v1_accounts_sync()
                balances: List[Balance] = []
                for entry in res.data:
                    try:
                        balances.append(
                            Balance(
                                asset=entry.currency,
                                free=Decimal(entry.available),
                                locked=Decimal(entry.holds),
                            )
                        )
                    except Exception:
                        continue
                if balances:
                    self._cache._apply_balance(self._account_type, balances)
                    self._log.debug(
                        f"Initialized KuCoin spot balances: {len(balances)} assets"
                    )
            else:
                res = self._api_client.get_fapi_v1_account_sync()
                info = res.data
                free = Decimal(str(info.availableBalance))
                margin_balance = Decimal(str(info.marginBalance))
                locked = margin_balance - free
                balances = [
                    Balance(
                        asset=info.currency,
                        free=free,
                        locked=locked,
                    )
                ]
                self._cache._apply_balance(self._account_type, balances)
                self._log.debug("Initialized KuCoin futures balance applied")
        except Exception as e:
            self._log.warning(f"Init balance failed: {e}")

    def _init_position(self):
        if self._account_type != KucoinAccountType.FUTURES:
            return
        try:
            res = self._api_client.get_api_v1_positions_sync()
            
            for p in res.data:
                sym_id = p.symbol + "_linear"  # KuCoin futures are linear USDT margined
                symbol = self._market_id.get(sym_id, p.symbol)
                signed_amount = Decimal(p.currentQty)
                side = PositionSide.LONG if signed_amount > 0 else PositionSide.SHORT
                position = Position(
                    symbol=symbol,
                    exchange=self._exchange_id,
                    signed_amount=signed_amount,
                    side=side,
                    entry_price=float(p.avgEntryPrice),
                    unrealized_pnl=float(p.unrealisedPnl),
                    realized_pnl=float(p.realisedPnl),
                )
                self._cache._apply_position(position)
        except Exception as e:
            self._log.warning(f"Init positions failed: {e}")

    def _position_mode_check(self):
        # Enforce one-way mode for futures
        if self._account_type == KucoinAccountType.FUTURES:
            try:
                res = self._api_client.get_api_v1_position_mode_sync()
                self._log.debug(
                    f"KuCoin position mode: {getattr(res.data, 'positionMode', '?')}"
                )
            except Exception as e:
                raise

    async def create_tp_sl_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = TimeInForce.GTC,
        tp_order_type: OrderType | None = None,
        tp_trigger_price: Decimal | None = None,
        tp_price: Decimal | None = None,
        tp_trigger_type=None,
        sl_order_type: OrderType | None = None,
        sl_trigger_price: Decimal | None = None,
        sl_price: Decimal | None = None,
        sl_trigger_type=None,
        **kwargs,
    ) -> Order:
        # Not implemented for KuCoin in this minimal version
        raise NotImplementedError("KuCoin TP/SL via OMS not implemented")

    def _map_tif(self, tif: TimeInForce) -> str:
        if tif == TimeInForce.GTC:
            return "GTC"
        if tif == TimeInForce.IOC:
            return "IOC"
        if tif == TimeInForce.FOK:
            return "FOK"
        return "GTC"

    def _map_side(self, side: OrderSide) -> str:
        return "buy" if side == OrderSide.BUY else "sell"

    def _map_type(self, type: OrderType) -> str:
        return "limit" if type == OrderType.LIMIT else "market"

    async def create_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce,
        reduce_only: bool,
        **kwargs,
    ) -> Order:
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found")
        sym_id = market.id

        try:
            if self._account_type == KucoinAccountType.SPOT:
                params = {
                    "symbol": sym_id,
                    "type": self._map_type(type),
                    "side": self._map_side(side),
                    "clientOid": oid,
                    "timeInForce": self._map_tif(time_in_force),
                }
                if type == OrderType.LIMIT:
                    params["price"] = str(price)
                    params["size"] = str(amount)
                else:
                    # market order supports size or funds; using size here
                    params["size"] = str(amount)

                res = await self._api_client.post_api_v1_order(**params)

                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    oid=oid,
                    eid=getattr(res.data, "orderId", None),
                    status=OrderStatus.PENDING,
                    amount=amount,
                    type=type,
                    side=side,
                    price=float(price) if type == OrderType.LIMIT else None,
                    time_in_force=time_in_force,
                    timestamp=self._clock.timestamp_ms(),
                    reduce_only=reduce_only,
                )
            elif self._account_type == KucoinAccountType.FUTURES:
                # Map futures REST parameters per docs
                fparams = {
                    "symbol": sym_id,
                    "side": self._map_side(side),
                    "type": self._map_type(type),
                    "clientOid": oid,
                    "timeInForce": self._map_tif(time_in_force) if type == OrderType.LIMIT else None,
                    "reduceOnly": reduce_only,
                }
                # Optional advanced params from kwargs
                leverage = kwargs.get("leverage")
                margin_mode = kwargs.get("marginMode")
                position_side = kwargs.get("positionSide")
                post_only = kwargs.get("postOnly")
                hidden = kwargs.get("hidden")
                iceberg = kwargs.get("iceberg")
                visible_size = kwargs.get("visibleSize")
                remark = kwargs.get("remark")
                stop = kwargs.get("stop")
                stop_price = kwargs.get("stopPrice")
                stop_price_type = kwargs.get("stopPriceType")
                close_order = kwargs.get("closeOrder")
                force_hold = kwargs.get("forceHold")
                stp = kwargs.get("stp")

                if leverage is not None:
                    fparams["leverage"] = int(leverage)
                if margin_mode is not None:
                    fparams["marginMode"] = margin_mode
                if position_side is not None:
                    fparams["positionSide"] = position_side
                if post_only is not None:
                    fparams["postOnly"] = bool(post_only)
                if hidden is not None:
                    fparams["hidden"] = bool(hidden)
                if iceberg is not None:
                    fparams["iceberg"] = bool(iceberg)
                if visible_size is not None:
                    fparams["visibleSize"] = str(visible_size)
                if remark is not None:
                    fparams["remark"] = str(remark)
                if stop is not None:
                    fparams["stop"] = stop
                if stop_price is not None:
                    fparams["stopPrice"] = str(stop_price)
                if stop_price_type is not None:
                    fparams["stopPriceType"] = stop_price_type
                if close_order is not None:
                    fparams["closeOrder"] = bool(close_order)
                if force_hold is not None:
                    fparams["forceHold"] = bool(force_hold)
                if stp is not None:
                    fparams["stp"] = stp

                # Quantity fields: choose size for lot-based
                if type == OrderType.LIMIT:
                    fparams["price"] = str(price)
                    fparams["size"] = str(int(amount))
                else:
                    # market: can use size/qty/valueQty depending on contract; default to size
                    fparams["size"] = str(int(amount))

                fres = await self._api_client.post_fapi_v1_order(**fparams)

                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    oid=oid,
                    eid=fres.get("data", {}).get("orderId") if isinstance(fres, dict) else None,
                    status=OrderStatus.PENDING,
                    amount=amount,
                    type=type,
                    side=side,
                    price=float(price) if type == OrderType.LIMIT else None,
                    time_in_force=time_in_force,
                    timestamp=self._clock.timestamp_ms(),
                    reduce_only=reduce_only,
                )
        except Exception as e:
            self._log.error(f"Error creating order: {e}")
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.FAILED,
                amount=amount,
                type=type,
                side=side,
                price=float(price) if type == OrderType.LIMIT else None,
                time_in_force=time_in_force,
                timestamp=self._clock.timestamp_ms(),
                reduce_only=reduce_only,
            )

        self.order_status_update(order)
        return order

    async def create_order_ws(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce,
        reduce_only: bool,
        **kwargs,
    ):
        if not self._ws_api_client:
            raise RuntimeError("WS API client not configured")

        # Map symbol to exchange id
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found")
        sym_id = market.id

        # Build base params; KuCoin WS API expects strings for numeric fields
        params = {
            "side": self._map_side(side),
            "symbol": sym_id,
            "timeInForce": self._map_tif(time_in_force),
            "timestamp": self._clock.timestamp_ms(),
            "type": self._map_type(type),
        }
        # Quantity is "size" (spot) or "quantity" (futures) in various APIs; WS client abstracts this.
        params["quantity"] = float(amount)
        # Include price only for limit orders
        if type == OrderType.LIMIT:
            params["price"] = str(price)

        if self._account_type == KucoinAccountType.FUTURES:
            await self._ws_api_client.futures_add_order(
                id=oid,
                price=params.get("price"),
                quantity=params["quantity"],
                side=params["side"],
                symbol=params["symbol"],
                timeInForce=params["timeInForce"],
                timestamp=params["timestamp"],
                type=params["type"],
                reduceOnly=reduce_only,
            )
        else:
            await self._ws_api_client.spot_add_order(
                id=oid,
                price=params.get("price"),
                quantity=params["quantity"],
                side=params["side"],
                symbol=params["symbol"],
                timeInForce=params["timeInForce"],
                timestamp=params["timestamp"],
                type=params["type"],
            )

        # Register temp order for tracking
        self._registry.register_tmp_order(
            Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.PENDING,
                side=side,
                amount=amount,
                type=type,
                price=float(price) if type == OrderType.LIMIT else None,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                timestamp=self._clock.timestamp_ms(),
            )
        )

    async def create_batch_orders(self, orders: List[BatchOrderSubmit]) -> List[Order]:
        """Create multiple orders in a batch, modeled after Binance.

        - Spot: submits sequential REST `create_order` requests and aggregates results.
        - Futures: submits sequential REST `create_order` (using futures branch) and aggregates results.
        """
        results: List[Order] = []

        for o in orders:
            try:
                res = await self.create_order(
                    oid=o.oid,
                    symbol=o.symbol,
                    side=o.side,
                    type=o.type,
                    amount=o.amount,
                    price=o.price if o.type == OrderType.LIMIT else Decimal("0"),
                    time_in_force=o.time_in_force or TimeInForce.GTC,
                    reduce_only=getattr(o, "reduce_only", False),
                    # pass through optional futures params if present
                    leverage=getattr(o, "leverage", None),
                    marginMode=getattr(o, "marginMode", None),
                    positionSide=getattr(o, "positionSide", None),
                    postOnly=getattr(o, "postOnly", None),
                    hidden=getattr(o, "hidden", None),
                    iceberg=getattr(o, "iceberg", None),
                    visibleSize=getattr(o, "visibleSize", None),
                    remark=getattr(o, "remark", None),
                    stop=getattr(o, "stop", None),
                    stopPrice=getattr(o, "stopPrice", None),
                    stopPriceType=getattr(o, "stopPriceType", None),
                    closeOrder=getattr(o, "closeOrder", None),
                    forceHold=getattr(o, "forceHold", None),
                    stp=getattr(o, "stp", None),
                )
                results.append(res)
            except Exception as e:
                self._log.error(f"Batch order failed for {o.symbol}/{o.oid}: {e}")
                results.append(
                    Order(
                        exchange=self._exchange_id,
                        symbol=o.symbol,
                        oid=o.oid,
                        status=OrderStatus.FAILED,
                        side=o.side,
                        amount=o.amount,
                        type=o.type,
                        price=float(o.price) if o.type == OrderType.LIMIT else None,
                        time_in_force=o.time_in_force or TimeInForce.GTC,
                        reduce_only=getattr(o, "reduce_only", False),
                        timestamp=self._clock.timestamp_ms(),
                    )
                )

        return results

    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            sym_id = market.id

            if self._account_type == KucoinAccountType.SPOT:
                # Prefer clientOid for cancel; KuCoin API requires clientOid & symbol
                await self._api_client.delete_api_v1_order_by_clientoid(
                    clientOid=oid,
                    symbol=sym_id,
                )
            elif self._account_type == KucoinAccountType.FUTURES:
                # Support cancel by orderId or clientOid
                order_id = kwargs.get("orderId")
                client_oid = kwargs.get("clientOid", oid)
                if order_id:
                    await self._api_client.delete_fapi_v1_order_by_orderid(orderId=order_id)
                else:
                    await self._api_client.delete_fapi_v1_order_by_clientoid(
                        clientOid=client_oid,
                        symbol=sym_id,
                    )

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.CANCELING,
                timestamp=self._clock.timestamp_ms(),
            )
        except Exception as e:
            self._log.error(f"Error canceling order: {e}")
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.CANCEL_FAILED,
                timestamp=self._clock.timestamp_ms(),
            )
        self.order_status_update(order)
        return order

    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        if not self._ws_api_client:
            raise RuntimeError("WS API client not configured")
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found")
        sym_id = market.id

        await self._ws_api_client.connect()

        clientOid = kwargs.get("clientOid")
        orderId = kwargs.get("orderId")

        if self._account_type == KucoinAccountType.FUTURES:
            await self._ws_api_client.futures_cancel_order(
                id=oid, symbol=sym_id, clientOid=clientOid, orderId=orderId
            )
        else:
            await self._ws_api_client.spot_cancel_order(
                id=oid, symbol=sym_id, clientOid=clientOid, orderId=orderId
            )

    async def modify_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formatted wrongly, or not supported")
            sym_id = market.id

            order_id = kwargs.get("orderId")
            client_oid = kwargs.get("clientOid", oid)
            new_price = str(price) if price is not None else None
            new_size = str(amount) if amount is not None else None

            if self._account_type == KucoinAccountType.SPOT:
                await self._api_client.post_api_v1_order_modify(
                    symbol=sym_id,
                    orderId=order_id,
                    clientOid=client_oid,
                    newPrice=new_price,
                    newSize=new_size,
                )
            else:
                raise NotImplementedError("KuCoin futures modify order not implemented")

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.REPLACED,
                price=float(price) if price is not None else None,
                amount=amount if amount is not None else None,
                timestamp=self._clock.timestamp_ms(),
            )
        except Exception as e:
            self._log.error(f"Error modifying order: {e}")
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.REPLACE_FAILED,
                price=float(price) if price is not None else None,
                amount=amount if amount is not None else None,
                timestamp=self._clock.timestamp_ms(),
            )

        self.order_status_update(order)
        return order

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            if symbol:
                market = self._market.get(symbol)
                if not market:
                    raise ValueError(f"Symbol {symbol} formatted wrongly, or not supported")
                sym_id = market.id
            else:
                sym_id = None

            if self._account_type == KucoinAccountType.SPOT:
                if sym_id:
                    await self._api_client.delete_api_v1_orders_by_symbol(symbol=sym_id)
                else:
                    await self._api_client.delete_api_v1_orders_cancel_all()
            else:
                await self._api_client.delete_fapi_v1_orders(symbol=sym_id)  # sym_id may be None to cancel all
            return True
        except Exception as e:
            self._log.error(f"Error canceling all orders: {e}")
            return False


async def _test_create_and_cancel_order_spot(api_key: str, secret: str, passphrase: str) -> None:
    """Minimal test: instantiate KucoinOrderManagementSystem and run create_order + cancel_order for spot."""
    import asyncio
    from decimal import Decimal
    from nexustrader.core.entity import TaskManager

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    from nautilus_trader.model.identifiers import TraderId
    msgbus = MessageBus(trader_id=TraderId("TESTER-001"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-TEST",
        user_id="USER-TEST",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    api_client = KucoinApiClient(clock=clock, api_key=api_key, secret=secret)
    # attach passphrase for signed requests where required
    setattr(api_client, "_passphrase", passphrase)
    setattr(api_client, "_key_version", "2")

    # Minimal market mapping
    symbol = "BTC-USDT"
    class _M: id = symbol
    market = {symbol: _M()}
    market_id = {symbol: symbol}

    oms = KucoinOrderManagementSystem(
        account_type=KucoinAccountType.SPOT,
        api_key=api_key,
        secret=secret,
        market=market,
        market_id=market_id,
        registry=registry,
        cache=cache,
        api_client=api_client,
        exchange_id=ExchangeType.KUCOIN,
        clock=clock,
        msgbus=msgbus,
        task_manager=task_manager,
    )

    oid = f"spot-{clock.timestamp_ms()}"
    print("Creating spot order...")
    order = await oms.create_order(
        oid=oid,
        symbol=symbol,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        amount=Decimal("0.2"),
        price=Decimal("1"),
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
    )
    print({"create_status": order.status, "oid": order.oid, "eid": order.eid})

    print("Canceling spot order...")
    cancel_res = await oms.cancel_order(oid=oid, symbol=symbol)
    print({"cancel_status": cancel_res.status, "oid": cancel_res.oid})

# Test helper to create and cancel a spot order via WS API
async def _test_create_and_cancel_order_ws(api_key: str, secret: str, passphrase: str) -> None:
    """Minimal WS test: instantiate KucoinOrderManagementSystem and run create_order_ws + cancel_order_ws for spot."""
    import asyncio
    from decimal import Decimal
    from nexustrader.core.entity import TaskManager
    from nautilus_trader.model.identifiers import TraderId

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-WS"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-WS",
        user_id="USER-WS",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    api_client = KucoinApiClient(clock=clock, api_key=api_key, secret=secret)
    setattr(api_client, "_passphrase", passphrase)
    setattr(api_client, "_key_version", "2")

    # Minimal market mapping for spot
    symbol = "BTC-USDT"
    class _M: id = symbol
    market = {symbol: _M()}
    market_id = {symbol: symbol}

    oms = KucoinOrderManagementSystem(
        account_type=KucoinAccountType.SPOT,
        api_key=api_key,
        secret=secret,
        market=market,
        market_id=market_id,
        registry=registry,
        cache=cache,
        api_client=api_client,
        exchange_id=ExchangeType.KUCOIN,
        clock=clock,
        msgbus=msgbus,
        task_manager=task_manager,
    )

    # Ensure WS-API is connected before sending
    await oms._ws_api_client.connect()

    oid = f"ws-spot-{clock.timestamp_ms()}"
    print("Creating spot order via WS...")
    await oms.create_order_ws(
        oid=oid,
        symbol=symbol,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        amount=Decimal("0.2"),
        price=Decimal("1"),
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
    )

    await asyncio.sleep(2)

    print("Canceling spot order via WS...")
    await oms.cancel_order_ws(oid=oid, symbol=symbol)

    await asyncio.sleep(3)


async def _test_subscribe_kline_then_unsubscribe_spot(
    symbol: str = "BTC-USDT",
    interval: str = "1min",
) -> None:
    import asyncio
    from nautilus_trader.model.identifiers import TraderId
    from nexustrader.core.entity import TaskManager

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-KLINE"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-KLINE",
        user_id="USER-KLINE",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    oms = await _build_spot_oms_with_public_ws(
        symbol,
        task_manager=task_manager,
        clock=clock,
        msgbus=msgbus,
        registry=registry,
        cache=cache,
    )

    def _on_kline(k: Kline):
        print({
            "topic": "kline",
            "symbol": k.symbol,
            "interval": k.interval.value if hasattr(k.interval, "value") else k.interval,
            "close": k.close,
            "ts": k.timestamp,
        })

    msgbus.subscribe(topic="kline", handler=_on_kline)

    print(f"Subscribing spot kline: {symbol} {interval}...")
    await oms._ws_client.subscribe_spot_kline([symbol], interval)
    await asyncio.sleep(10)

    print(f"Unsubscribing spot kline: {symbol} {interval}...")
    await oms._ws_client.unsubscribe_spot_kline([symbol], interval)
    await asyncio.sleep(2)


async def _test_subscribe_spot_book_l1_then_unsubscribe(
    symbol: str = "BTC-USDT",
) -> None:
    import asyncio
    from nautilus_trader.model.identifiers import TraderId
    from nexustrader.core.entity import TaskManager

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-BOOKL1"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-BOOKL1",
        user_id="USER-BOOKL1",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    oms = await _build_spot_oms_with_public_ws(
        symbol,
        task_manager=task_manager,
        clock=clock,
        msgbus=msgbus,
        registry=registry,
        cache=cache,
    )

    def _on_bookl1(b: BookL1):
        print({
            "topic": "bookl1",
            "symbol": b.symbol,
            "bid": b.bid,
            "ask": b.ask,
            "bid_size": b.bid_size,
            "ask_size": b.ask_size,
            "ts": b.timestamp,
        })

    msgbus.subscribe(topic="bookl1", handler=_on_bookl1)

    print(f"Subscribing spot book L1: {symbol}...")
    await oms._ws_client.subscribe_spot_book_l1([symbol])
    await asyncio.sleep(10)

    print(f"Unsubscribing spot book L1: {symbol}...")
    await oms._ws_client.unsubscribe_spot_book_l1([symbol])
    await asyncio.sleep(2)


async def _test_subscribe_spot_trade_then_unsubscribe(
    symbol: str = "BTC-USDT",
) -> None:
    import asyncio
    from nautilus_trader.model.identifiers import TraderId
    from nexustrader.core.entity import TaskManager

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-TRADE"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-TRADE",
        user_id="USER-TRADE",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    oms = await _build_spot_oms_with_public_ws(
        symbol,
        task_manager=task_manager,
        clock=clock,
        msgbus=msgbus,
        registry=registry,
        cache=cache,
    )

    def _on_trade(t: Trade):
        print({
            "topic": "trade",
            "symbol": t.symbol,
            "side": t.side.value if hasattr(t.side, "value") else t.side,
            "price": t.price,
            "size": t.size,
            "ts": t.timestamp,
        })

    msgbus.subscribe(topic="trade", handler=_on_trade)

    print(f"Subscribing spot trade: {symbol}...")
    await oms._ws_client.subscribe_spot_trade([symbol])
    await asyncio.sleep(10)

    print(f"Unsubscribing spot trade: {symbol}...")
    await oms._ws_client.unsubscribe_spot_trade([symbol])
    await asyncio.sleep(2)


async def _test_subscribe_spot_book_l2_then_unsubscribe(
    symbol: str = "BTC-USDT",
) -> None:
    import asyncio
    from nautilus_trader.model.identifiers import TraderId
    from nexustrader.core.entity import TaskManager

    loop = asyncio.get_event_loop()
    task_manager = TaskManager(loop=loop)
    clock = LiveClock()
    msgbus = MessageBus(trader_id=TraderId("TESTER-BOOKL2"), clock=clock)
    registry = OrderRegistry()
    cache = AsyncCache(
        strategy_id="STRAT-BOOKL2",
        user_id="USER-BOOKL2",
        msgbus=msgbus,
        clock=clock,
        task_manager=task_manager,
    )

    oms = await _build_spot_oms_with_public_ws(
        symbol,
        task_manager=task_manager,
        clock=clock,
        msgbus=msgbus,
        registry=registry,
        cache=cache,
    )

    # Print a concise L2 summary
    def _on_bookl2(b: BookL2):
        top_bid = b.bids[0].price if b.bids else None
        top_ask = b.asks[0].price if b.asks else None
        print({
            "topic": "bookl2",
            "symbol": b.symbol,
            "bids": len(b.bids),
            "asks": len(b.asks),
            "top_bid": top_bid,
            "top_ask": top_ask,
            "ts": b.timestamp,
        })

    msgbus.subscribe(topic="bookl2", handler=_on_bookl2)

    print(f"Subscribing spot book L2: {symbol}...")
    await oms._ws_client.subscribe_spot_book_l5([symbol])
    await asyncio.sleep(10)

    print(f"Unsubscribing spot book L2: {symbol}...")
    await oms._ws_client.unsubscribe_spot_book_l5([symbol])
    await asyncio.sleep(2)

async def _build_spot_oms_with_public_ws(
    symbol: str,
    *,
    task_manager,
    clock: LiveClock,
    msgbus: MessageBus,
    registry: OrderRegistry,
    cache: AsyncCache,
) -> KucoinOrderManagementSystem:
    api_client = KucoinApiClient(clock=clock, api_key=None, secret=None)

    class _M:
        id = symbol

    market: Dict[str, Any] = {symbol: _M()}
    market_id: Dict[str, str] = {symbol: symbol}

    ws_url = await api_client.fetch_ws_url(futures=False, private=False)
    forward_handler = None

    def _handler(raw: bytes):
        if forward_handler:
            forward_handler(raw)

    custom_ws = KucoinWSClient(
        account_type=KucoinAccountType.SPOT,
        handler=_handler,
        task_manager=task_manager,
        clock=clock,
        custom_url=ws_url,
    )

    oms = KucoinOrderManagementSystem(
        account_type=KucoinAccountType.SPOT,
        api_key=None,
        secret=None,
        market=market,
        market_id=market_id,
        registry=registry,
        cache=cache,
        api_client=api_client,
        ws_client=custom_ws,
        exchange_id=ExchangeType.KUCOIN,
        clock=clock,
        msgbus=msgbus,
        task_manager=task_manager,
    )

    forward_handler = oms._ws_msg_handler
    return oms


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="KuCoin OMS tests")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # Kline subscribe/unsubscribe (public WS)
    p_kline = subparsers.add_parser(
        "kline",
        help="Subscribe spot kline for 10s then unsubscribe",
    )
    p_kline.add_argument("--symbol", default="BTC-USDT", help="Spot symbol, e.g. BTC-USDT")
    p_kline.add_argument("--interval", default="1min", help="Interval, e.g. 1min, 5min, 1hour")

    # Book L1 subscribe/unsubscribe (public WS)
    p_bookl1 = subparsers.add_parser(
        "bookl1",
        help="Subscribe spot book L1 for 10s then unsubscribe",
    )
    p_bookl1.add_argument("--symbol", default="BTC-USDT", help="Spot symbol, e.g. BTC-USDT")

    # Trade subscribe/unsubscribe (public WS)
    p_trade = subparsers.add_parser(
        "trade",
        help="Subscribe spot trade for 10s then unsubscribe",
    )
    p_trade.add_argument("--symbol", default="BTC-USDT", help="Spot symbol, e.g. BTC-USDT")

    # Book L2 subscribe/unsubscribe (public WS)
    p_bookl2 = subparsers.add_parser(
        "bookl2",
        help="Subscribe spot book L2 for 10s then unsubscribe",
    )
    p_bookl2.add_argument("--symbol", default="BTC-USDT", help="Spot symbol, e.g. BTC-USDT")

    # WS order create+cancel (requires credentials)
    p_wsorder = subparsers.add_parser(
        "ws-order",
        help="Create then cancel a spot order via WS API",
    )
    p_wsorder.add_argument("--api-key", required=True, help="KuCoin API key")
    p_wsorder.add_argument("--secret", required=True, help="KuCoin API secret")
    p_wsorder.add_argument("--passphrase", required=True, help="KuCoin API passphrase")

    args = parser.parse_args()

    if args.cmd == "kline":
        asyncio.run(
            _test_subscribe_kline_then_unsubscribe_spot(
                symbol=args.symbol,
                interval=args.interval,
            )
        )
    elif args.cmd == "bookl1":
        asyncio.run(
            _test_subscribe_spot_book_l1_then_unsubscribe(
                symbol=args.symbol,
            )
        )
    elif args.cmd == "trade":
        asyncio.run(
            _test_subscribe_spot_trade_then_unsubscribe(
                symbol=args.symbol,
            )
        )
    elif args.cmd == "bookl2":
        asyncio.run(
            _test_subscribe_spot_book_l2_then_unsubscribe(
                symbol=args.symbol,
            )
        )
    elif args.cmd == "ws-order":
        asyncio.run(
            _test_create_and_cancel_order_ws(
                args.api_key,
                args.secret,
                args.passphrase,
            )
        )

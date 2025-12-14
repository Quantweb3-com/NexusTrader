import msgspec
from decimal import Decimal
from typing import Dict, List, Any

from nexustrader.base.oms import OrderManagementSystem
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.kucoin.constants import KucoinAccountType
from nexustrader.exchange.kucoin.rest_api import KucoinApiClient
from nexustrader.exchange.kucoin.websockets import KucoinWSClient, KucoinWSApiClient
from nexustrader.schema import Order, Position, BatchOrderSubmit
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
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
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=KucoinWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
            ),
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

        # Decoders if needed later
        self._ws_general_decoder = msgspec.json.Decoder(object)

    def _ws_msg_handler(self, raw: bytes):
        # Placeholder: integrate order/balance updates when private streams are enabled
        try:
            _ = self._ws_general_decoder.decode(raw)
        except Exception:
            self._log.debug(f"KuCoin WS msg: {raw}")

    def _ws_api_msg_handler(self, raw: bytes):
        # KuCoin WS API returns op/id style frames; for now log
        try:
            msg = msgspec.json.decode(raw)
            self._log.debug(f"KuCoin WS API msg: {msg}")
        except Exception:
            self._log.debug(f"KuCoin WS API raw: {raw}")

    def _init_account_balance(self):
        # Best-effort: fetch and cache balances for spot or futures
        try:
            if self._account_type == KucoinAccountType.SPOT:
                res = self._api_client._task_manager.run_sync(
                    self._api_client.get_api_v1_accounts()
                )
                # Convert to internal balances if schema available; else skip
            else:
                res = self._api_client._task_manager.run_sync(
                    self._api_client.get_fapi_v1_account()
                )
            self._log.debug(f"Initialized KuCoin balances: {type(res).__name__}")
        except Exception as e:
            self._log.warning(f"Init balance failed: {e}")

    def _init_position(self):
        if self._account_type != KucoinAccountType.FUTURES:
            return
        try:
            res = self._api_client._task_manager.run_sync(
                self._api_client.get_api_v1_positions()
            )
            for p in res.data:
                sym_id = p.symbol + "_linear"  # KuCoin futures are linear USDT margined
                symbol = self._market_id.get(sym_id, p.symbol)
                signed_amount = Decimal(p.currentQty)
                side = None
                if signed_amount > 0:
                    side = None  # long/short mapping can be refined if API exposes side
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
                res = self._api_client._task_manager.run_sync(
                    self._api_client.get_api_v1_position_mode()
                )
                self._log.debug(
                    f"KuCoin position mode: {getattr(res.data, 'positionMode', '?')}"
                )
            except Exception as e:
                self._log.warning(f"Position mode check failed: {e}")

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
        """Create an order using KuCoin REST ApiClient (not WS API).

        Spot only in this minimal implementation. Futures REST order can be added later.
        Emits PENDING on success or FAILED on error via order_status_update().
        """
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
        """Cancel an order using KuCoin REST ApiClient (not WS API).

        Spot: uses `delete_api_v1_order_by_clientoid`.
        Futures: not implemented here yet.
        Emits CANCELING on success, CANCEL_FAILED on error.
        """
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

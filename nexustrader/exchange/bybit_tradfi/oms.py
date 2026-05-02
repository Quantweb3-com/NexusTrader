"""
OrderManagementSystem for the Bybit TradeFi (MT5) connector.

All order operations go through the MT5 Python API via the shared
single-threaded executor held by BybitTradeFiExchangeManager.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Dict, List

from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
    TriggerType,
)
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, Logger, MessageBus
from nexustrader.core.registry import OrderRegistry
from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager
from nexustrader.schema import Balance, BatchOrderSubmit, Order, Position


class BybitTradeFiOrderManagementSystem:
    """
    OMS for Bybit TradeFi.

    Implements the interface expected by ExecutionManagementSystem without
    subclassing the abstract OMS base class (which pulls in WSClient /
    ApiClient dependencies that are irrelevant for MT5).
    """

    def __init__(
        self,
        account_type: BybitTradeFiAccountType,
        exchange: BybitTradeFiExchangeManager,
        registry: OrderRegistry,
        cache: AsyncCache,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
    ) -> None:
        self._log = Logger(name=type(self).__name__)
        self._account_type = account_type
        self._exchange = exchange
        self._executor = exchange._executor
        self._market = exchange.market
        self._market_id = exchange.market_id
        self._registry = registry
        self._cache = cache
        self._clock = clock
        self._msgbus = msgbus
        self._task_manager = task_manager
        self._exchange_id = ExchangeType.BYBIT_TRADFI

        # Map NexusTrader oid → MT5 ticket (int)
        self._oid_to_ticket: Dict[str, int] = {}
        # Map MT5 ticket → oid (for reverse lookups in polling)
        self._ticket_to_oid: Dict[int, str] = {}

        # Stub attributes expected by PrivateConnector.disconnect()
        self._ws_client = _NullWsClientStub()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_account_balance(self) -> None:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_init_balance(), loop)
            future.result(timeout=30)
        else:
            loop.run_until_complete(self._async_init_balance())

    async def _async_init_balance(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            account = await loop.run_in_executor(self._executor, self._mt5_account_info)
            if account is None:
                self._log.warning(
                    "mt5.account_info() returned None – balance not initialised"
                )
                return
            balances = [
                Balance(
                    asset=account.currency,
                    free=Decimal(str(account.balance)),
                )
            ]
            self._cache._apply_balance(self._account_type, balances)
            await self._cache.sync_balances()
        except Exception as exc:
            self._log.error(f"Failed to initialise MT5 account balance: {exc}")

    def _init_position(self) -> None:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._async_init_position(), loop)
            future.result(timeout=30)
        else:
            loop.run_until_complete(self._async_init_position())

    async def _async_init_position(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            positions = await loop.run_in_executor(
                self._executor, self._mt5_positions_get
            )
            if not positions:
                return
            for pos in positions:
                nexus_symbol = self._market_id.get(pos.symbol)
                if nexus_symbol is None:
                    continue
                side = PositionSide.LONG if pos.type == 0 else PositionSide.SHORT
                signed = (
                    Decimal(str(pos.volume))
                    if side.is_long
                    else -Decimal(str(pos.volume))
                )
                position = Position(
                    symbol=nexus_symbol,
                    exchange=self._exchange_id,
                    side=side,
                    signed_amount=signed,
                    entry_price=pos.price_open,
                    unrealized_pnl=pos.profit,
                )
                self._cache._apply_position(position)
            await self._cache.sync_positions()
        except Exception as exc:
            self._log.error(f"Failed to initialise MT5 positions: {exc}")

    # ------------------------------------------------------------------
    # Order status broadcasting (mirrors OMS base class)
    # ------------------------------------------------------------------

    def order_status_update(self, order: Order) -> None:
        if order.oid is None:
            return
        if not self._registry.is_registered(order.oid):
            return

        valid = self._cache._order_status_update(order)
        if not valid:
            return

        endpoint_map = {
            OrderStatus.PENDING: "pending",
            OrderStatus.FAILED: "failed",
            OrderStatus.ACCEPTED: "accepted",
            OrderStatus.PARTIALLY_FILLED: "partially_filled",
            OrderStatus.CANCELED: "canceled",
            OrderStatus.CANCELING: "canceling",
            OrderStatus.CANCEL_FAILED: "cancel_failed",
            OrderStatus.FILLED: "filled",
        }
        endpoint = endpoint_map.get(order.status)
        if endpoint:
            self._msgbus.send(endpoint=endpoint, msg=order)

        if order.is_closed:
            self._registry.unregister_order(order.oid)
            self._registry.unregister_tmp_order(order.oid)
            # Clean up ticket mapping
            ticket = self._oid_to_ticket.pop(order.oid, None)
            if ticket is not None:
                self._ticket_to_oid.pop(ticket, None)

    # ------------------------------------------------------------------
    # MT5 raw calls (run in executor thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _mt5_account_info():
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().account_info()

    @staticmethod
    def _mt5_positions_get():
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().positions_get()

    @staticmethod
    def _mt5_orders_get():
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().orders_get()

    @staticmethod
    def _mt5_order_send(request: dict):
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().order_send(request)

    @staticmethod
    def _mt5_history_orders_get(ticket: int):
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        return get_mt5().history_orders_get(ticket=ticket)

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    async def create_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None,
        time_in_force: TimeInForce,
        reduce_only: bool,
        **kwargs,
    ) -> Order:
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        mt5 = get_mt5()
        mt5_symbol = self._nexus_to_mt5(symbol)
        if mt5_symbol is None:
            return self._failed_order(
                oid, symbol, side, type, amount, price, time_in_force
            )

        loop = asyncio.get_event_loop()

        # Build request dict
        if type in (
            OrderType.MARKET,
            OrderType.TAKE_PROFIT_MARKET,
            OrderType.STOP_LOSS_MARKET,
        ):
            action = mt5.TRADE_ACTION_DEAL
            order_type = mt5.ORDER_TYPE_BUY if side.is_buy else mt5.ORDER_TYPE_SELL
            fill_mode = mt5.ORDER_FILLING_IOC
            execution_price_coro = loop.run_in_executor(
                self._executor, lambda: self._get_market_price(mt5_symbol, side)
            )
            exec_price = await execution_price_coro
            request = {
                "action": action,
                "symbol": mt5_symbol,
                "volume": float(amount),
                "type": order_type,
                "price": exec_price,
                "type_filling": fill_mode,
                "comment": oid,
            }
        elif type in (OrderType.LIMIT, OrderType.POST_ONLY):
            action = mt5.TRADE_ACTION_PENDING
            order_type = (
                mt5.ORDER_TYPE_BUY_LIMIT if side.is_buy else mt5.ORDER_TYPE_SELL_LIMIT
            )
            price_type = kwargs.get("price_type")
            if price_type in ("bid", "ask", "opponent"):
                limit_price = await loop.run_in_executor(
                    self._executor,
                    lambda: self._get_fresh_price(mt5_symbol, side, price_type),
                )
            else:
                limit_price = float(price)
            request = {
                "action": action,
                "symbol": mt5_symbol,
                "volume": float(amount),
                "type": order_type,
                "price": limit_price,
                "comment": oid,
            }
        else:
            self._log.error(f"Unsupported MT5 order type: {type}")
            return self._failed_order(
                oid, symbol, side, type, amount, price, time_in_force
            )

        # Emit PENDING
        pending_order = self._make_order(
            oid, symbol, side, type, amount, price, time_in_force, OrderStatus.PENDING
        )
        self.order_status_update(pending_order)

        result = await loop.run_in_executor(
            self._executor, lambda: self._mt5_order_send(request)
        )

        if result is None or result.retcode != 10009:  # TRADE_RETCODE_DONE
            err = result.comment if result else "no result"
            self._log.error(f"MT5 order_send failed (oid={oid}): {err}")
            failed = self._make_order(
                oid,
                symbol,
                side,
                type,
                amount,
                price,
                time_in_force,
                OrderStatus.FAILED,
            )
            self.order_status_update(failed)
            return failed

        ticket = result.order or result.deal
        self._oid_to_ticket[oid] = ticket
        self._ticket_to_oid[ticket] = oid

        # Market orders fill immediately → FILLED
        if action == mt5.TRADE_ACTION_DEAL:
            filled = self._make_order(
                oid,
                symbol,
                side,
                type,
                amount,
                price,
                time_in_force,
                OrderStatus.FILLED,
                filled=amount,
                average=Decimal(str(result.price)),
            )
            self.order_status_update(filled)
            return filled

        # Pending orders → ACCEPTED
        accepted = self._make_order(
            oid, symbol, side, type, amount, price, time_in_force, OrderStatus.ACCEPTED
        )
        self.order_status_update(accepted)
        return accepted

    async def create_order_ws(self, *args, **kwargs) -> None:
        """MT5 has no WebSocket order API – delegates to REST path."""
        await self.create_order(*args, **kwargs)

    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        mt5 = get_mt5()
        ticket = self._oid_to_ticket.get(oid)
        if ticket is None:
            self._log.warning(f"cancel_order: no MT5 ticket found for oid={oid}")
            return self._unknown_cancel_order(oid, symbol)

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
            "comment": oid,
        }
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor, lambda: self._mt5_order_send(request)
        )

        side_val = OrderSide.BUY  # unknown side for cancel
        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            oid=oid,
            eid=str(ticket),
            side=side_val,
            type=OrderType.LIMIT,
            amount=Decimal("0"),
            filled=Decimal("0"),
            timestamp=self._clock.timestamp_ms(),
            status=OrderStatus.CANCELED
            if (result and result.retcode == 10009)
            else OrderStatus.CANCEL_FAILED,
            time_in_force=TimeInForce.GTC,
        )
        self.order_status_update(order)
        return order

    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        await self.cancel_order(oid, symbol, **kwargs)

    async def cancel_all_orders(self, symbol: str) -> bool:
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        mt5 = get_mt5()
        mt5_symbol = self._nexus_to_mt5(symbol)
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(
            self._executor, lambda: mt5.orders_get(symbol=mt5_symbol)
        )
        if not orders:
            return True
        success = True
        for o in orders:
            request = {"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}
            result = await loop.run_in_executor(
                self._executor, lambda: self._mt5_order_send(request)
            )
            if not result or result.retcode != 10009:
                success = False
        return success

    async def modify_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        mt5 = get_mt5()
        ticket = self._oid_to_ticket.get(oid)
        if ticket is None:
            self._log.warning(f"modify_order: no MT5 ticket for oid={oid}")
            return self._unknown_cancel_order(oid, symbol)

        request: dict = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": ticket,
        }
        if price is not None:
            request["price"] = float(price)
        tp = kwargs.get("tp_price") or kwargs.get("tp_trigger_price")
        sl = kwargs.get("sl_price") or kwargs.get("sl_trigger_price")
        if tp:
            request["tp"] = float(tp)
        if sl:
            request["sl"] = float(sl)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor, lambda: self._mt5_order_send(request)
        )
        ok = result and result.retcode == 10009
        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            oid=oid,
            eid=str(ticket),
            side=side or OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=amount or Decimal("0"),
            filled=Decimal("0"),
            timestamp=self._clock.timestamp_ms(),
            status=OrderStatus.ACCEPTED if ok else OrderStatus.FAILED,
            time_in_force=TimeInForce.GTC,
            price=price,
        )
        self.order_status_update(order)
        return order

    async def create_batch_orders(self, orders: List[BatchOrderSubmit]) -> List[Order]:
        results = []
        for o in orders:
            result = await self.create_order(
                oid=o.oid,
                symbol=o.symbol,
                side=o.side,
                type=o.type,
                amount=o.amount,
                price=o.price,
                time_in_force=o.time_in_force or TimeInForce.GTC,
                reduce_only=o.reduce_only,
                **o.kwargs,
            )
            results.append(result)
        return results

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
        tp_trigger_type: TriggerType | None = None,
        sl_order_type: OrderType | None = None,
        sl_trigger_price: Decimal | None = None,
        sl_price: Decimal | None = None,
        sl_trigger_type: TriggerType | None = None,
        **kwargs,
    ) -> Order:
        return await self.create_order(
            oid=oid,
            symbol=symbol,
            side=side,
            type=type,
            amount=amount,
            price=price,
            time_in_force=time_in_force or TimeInForce.GTC,
            reduce_only=False,
            tp_price=tp_price or tp_trigger_price,
            sl_price=sl_price or sl_trigger_price,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Background order-status polling
    # ------------------------------------------------------------------

    async def start_order_polling(self, interval_s: float = 0.5) -> None:
        """
        Periodically poll MT5 pending orders and closed history to update
        order statuses in NexusTrader.
        """
        while True:
            await asyncio.sleep(interval_s)
            try:
                await self._poll_pending_orders()
            except Exception as exc:
                self._log.error(f"Order polling error: {exc}")

    async def _poll_pending_orders(self) -> None:
        if not self._oid_to_ticket:
            return
        loop = asyncio.get_event_loop()
        mt5_orders = await loop.run_in_executor(self._executor, self._mt5_orders_get)
        live_tickets = {o.ticket for o in mt5_orders} if mt5_orders else set()

        for oid, ticket in list(self._oid_to_ticket.items()):
            if ticket in live_tickets:
                continue  # still open
            # Order is gone from pending → check history
            history = await loop.run_in_executor(
                self._executor, lambda: self._mt5_history_orders_get(ticket)
            )
            if not history:
                continue
            hist_order = history[0]
            status = self._map_mt5_order_state(hist_order.state)
            nexus_symbol = self._market_id.get(hist_order.symbol, hist_order.symbol)
            order = Order(
                exchange=self._exchange_id,
                symbol=nexus_symbol,
                oid=oid,
                eid=str(ticket),
                side=OrderSide.BUY if hist_order.type in (0, 2, 4) else OrderSide.SELL,
                type=OrderType.LIMIT,
                amount=Decimal(str(hist_order.volume_initial)),
                filled=Decimal(str(hist_order.volume_current)),
                timestamp=int(hist_order.time_done) * 1000,
                status=status,
                time_in_force=TimeInForce.GTC,
            )
            self.order_status_update(order)

    @staticmethod
    def _map_mt5_order_state(state: int) -> OrderStatus:
        # MT5 ORDER_STATE_* constants
        # 0=STARTED, 1=PLACED, 2=CANCELED, 3=PARTIAL, 4=FILLED,
        # 5=REJECTED, 6=EXPIRED, 7=REQUEST_ADD, 8=REQUEST_MODIFY, 9=REQUEST_CANCEL
        mapping = {
            0: OrderStatus.ACCEPTED,
            1: OrderStatus.ACCEPTED,
            2: OrderStatus.CANCELED,
            3: OrderStatus.PARTIALLY_FILLED,
            4: OrderStatus.FILLED,
            5: OrderStatus.FAILED,
            6: OrderStatus.EXPIRED,
        }
        return mapping.get(state, OrderStatus.ACCEPTED)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _nexus_to_mt5(self, nexus_symbol: str) -> str | None:
        """Reverse-lookup: NexusTrader symbol → MT5 symbol name."""
        market = self._market.get(nexus_symbol)
        return market.id if market else None

    @staticmethod
    def _get_market_price(mt5_symbol: str, side: OrderSide) -> float:
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        tick = get_mt5().symbol_info_tick(mt5_symbol)
        if tick is None:
            raise RuntimeError(f"Cannot get tick for {mt5_symbol}")
        return tick.ask if side.is_buy else tick.bid

    @staticmethod
    def _get_fresh_price(mt5_symbol: str, side: OrderSide, price_type: str) -> float:
        """Fetch the latest tick from MT5 and return the requested price side.

        Parameters
        ----------
        price_type:
            "bid"      – always use the current best bid.
            "ask"      – always use the current best ask.
            "opponent" – the price that will trade against the counterpart:
                         ask for a buy order, bid for a sell order.
        """
        from nexustrader.exchange.bybit_tradfi._mt5_bridge import get_mt5

        tick = get_mt5().symbol_info_tick(mt5_symbol)
        if tick is None:
            raise RuntimeError(f"Cannot get tick for {mt5_symbol}")
        if price_type == "bid":
            return tick.bid
        if price_type == "ask":
            return tick.ask
        # "opponent"
        return tick.ask if side.is_buy else tick.bid

    def _make_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None,
        time_in_force: TimeInForce,
        status: OrderStatus,
        filled: Decimal = Decimal("0"),
        average: Decimal | None = None,
    ) -> Order:
        return Order(
            exchange=self._exchange_id,
            symbol=symbol,
            oid=oid,
            side=side,
            type=type,
            amount=amount,
            filled=filled,
            remaining=amount - filled,
            price=price,
            average=average,
            timestamp=self._clock.timestamp_ms(),
            status=status,
            time_in_force=time_in_force,
        )

    def _failed_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None,
        time_in_force: TimeInForce,
    ) -> Order:
        return self._make_order(
            oid, symbol, side, type, amount, price, time_in_force, OrderStatus.FAILED
        )

    def _unknown_cancel_order(self, oid: str, symbol: str) -> Order:
        return Order(
            exchange=self._exchange_id,
            symbol=symbol,
            oid=oid,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=Decimal("0"),
            filled=Decimal("0"),
            timestamp=self._clock.timestamp_ms(),
            status=OrderStatus.CANCEL_FAILED,
            time_in_force=TimeInForce.GTC,
        )


class _NullWsClientStub:
    """Placeholder so PrivateConnector.disconnect() can call _ws_client.disconnect()."""

    async def disconnect(self) -> None:
        pass

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Literal
from decimal import Decimal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from nexustrader.constants import AccountType, ExchangeType, WsOrderResultType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import Logger, LiveClock, MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.base.api_client import ApiClient
from nexustrader.base.ws_client import WSClient
from nexustrader.schema import (
    Order,
    BaseMarket,
    BatchOrderSubmit,
)
from nexustrader.constants import (
    OrderSide,
    OrderType,
    TimeInForce,
    TriggerType,
    OrderStatus,
)


class OrderManagementSystem(ABC):
    def __init__(
        self,
        account_type: AccountType,
        market: Dict[str, BaseMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: ApiClient,
        ws_client: WSClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
    ):
        self._log = Logger(name=type(self).__name__)
        self._market = market
        self._market_id = market_id
        self._registry = registry
        self._account_type = account_type
        self._cache = cache
        self._api_client = api_client
        self._ws_client = ws_client
        self._exchange_id = exchange_id
        self._clock = clock
        self._msgbus = msgbus
        self._task_manager = task_manager
        self._reconnect_reconcile_grace_ms = 700
        self._cancel_success_reconcile_delay_sec = 1.0
        self._post_ack_terminal_reconcile_delay_sec = 1.0
        self._post_ack_terminal_reconcile_max_attempts = 3
        self._post_ack_terminal_reconcile_oids: set[str] = set()

        self._ws_client.set_lifecycle_hooks(
            on_connected=self._on_private_ws_connected,
            on_disconnected=self._on_private_ws_disconnected,
            on_reconnected=self._on_private_ws_reconnected,
        )

        self._init_account_balance()
        self._init_position()
        self._position_mode_check()

    def _run_sync(self, coro):
        return self._task_manager.run_sync(coro)

    def _publish_private_ws_event(self, event: str):
        self._msgbus.publish(
            topic="private_ws_status",
            msg={
                "exchange": self._exchange_id.value,
                "account_type": self._account_type.value,
                "event": event,
                "timestamp": self._clock.timestamp_ms(),
            },
        )

    def _on_private_ws_connected(self):
        self._publish_private_ws_event("connected")

    def _on_private_ws_disconnected(self):
        self._publish_private_ws_event("disconnected")

    async def _on_private_ws_reconnected(self):
        self._publish_private_ws_event("reconnected")
        diff = await self._resync_after_reconnect()
        self._msgbus.publish(
            topic="private_ws_resync_diff",
            msg={
                "exchange": self._exchange_id.value,
                "account_type": self._account_type.value,
                "timestamp": self._clock.timestamp_ms(),
                "diff": diff,
            },
        )
        if diff.get("success", True):
            self._publish_private_ws_event("resynced")
        else:
            self._publish_private_ws_event("resync_failed")

    async def _resync_after_reconnect(self):
        # Default behavior: refresh balances and positions only.
        # Exchange-specific OMS can override to include open orders / recent trades replay.
        before_positions = set(self._cache.get_all_positions(self._exchange_id).keys())
        before_open_orders = set(
            self._cache.get_open_orders(
                exchange=self._exchange_id, include_canceling=True
            )
        )
        try:
            await self._async_resync_init()
            after_positions = set(
                self._cache.get_all_positions(self._exchange_id).keys()
            )
            after_open_orders = set(
                self._cache.get_open_orders(
                    exchange=self._exchange_id, include_canceling=True
                )
            )
            return {
                "success": True,
                "positions_opened": sorted(after_positions - before_positions),
                "positions_closed": sorted(before_positions - after_positions),
                "open_orders_added": sorted(after_open_orders - before_open_orders),
                "open_orders_removed": sorted(before_open_orders - after_open_orders),
            }
        except Exception as e:
            self._log.error(f"Private WS reconnect resync failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "positions_opened": [],
                "positions_closed": [],
                "open_orders_added": [],
                "open_orders_removed": [],
            }

    async def _confirm_missing_open_orders(
        self, missing_oids: set[str], grace_ms: int | None = None
    ) -> set[str]:
        """
        Conservative missing-order confirmation after reconnect:
        - wait a short grace window for delayed snapshots/callbacks
        - re-query each order via fetch_order
        - only return oids that are confirmed closed
        """
        if not missing_oids:
            return set()

        if grace_ms is None:
            grace_ms = self._reconnect_reconcile_grace_ms

        await asyncio.sleep(max(grace_ms, 0) / 1000)
        confirmed_closed: set[str] = set()

        for oid in missing_oids:
            cached = self._cache.get_order(oid)
            if cached is None or not isinstance(cached, Order):
                continue

            try:
                latest = await self.fetch_order(cached.symbol, oid, force_refresh=True)
            except Exception as e:
                self._log.warning(
                    f"Missing-order confirmation failed for {cached.symbol}#{oid}: {e}"
                )
                continue

            # If query returns no data, keep the order conservative-open.
            if latest is None:
                self._log.warning(
                    f"Reconnect reconcile keeps order open (unconfirmed): {cached.symbol}#{oid}"
                )
                continue

            self.order_status_update(latest)
            if latest.is_closed:
                confirmed_closed.add(oid)

        return confirmed_closed

    async def _async_resync_init(self):
        """Run the synchronous _init_account_balance / _init_position in a thread-pool
        executor so they do not block the event-loop thread.

        Background: both methods call ``_run_sync()`` which internally uses
        ``asyncio.run_coroutine_threadsafe(coro, loop).result()``.  When
        invoked from a coroutine that is already running inside the event loop
        (e.g. as a task created by ``_emit_hook``), calling ``.result()`` on
        the event-loop thread deadlocks because the loop is blocked waiting
        for the future to complete, yet the future can only be completed by
        the same loop.  Running the call in an executor thread avoids this:
        the executor thread blocks on ``.result()`` while the event loop
        remains free to drive the submitted coroutine to completion.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_account_balance)
        await loop.run_in_executor(None, self._init_position)

    def set_reconnect_reconcile_grace_ms(self, grace_ms: int):
        if grace_ms < 0:
            raise ValueError("grace_ms must be >= 0")
        self._reconnect_reconcile_grace_ms = grace_ms

    def _reject_all_pending_ws_acks(self):
        """Reject all pending WS ACK futures on WS API disconnect.

        Override in exchange OMS that maintains ``_pending_ws_acks``.
        """

    def _on_ws_api_disconnected(self):
        self._reject_all_pending_ws_acks()

    async def _confirm_order_after_ack_timeout(self, oid: str, symbol: str) -> bool:
        """Try REST ``fetch_order`` after ACK timeout to resolve order state.

        Returns ``True`` if the order was found (state updated in cache),
        ``False`` if still unknown (REST also failed or order not found).
        """
        try:
            order = await self.fetch_order(symbol, oid, force_refresh=True)
            if order is not None:
                self._log.info(
                    f"[{symbol}] ACK timeout resolved via REST: oid={oid} status={order.status}"
                )
                self.order_status_update(order)
                return True
        except Exception as e:
            self._log.error(
                f"[{symbol}] REST confirmation after ACK timeout failed: {e}"
            )
        return False

    def _should_reconcile_terminal_after_ack(self, order: Order) -> bool:
        if order.is_closed:
            return False

        if order.status not in {
            OrderStatus.PENDING,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            return False

        if order.type is not None and order.type.is_market:
            return True

        return order.time_in_force in {TimeInForce.IOC, TimeInForce.FOK}

    def _schedule_post_ack_terminal_reconcile(self, order: Order):
        if not self._should_reconcile_terminal_after_ack(order):
            return

        if not hasattr(self, "_post_ack_terminal_reconcile_oids"):
            self._post_ack_terminal_reconcile_oids = set()

        if order.oid in self._post_ack_terminal_reconcile_oids:
            return

        self._post_ack_terminal_reconcile_oids.add(order.oid)
        self._task_manager.create_task(
            self._reconcile_post_ack_terminal_after_grace(order.oid, order.symbol),
            name=f"{self._exchange_id.value}-post-ack-terminal-reconcile-{order.oid}",
        )

    def _is_meaningful_order_update(self, cached: Order | None, latest: Order) -> bool:
        if cached is None:
            return True

        return any(
            (
                latest.status != cached.status,
                latest.filled != cached.filled,
                latest.remaining != cached.remaining,
                latest.average != cached.average,
                latest.eid != cached.eid,
            )
        )

    async def _reconcile_post_ack_terminal_after_grace(self, oid: str, symbol: str):
        try:
            delay = getattr(self, "_post_ack_terminal_reconcile_delay_sec", 1.0)
            max_attempts = getattr(
                self, "_post_ack_terminal_reconcile_max_attempts", 3
            )

            for _ in range(max_attempts):
                await asyncio.sleep(delay)

                cached = self._cache.get_order(oid)
                if cached is None or not isinstance(cached, Order):
                    return
                if cached.is_closed or not self._registry.is_registered(oid):
                    return

                try:
                    latest = await self.fetch_order(symbol, oid, force_refresh=True)
                except Exception as e:
                    self._log.warning(
                        f"[{symbol}] post-ACK terminal reconciliation failed for oid={oid}: {e}"
                    )
                    continue

                if latest is None:
                    continue

                if self._is_meaningful_order_update(cached, latest):
                    self._log.warning(
                        f"[{symbol}] post-ACK order reconciled via REST: "
                        f"oid={oid} status={latest.status}"
                    )
                    self.order_status_update(latest)

                if latest.is_closed:
                    return

            cached = self._cache.get_order(oid)
            if cached is not None and isinstance(cached, Order) and not cached.is_closed:
                self._log.warning(
                    f"[{symbol}] post-ACK terminal reconciliation exhausted for "
                    f"oid={oid} status={cached.status}"
                )
        finally:
            if hasattr(self, "_post_ack_terminal_reconcile_oids"):
                self._post_ack_terminal_reconcile_oids.discard(oid)

    def _schedule_cancel_success_reconcile(self, oid: str, symbol: str):
        self._task_manager.create_task(
            self._reconcile_cancel_success_after_grace(oid, symbol),
            name=f"{self._exchange_id.value}-cancel-success-reconcile-{oid}",
        )

    async def _reconcile_cancel_success_after_grace(self, oid: str, symbol: str):
        await asyncio.sleep(self._cancel_success_reconcile_delay_sec)

        cached = self._cache.get_order(oid)
        if cached is not None and isinstance(cached, Order) and cached.is_closed:
            return

        try:
            latest = await self.fetch_order(symbol, oid, force_refresh=True)
        except Exception as e:
            self._log.warning(
                f"[{symbol}] cancel success reconciliation failed for oid={oid}: {e}"
            )
            return

        if latest is None:
            return

        self._log.warning(
            f"[{symbol}] cancel success reconciled via REST: "
            f"oid={oid} status={latest.status}"
        )
        self.order_status_update(latest)

    def order_status_update(self, order: Order, silent: bool = False):
        """Update order state in cache and optionally dispatch strategy callbacks.

        Args:
            order:  The updated order object.
            silent: When ``True`` the cache is updated but **no** strategy
                    callbacks are dispatched.  Use this during reconnect
                    resync to refresh cache state without re-triggering
                    callbacks (e.g. ``on_accepted_order``) for orders whose
                    status has not meaningfully changed.
        """
        if order.oid is None:
            return

        if not self._registry.is_registered(order.oid):
            return

        valid = self._cache.update_order_status(order)
        if not valid:
            return

        if silent:
            return

        match order.status:
            case OrderStatus.PENDING:
                self._log.debug(f"ORDER STATUS PENDING: {str(order)}")
                self._msgbus.send(endpoint="pending", msg=order)
            case OrderStatus.FAILED:
                self._log.debug(f"ORDER STATUS FAILED: {str(order)}")
                self._msgbus.send(endpoint="failed", msg=order)
            case OrderStatus.ACCEPTED:
                self._log.debug(f"ORDER STATUS ACCEPTED: {str(order)}")
                self._msgbus.send(endpoint="accepted", msg=order)
            case OrderStatus.PARTIALLY_FILLED:
                self._log.debug(f"ORDER STATUS PARTIALLY FILLED: {str(order)}")
                self._msgbus.send(endpoint="partially_filled", msg=order)
            case OrderStatus.CANCELED:
                self._log.debug(f"ORDER STATUS CANCELED: {str(order)}")
                self._msgbus.send(endpoint="canceled", msg=order)
            case OrderStatus.CANCELING:
                self._log.debug(f"ORDER STATUS CANCELING: {str(order)}")
                self._msgbus.send(endpoint="canceling", msg=order)
            case OrderStatus.CANCEL_FAILED:
                self._log.debug(f"ORDER STATUS CANCEL FAILED: {str(order)}")
                self._msgbus.send(endpoint="cancel_failed", msg=order)
            case OrderStatus.FILLED:
                self._log.debug(f"ORDER STATUS FILLED: {str(order)}")
                self._msgbus.send(endpoint="filled", msg=order)
            case OrderStatus.EXPIRED:
                self._log.debug(f"ORDER STATUS EXPIRED: {str(order)}")

        if order.is_closed:
            self._registry.unregister_order(order.oid)
            self._registry.unregister_tmp_order(order.oid)

    def _price_to_precision(
        self,
        symbol: str,
        price: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        """
        Convert the price to the precision of the market
        """
        market = self._market[symbol]
        price: Decimal = Decimal(str(price))

        decimal = market.precision.price

        if decimal >= 1:
            exp = Decimal(int(decimal))
            precision_decimal = Decimal("1")
        else:
            exp = Decimal("1")
            precision_decimal = Decimal(str(decimal))

        if mode == "round":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_HALF_UP
            ) * exp
        elif mode == "ceil":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_CEILING
            ) * exp
        elif mode == "floor":
            format_price = (price / exp).quantize(
                precision_decimal, rounding=ROUND_FLOOR
            ) * exp
        return format_price

    @abstractmethod
    def _init_account_balance(self):
        """Initialize the account balance"""
        pass

    @abstractmethod
    def _init_position(self):
        """Initialize the position"""
        pass

    @abstractmethod
    def _position_mode_check(self):
        """Check the position mode"""
        pass

    @abstractmethod
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
        tp_trigger_type: TriggerType | None = TriggerType.LAST_PRICE,
        sl_order_type: OrderType | None = None,
        sl_trigger_price: Decimal | None = None,
        sl_price: Decimal | None = None,
        sl_trigger_type: TriggerType | None = TriggerType.LAST_PRICE,
        **kwargs,
    ) -> Order:
        """Create a take profit and stop loss order"""
        pass

    @abstractmethod
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
        """Create an order"""
        pass

    @abstractmethod
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
    ) -> WsOrderResultType | None:
        pass

    @abstractmethod
    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create a batch of orders"""
        pass

    @abstractmethod
    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        """Cancel an order"""
        pass

    @abstractmethod
    async def cancel_order_ws(
        self, oid: str, symbol: str, **kwargs
    ) -> WsOrderResultType | None:
        """Cancel an order"""
        pass

    @abstractmethod
    async def modify_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        """Modify an order"""
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders"""
        pass

    async def fetch_order(
        self, symbol: str, oid: str, force_refresh: bool = False
    ) -> Order | None:
        return None

    async def fetch_open_orders(self, symbol: str) -> list[Order]:
        return []

    async def fetch_recent_trades(
        self,
        symbol: str,
        limit: int = 50,
        since_ms: int | None = None,
    ) -> list[Order]:
        """Return recent filled orders for *symbol*.

        The base implementation scans the local cache and is intended as a
        fallback.  Exchange-specific OMS subclasses **should** override this
        method to query the exchange's fills/trade-history REST endpoint
        (e.g. ``GET /fapi/v1/userTrades``, ``GET /v5/execution/list``, …)
        so that fills that arrived during a WS disconnect gap are captured
        even when the order was not tracked in the local registry.

        Args:
            symbol:   Internal symbol string (e.g. ``"BTCUSDT-PERP.BINANCE"``).
            limit:    Maximum number of trades to return.
            since_ms: If given, only return trades with ``timestamp >= since_ms``.
                      Exchange overrides are expected to pass this to the REST
                      ``startTime`` / ``begin`` parameter where supported.
        """
        oids = self._cache.get_symbol_orders(symbol)
        orders: list[Order] = []
        for oid in oids:
            order = self._cache.get_order(oid)
            if order is None or not isinstance(order, Order):
                continue
            if not (order.filled and order.filled > 0):
                continue
            if since_ms is not None and (order.timestamp or 0) < since_ms:
                continue
            orders.append(order)
        orders.sort(key=lambda x: x.timestamp or 0, reverse=True)
        return orders[:limit]

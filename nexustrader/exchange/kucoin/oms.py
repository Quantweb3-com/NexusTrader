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
        # Prefer WS API if available
        if self._ws_api_client:
            return await self.create_order_ws(
                oid,
                symbol,
                side,
                type,
                amount,
                price,
                time_in_force,
                reduce_only,
                **kwargs,
            )
        raise NotImplementedError("KuCoin REST order not implemented in this OMS")

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

        params = {
            "price": str(price),
            "quantity": float(amount),
            "side": self._map_side(side),
            "symbol": sym_id,
            "timeInForce": self._map_tif(time_in_force),
            "timestamp": self._clock.timestamp_ms(),
            "type": self._map_type(type),
        }

        await self._ws_api_client.connect()

        if self._account_type == KucoinAccountType.FUTURES:
            await self._ws_api_client.futures_add_order(
                id=oid,
                price=params["price"],
                quantity=params["quantity"],
                side=params["side"],
                symbol=params["symbol"],
                timeInForce=params["timeInForce"],
                timestamp=params["timestamp"],
                type=params["type"],
            )
        else:
            await self._ws_api_client.spot_add_order(
                id=oid,
                price=params["price"],
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
                price=float(price),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                timestamp=self._clock.timestamp_ms(),
            )
        )

    async def create_batch_orders(self, orders: List[BatchOrderSubmit]) -> List[Order]:
        # Spot REST batch supported; futures batch not implemented here
        raise NotImplementedError("KuCoin batch orders not implemented")

    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        # Prefer WS API cancel
        if self._ws_api_client:
            await self.cancel_order_ws(oid, symbol, **kwargs)
            # Return a lightweight canceling status
            return Order(
                exchange=self._exchange_id,
                symbol=symbol,
                oid=oid,
                status=OrderStatus.CANCELING,
                timestamp=self._clock.timestamp_ms(),
            )
        raise NotImplementedError("KuCoin REST cancel not implemented")

    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        if not self._ws_api_client:
            raise RuntimeError("WS API client not configured")
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found")
        sym_id = market.id

        await self._ws_api_client.connect()

        if self._account_type == KucoinAccountType.FUTURES:
            await self._ws_api_client.futures_cancel_order(id=oid, symbol=sym_id)
        else:
            await self._ws_api_client.spot_cancel_order(id=oid, symbol=sym_id)

    async def modify_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        # Spot REST modify supported in API client; futures TBD
        raise NotImplementedError("KuCoin modify order not implemented")

    async def cancel_all_orders(self, symbol: str) -> bool:
        # Spot REST cancel-all supported; futures TBD
        raise NotImplementedError("KuCoin cancel all not implemented")

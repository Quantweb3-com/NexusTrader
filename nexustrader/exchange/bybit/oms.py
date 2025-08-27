import msgspec
from typing import Dict, List
from decimal import Decimal

from nexustrader.error import PositionModeError

from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.base import OrderManagementSystem
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.cache import AsyncCache
from nexustrader.schema import (
    Order,
    Position,
    BatchOrderSubmit,
)
from nexustrader.constants import (
    OrderSide,
    OrderStatus,
    ExchangeType,
    OrderType,
    TimeInForce,
    PositionSide,
    TriggerType,
)
from nexustrader.exchange.bybit.schema import (
    BybitWsMessageGeneral,
    BybitWsApiGeneralMsg,
    BybitWsOrderMsg,
    BybitMarket,
    BybitWsPositionMsg,
    BybitWsAccountWalletMsg,
    BybitWalletBalanceResponse,
    BybitPositionStruct,
    BybitWsApiOrderMsg,
)
from nexustrader.exchange.bybit.rest_api import BybitApiClient
from nexustrader.exchange.bybit.websockets import BybitWSClient, BybitWSApiClient
from nexustrader.exchange.bybit.constants import (
    BybitAccountType,
    BybitEnumParser,
    BybitProductType,
    BybitOrderType,
    BybitTimeInForce,
)


class BybitOrderManagementSystem(OrderManagementSystem):
    _ws_client: BybitWSClient
    _account_type: BybitAccountType
    _market: Dict[str, BybitMarket]
    _market_id: Dict[str, str]
    _api_client: BybitApiClient

    def __init__(
        self,
        account_type: BybitAccountType,
        api_key: str,
        secret: str,
        market: Dict[str, BybitMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: BybitApiClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=BybitWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
                api_key=api_key,
                secret=secret,
            ),
            exchange_id=exchange_id,
            clock=clock,
            msgbus=msgbus,
        )

        self._ws_api_client = BybitWSApiClient(
            account_type=account_type,
            api_key=api_key,
            secret=secret,
            handler=self._ws_api_msg_handler,
            task_manager=task_manager,
            clock=clock,
            enable_rate_limit=enable_rate_limit,
        )

        self._ws_api_msg_general_decoder = msgspec.json.Decoder(BybitWsApiGeneralMsg)
        self._ws_api_msg_order_decoder = msgspec.json.Decoder(BybitWsApiOrderMsg)
        self._ws_msg_general_decoder = msgspec.json.Decoder(BybitWsMessageGeneral)
        self._ws_msg_order_update_decoder = msgspec.json.Decoder(BybitWsOrderMsg)
        self._ws_msg_position_decoder = msgspec.json.Decoder(BybitWsPositionMsg)
        self._ws_msg_wallet_decoder = msgspec.json.Decoder(BybitWsAccountWalletMsg)

    def _parse_order_create(self, raw: bytes):
        msg = self._ws_api_msg_order_decoder.decode(raw)
        uuid = msg.uuid
        tmp_order = self._registry.get_tmp_order(uuid)
        symbol = tmp_order.symbol
        amount = tmp_order.amount
        type = tmp_order.type
        price = tmp_order.price
        side = tmp_order.side
        time_in_force = tmp_order.time_in_force
        reduce_only = tmp_order.reduce_only
        ts = self._clock.timestamp_ms()
        if msg.is_success:
            ordId = msg.data.orderId
            self._log.debug(f"[{symbol}] new order success: uuid: {uuid} id: {ordId}")
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                uuid=uuid,
                id=ordId,
                side=side,
                status=OrderStatus.PENDING,
                amount=amount,
                timestamp=ts,
                type=type,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
            self._cache._order_initialized(order)  # INITIALIZED -> PENDING
            self._msgbus.send(endpoint="pending", msg=order)
            self._registry.register_order(order)
        else:
            self._log.error(
                f"[{symbol}] new order failed: uuid: {uuid} {msg.error_msg}"
            )
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                uuid=uuid,
                status=OrderStatus.FAILED,
                amount=amount,
                timestamp=ts,
                side=side,
                type=type,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
            self._cache._order_status_update(order)  # INITIALIZED -> FAILED
            self._msgbus.send(endpoint="failed", msg=order)

    def _parse_order_cancel(self, raw: bytes):
        msg = self._ws_api_msg_order_decoder.decode(raw)
        uuid = msg.uuid
        tmp_order = self._registry.get_tmp_order(uuid)
        symbol = tmp_order.symbol
        amount = tmp_order.amount
        side = tmp_order.side
        type = tmp_order.type
        price = tmp_order.price
        time_in_force = tmp_order.time_in_force
        reduce_only = tmp_order.reduce_only
        ts = self._clock.timestamp_ms()
        if msg.is_success:
            ordId = msg.data.orderId
            self._log.debug(
                f"[{symbol}] canceling order success: uuid: {uuid} id: {ordId}"
            )
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                uuid=uuid,
                id=ordId,
                side=side,
                status=OrderStatus.CANCELING,
                amount=amount,
                type=type,
                price=price,
                time_in_force=time_in_force,
                timestamp=ts,
                reduce_only=reduce_only,
            )
            self._cache._order_status_update(order)  # SOME STATUS -> CANCELING
            self._msgbus.send(endpoint="canceling", msg=order)
        else:
            self._log.error(
                f"[{symbol}] canceling order failed: uuid: {uuid} {msg.error_msg}"
            )
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                uuid=uuid,
                status=OrderStatus.CANCEL_FAILED,
                amount=amount,
                side=side,
                type=type,
                price=price,
                time_in_force=time_in_force,
                timestamp=ts,
                reduce_only=reduce_only,
            )
            self._cache._order_status_update(order)  # SOME STATUS -> FAILED
            self._msgbus.send(endpoint="cancel_failed", msg=order)

    def _ws_api_msg_handler(self, raw: bytes):
        try:
            ws_msg = self._ws_api_msg_general_decoder.decode(raw)
            if ws_msg.is_pong:
                self._ws_api_client._transport.notify_user_specific_pong_received()
                self._log.debug(f"Pong received {str(ws_msg)}")
                return
            elif ws_msg.is_order_create:
                self._parse_order_create(raw)
            elif ws_msg.is_order_cancel:
                self._parse_order_cancel(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _ws_msg_handler(self, raw: bytes):
        try:
            ws_msg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.op == "pong":
                self._ws_client._transport.notify_user_specific_pong_received()
                self._log.debug(f"Pong received {str(ws_msg)}")
                return
            if ws_msg.success is False:
                self._log.error(f"WebSocket error: {ws_msg}")
                return
            if "order" in ws_msg.topic:
                self._parse_order_update(raw)
            elif "position" in ws_msg.topic:
                self._parse_position_update(raw)
            elif "wallet" == ws_msg.topic:
                self._parse_wallet_update(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _get_category(self, market: BybitMarket):
        if market.spot:
            return "spot"
        elif market.linear:
            return "linear"
        elif market.inverse:
            return "inverse"
        else:
            raise ValueError(f"Unsupported market type: {market.type}")

    async def cancel_order_ws(self, uuid: str, symbol: str, order_id: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id
        category = self._get_category(market)
        params = {
            "category": category,
            "symbol": id,
            "orderId": order_id,
            **kwargs,
        }

        await self._ws_api_client.cancel_order(id=uuid, **params)

    async def cancel_order(self, uuid: str, symbol: str, order_id: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id
        category = self._get_category(market)
        params = {
            "category": category,
            "symbol": id,
            "order_id": order_id,
            **kwargs,
        }
        try:
            res = await self._api_client.post_v5_order_cancel(**params)
            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                id=res.result.orderId,
                client_order_id=res.result.orderLinkId,
                timestamp=res.time,
                symbol=symbol,
                status=OrderStatus.CANCELING,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.CANCEL_FAILED,
            )
            return order

    def _init_account_balance(self):
        res: BybitWalletBalanceResponse = (
            self._api_client.get_v5_account_wallet_balance(account_type="UNIFIED")
        )
        for result in res.result.list:
            self._cache._apply_balance(self._account_type, result.parse_to_balances())

    def _get_all_positions_list(
        self, category: BybitProductType, settle_coin: str | None = None
    ) -> list[BybitPositionStruct]:
        all_positions = []
        next_page_cursor = ""

        while True:
            res = self._api_client.get_v5_position_list(
                category=category.value,
                settleCoin=settle_coin,
                limit=200,
                cursor=next_page_cursor,
            )

            all_positions.extend(res.result.list)

            # If there's no next page cursor, we've reached the end
            if not res.result.nextPageCursor:
                break

            next_page_cursor = res.result.nextPageCursor

        return all_positions

    def _init_position(self):
        res_linear_usdt = self._get_all_positions_list(
            BybitProductType.LINEAR, settle_coin="USDT"
        )
        res_linear_usdc = self._get_all_positions_list(
            BybitProductType.LINEAR, settle_coin="USDC"
        )
        res_inverse = self._get_all_positions_list(BybitProductType.INVERSE)

        self._apply_cache_position(res_linear_usdt, BybitProductType.LINEAR)
        self._apply_cache_position(res_linear_usdc, BybitProductType.LINEAR)
        self._apply_cache_position(res_inverse, BybitProductType.INVERSE)

        self._cache.get_all_positions()

    def _position_mode_check(self):
        # NOTE: no need to implement this for bybit, we do position mode check in _get_all_positions_list
        pass

    def _apply_cache_position(
        self, positions: list[BybitPositionStruct], category: BybitProductType
    ):
        for result in positions:
            side = result.side.parse_to_position_side()
            if side == PositionSide.FLAT:
                signed_amount = Decimal(0)
                side = None
            elif side == PositionSide.LONG:
                signed_amount = Decimal(result.size)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(result.size)

            if category.is_inverse:
                id = result.symbol + "_inverse"
            elif category.is_linear:
                id = result.symbol + "_linear"

            symbol = self._market_id[id]

            if not result.positionIdx.is_one_way_mode():
                raise PositionModeError(
                    f"Please Set Position Mode to `One-Way Mode` in Bybit App for {symbol}"
                )

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(result.avgPrice),
                unrealized_pnl=float(result.unrealisedPnl),
                realized_pnl=float(result.cumRealisedPnl),
            )
            self._cache._apply_position(position)

    async def create_tp_sl_order(
        self,
        uuid: str,
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
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        category = self._get_category(market)

        params = {
            "category": category,
            "symbol": id,
            "side": BybitEnumParser.to_bybit_order_side(side).value,
            "qty": str(amount),
        }

        if type.is_limit:
            if not price:
                raise ValueError("Price is required for limit order")
            params["price"] = str(price)
            params["order_type"] = BybitOrderType.LIMIT.value
            params["timeInForce"] = BybitEnumParser.to_bybit_time_in_force(
                time_in_force
            ).value
        elif type.is_post_only:
            if not price:
                raise ValueError("Price is required for post-only order")
            params["order_type"] = BybitOrderType.LIMIT.value
            params["price"] = str(price)
            params["timeInForce"] = BybitTimeInForce.POST_ONLY.value
        elif type == OrderType.MARKET:
            params["order_type"] = BybitOrderType.MARKET.value

        if market.spot:
            params["marketUnit"] = "baseCoin"

        if tp_order_type:
            params["takeProfit"] = str(tp_trigger_price)
            params["triggerBy"] = BybitEnumParser.to_bybit_trigger_type(
                tp_trigger_type
            ).value
            if tp_order_type.is_limit:
                if not tp_price:
                    raise ValueError("Price is required for limit take profit order")
                params["tpOrderType"] = BybitOrderType.LIMIT.value
                params["tpLimitPrice"] = str(tp_price)

        if sl_order_type:
            params["stopLoss"] = str(sl_trigger_price)
            params["triggerBy"] = BybitEnumParser.to_bybit_trigger_type(
                sl_trigger_type
            ).value
            if sl_order_type.is_limit:
                if not sl_price:
                    raise ValueError("Price is required for limit stop loss order")
                params["slOrderType"] = BybitOrderType.LIMIT.value
                params["slLimitPrice"] = str(sl_price)

        if not market.spot:
            tpslMode = kwargs.pop("tpslMode", "Partial")
            params["tpslMode"] = tpslMode

        params.update(kwargs)

        try:
            res = await self._api_client.post_v5_order_create(**params)

            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                uuid=uuid,
                client_order_id=res.result.orderLinkId,
                timestamp=int(res.time),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=False,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                uuid=uuid,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def create_batch_orders(self, orders: List[BatchOrderSubmit]):
        if not orders:
            raise ValueError("No orders provided for batch submission")

        # Get category from first order
        first_market = self._market.get(orders[0].symbol)
        if not first_market:
            raise ValueError(f"Symbol {orders[0].symbol} not found in market")
        category = self._get_category(first_market)

        batch_orders = []
        for order in orders:
            market = self._market.get(order.symbol)
            if not market:
                raise ValueError(f"Symbol {order.symbol} not found in market")
            id = market.id

            params = {
                "symbol": id,
                "side": BybitEnumParser.to_bybit_order_side(order.side).value,
                "qty": str(order.amount),
            }
            if order.type.is_limit:
                if not order.price:
                    raise ValueError("Price is required for limit order")
                params["orderType"] = BybitOrderType.LIMIT.value
                params["price"] = str(order.price)
                params["timeInForce"] = BybitEnumParser.to_bybit_time_in_force(
                    order.time_in_force
                ).value
            elif order.type.is_post_only:
                if not order.price:
                    raise ValueError("Price is required for limit order")
                params["orderType"] = BybitOrderType.LIMIT.value
                params["price"] = str(order.price)
                params["timeInForce"] = BybitTimeInForce.POST_ONLY.value
            elif order.type == OrderType.MARKET:
                params["orderType"] = BybitOrderType.MARKET.value

            if order.reduce_only:
                params["reduceOnly"] = True
            if market.spot:
                params["marketUnit"] = "baseCoin"
            params.update(order.kwargs)
            batch_orders.append(params)

        try:
            res = await self._api_client.post_v5_order_create_batch(
                category=category, request=batch_orders
            )
            res_batch_orders = []
            for order, res_order, res_ext in zip(
                orders, res.result.list, res.retExtInfo.list
            ):
                if res_ext.code == 0:
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        uuid=order.uuid,
                        id=res_order.orderId,
                        client_order_id=res_order.orderLinkId,
                        timestamp=int(res_order.createAt),
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price) if order.price else None,
                        time_in_force=order.time_in_force,
                        status=OrderStatus.PENDING,
                        filled=Decimal(0),
                        remaining=order.amount,
                        reduce_only=order.reduce_only,
                    )
                else:
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        symbol=order.symbol,
                        type=order.type,
                        uuid=order.uuid,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price) if order.price else None,
                        time_in_force=order.time_in_force,
                        status=OrderStatus.FAILED,
                        filled=Decimal(0),
                        remaining=order.amount,
                        reduce_only=order.reduce_only,
                    )
                    self._log.error(
                        f"Failed to place order for {order.symbol}: {res_ext.msg} code: {res_ext.code} {order.uuid}"
                    )
                res_batch_orders.append(res_batch_order)
            return res_batch_orders
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating batch orders: {error_msg}")
            res_batch_orders = [
                Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    symbol=order.symbol,
                    uuid=order.uuid,
                    type=order.type,
                    side=order.side,
                    amount=order.amount,
                    price=float(order.price) if order.price else None,
                    time_in_force=order.time_in_force,
                    status=OrderStatus.FAILED,
                    filled=Decimal(0),
                    remaining=order.amount,
                    reduce_only=order.reduce_only,
                )
                for order in orders
            ]
            return res_batch_orders

    async def create_order(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        # position_side: PositionSide | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        category = self._get_category(market)

        params = {
            "category": category,
            "symbol": id,
            "side": BybitEnumParser.to_bybit_order_side(side).value,
            "qty": str(amount),
        }

        if type.is_limit:
            if not price:
                raise ValueError("Price is required for limit order")
            params["price"] = str(price)
            params["order_type"] = BybitOrderType.LIMIT.value
            params["timeInForce"] = BybitEnumParser.to_bybit_time_in_force(
                time_in_force
            ).value
        elif type.is_post_only:
            if not price:
                raise ValueError("Price is required for post-only order")
            params["order_type"] = BybitOrderType.LIMIT.value
            params["price"] = str(price)
            params["timeInForce"] = BybitTimeInForce.POST_ONLY.value
        elif type == OrderType.MARKET:
            params["order_type"] = BybitOrderType.MARKET.value

        # if position_side:
        #     params["positionIdx"] = BybitEnumParser.to_bybit_position_side(
        #         position_side
        #     ).value
        if reduce_only:
            params["reduceOnly"] = True
        if market.spot:
            params["marketUnit"] = "baseCoin"

        params.update(kwargs)

        try:
            res = await self._api_client.post_v5_order_create(**params)

            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                uuid=uuid,
                client_order_id=res.result.orderLinkId,
                timestamp=int(res.time),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                # position_side=position_side,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=reduce_only,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                uuid=uuid,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                # position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=reduce_only,
            )
            return order

    async def create_order_ws(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        **kwargs,
    ):
        self._registry.register_tmp_order(
            order=Order(
                uuid=uuid,
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.INITIALIZED,
                amount=amount,
                type=type,
                side=side,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                timestamp=self._clock.timestamp_ms()
            )
        )
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        category = self._get_category(market)

        params = {
            "category": category,
            "symbol": id,
            "side": BybitEnumParser.to_bybit_order_side(side).value,
            "qty": str(amount),
        }

        if type.is_limit:
            if not price:
                raise ValueError("Price is required for limit order")
            params["price"] = str(price)
            params["orderType"] = BybitOrderType.LIMIT.value
            params["timeInForce"] = BybitEnumParser.to_bybit_time_in_force(
                time_in_force
            ).value
        elif type.is_post_only:
            if not price:
                raise ValueError("Price is required for post-only order")
            params["orderType"] = BybitOrderType.LIMIT.value
            params["price"] = str(price)
            params["timeInForce"] = BybitTimeInForce.POST_ONLY.value
        elif type == OrderType.MARKET:
            params["orderType"] = BybitOrderType.MARKET.value

        # if position_side:
        #     params["positionIdx"] = BybitEnumParser.to_bybit_position_side(
        #         position_side
        #     ).value
        if reduce_only:
            params["reduceOnly"] = True
        if market.spot:
            params["marketUnit"] = "baseCoin"

        params.update(kwargs)

        await self._ws_api_client.create_order(id=uuid, **params)

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id

            category = self._get_category(market)

            params = {
                "category": category,
                "symbol": symbol,
            }

            await self._api_client.post_v5_order_cancel_all(**params)
            return True
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(
                f"Error canceling all orders: {error_msg} params: {str(params)}"
            )
            return False

    async def modify_order(
        self,
        uuid: str,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ):
        # NOTE: side is not supported for modify order
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        category = self._get_category(market)
        params = {
            "category": category,
            "symbol": id,
            "orderId": order_id,
            "price": str(price) if price else None,
            "qty": str(amount) if amount else None,
            **kwargs,
        }

        try:
            res = await self._api_client.post_v5_order_amend(**params)
            order = Order(
                exchange=self._exchange_id,
                id=res.result.orderId,
                uuid=uuid,
                client_order_id=res.result.orderLinkId,
                timestamp=int(res.time),
                symbol=symbol,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                price=float(price) if price else None,
                remaining=amount,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                uuid=uuid,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
                price=float(price) if price else None,
            )
            return order

    def _parse_order_update(self, raw: bytes):
        order_msg = self._ws_msg_order_update_decoder.decode(raw)
        self._log.debug(f"Order update: {str(order_msg)}")
        for data in order_msg.data:
            category = data.category
            if category.is_spot:
                id = data.symbol + "_spot"
            elif category.is_linear:
                id = data.symbol + "_linear"
            elif category.is_inverse:
                id = data.symbol + "_inverse"
            symbol = self._market_id[id]

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=BybitEnumParser.parse_order_status(data.orderStatus),
                id=data.orderId,
                client_order_id=data.orderLinkId,
                timestamp=int(data.updatedTime),
                type=BybitEnumParser.parse_order_type(data.orderType, data.timeInForce),
                side=BybitEnumParser.parse_order_side(data.side),
                time_in_force=BybitEnumParser.parse_time_in_force(data.timeInForce),
                price=float(data.price),
                average=float(data.avgPrice) if data.avgPrice else None,
                amount=Decimal(data.qty),
                filled=Decimal(data.cumExecQty),
                remaining=Decimal(data.qty)
                - Decimal(
                    data.cumExecQty
                ),  # TODO: check if this is correct leavsQty is not correct
                fee=Decimal(data.cumExecFee),
                fee_currency=data.feeCurrency,
                cum_cost=Decimal(data.cumExecValue),
                reduce_only=data.reduceOnly,
                position_side=BybitEnumParser.parse_position_side(data.positionIdx),
            )

            self.order_submit(order)

    def _parse_position_update(self, raw: bytes):
        position_msg = self._ws_msg_position_decoder.decode(raw)
        self._log.debug(f"Position update: {str(position_msg)}")

        for data in position_msg.data:
            category = data.category
            if category.is_linear:  # only linear/inverse/ position is supported
                id = data.symbol + "_linear"
            elif category.is_inverse:
                id = data.symbol + "_inverse"
            symbol = self._market_id[id]

            side = data.side.parse_to_position_side()
            if side == PositionSide.LONG:
                signed_amount = Decimal(data.size)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.size)
            else:
                side = None
                signed_amount = Decimal(0)

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(data.entryPrice),
                unrealized_pnl=float(data.unrealisedPnl),
                realized_pnl=float(data.cumRealisedPnl),
            )

            self._cache._apply_position(position)

    def _parse_wallet_update(self, raw: bytes):
        wallet_msg = self._ws_msg_wallet_decoder.decode(raw)
        self._log.debug(f"Wallet update: {str(wallet_msg)}")

        for data in wallet_msg.data:
            balances = data.parse_to_balances()
            self._cache._apply_balance(self._account_type, balances)

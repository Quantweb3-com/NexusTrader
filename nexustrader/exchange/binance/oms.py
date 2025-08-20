import msgspec
import asyncio
from decimal import Decimal

from typing import Dict, Any
from nexustrader.constants import (
    PositionSide,
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    TriggerType,
)
from nexustrader.schema import Order, Position, BatchOrderSubmit
from nexustrader.base import OrderManagementSystem
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.entity import TaskManager
from nexustrader.error import PositionModeError
from nexustrader.exchange.binance.schema import (
    BinanceMarket,
    BinanceFuturesPositionInfo,
    BinancePortfolioMarginPositionRisk,
)
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceOrderType,
    BinanceTimeInForce,
)
from nexustrader.exchange.binance.rest_api import BinanceApiClient
from nexustrader.exchange.binance.websockets import BinanceWSClient, BinanceWSApiClient
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.exchange.binance.constants import (
    BinanceUserDataStreamWsEventType,
    BinanceBusinessUnit,
    BinanceEnumParser,
)
from nexustrader.exchange.binance.schema import (
    BinanceUserDataStreamMsg,
    BinanceSpotOrderUpdateMsg,
    BinanceFuturesOrderUpdateMsg,
    BinanceSpotAccountInfo,
    BinanceFuturesAccountInfo,
    BinanceWsOrderResponse,
    BinanceSpotUpdateMsg,
    BinanceFuturesUpdateMsg,
    BinancePortfolioMarginBalance,
)
from nexustrader.core.cache import AsyncCache


class BinanceOrderManagementSystem(OrderManagementSystem):
    _account_type: BinanceAccountType
    _market: Dict[str, BinanceMarket]
    _market_id: Dict[str, str]
    _api_client: BinanceApiClient
    _ws_client: BinanceWSClient

    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str,
        secret: str,
        market: Dict[str, BinanceMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: BinanceApiClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool,
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=BinanceWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                clock=clock,
            ),
            exchange_id=exchange_id,
            clock=clock,
            msgbus=msgbus,
        )
        self._ws_api_client = None
        if self._account_type.is_spot or self._account_type.is_future:
            self._ws_api_client = BinanceWSApiClient(
                account_type=account_type,
                api_key=api_key,
                secret=secret,
                handler=self._ws_api_msg_handler,
                task_manager=task_manager,
                clock=clock,
                enable_rate_limit=enable_rate_limit,
            )

        self._ws_msg_general_decoder = msgspec.json.Decoder(BinanceUserDataStreamMsg)
        self._ws_msg_spot_order_update_decoder = msgspec.json.Decoder(
            BinanceSpotOrderUpdateMsg
        )
        self._ws_msg_futures_order_update_decoder = msgspec.json.Decoder(
            BinanceFuturesOrderUpdateMsg
        )
        self._ws_msg_spot_account_update_decoder = msgspec.json.Decoder(
            BinanceSpotUpdateMsg
        )
        self._ws_msg_futures_account_update_decoder = msgspec.json.Decoder(
            BinanceFuturesUpdateMsg
        )
        self._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(
            BinanceWsOrderResponse
        )

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"

    def _ws_api_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_msg_ws_api_response_decoder.decode(raw)
            uuid = msg.id

            tmp_order = self._registry.get_tmp_order(uuid)

            if not self._registry.get_order_id(uuid):
                if msg.is_success:
                    sym_id = f"{msg.result.symbol}{self.market_type}"
                    symbol = self._market_id[sym_id]
                    self._log.debug(
                        f"[{symbol}] new order success: uuid: {uuid} id: {msg.result.orderId}"
                    )
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=symbol,
                        uuid=uuid,
                        id=str(msg.result.orderId),
                        status=OrderStatus.PENDING,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self._cache._order_initialized(order)  # INITIALIZED -> PENDING
                    self._msgbus.send(endpoint="pending", msg=order)
                    self._registry.register_order(order)
                else:
                    self._log.error(
                        f"[{symbol}] new order failed: uuid: {uuid} {msg.error.format_str}"
                    )
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        uuid=uuid,
                        status=OrderStatus.FAILED,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self._cache._order_status_update(order)  # INITIALIZED -> FAILED
                    self._msgbus.send(endpoint="failed", msg=order)
            else:
                if msg.is_success:
                    sym_id = f"{msg.result.symbol}{self.market_type}"
                    symbol = self._market_id[sym_id]
                    self._log.debug(
                        f"[{symbol}] new order success: uuid: {uuid} id: {msg.result.orderId}"
                    )
                    self._log.debug(
                        f"[{symbol}] canceling order success: uuid: {uuid} id: {msg.result.orderId}"
                    )
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=symbol,
                        uuid=uuid,
                        id=str(msg.result.orderId),
                        status=OrderStatus.CANCELING,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self._cache._order_status_update(order)  # SOME STATUS -> CANCELING
                    self._msgbus.send(endpoint="canceling", msg=order)
                else:
                    self._log.error(
                        f"[{tmp_order.symbol}] canceling order failed: uuid: {uuid} {msg.error.format_str}"
                    )
                    order = Order(
                        exchange=self._exchange_id,
                        symbol=tmp_order.symbol,
                        uuid=uuid,
                        status=OrderStatus.CANCEL_FAILED,
                        amount=tmp_order.amount,
                        type=tmp_order.type,
                        price=tmp_order.price,
                        time_in_force=tmp_order.time_in_force,
                        reduce_only=tmp_order.reduce_only,
                    )
                    self._cache._order_status_update(order)  # SOME STATUS -> FAILED
                    self._msgbus.send(endpoint="cancel_failed", msg=order)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding WebSocket API message: {str(raw)} {e}")

    def _ws_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_msg_general_decoder.decode(raw)
            if msg.e:
                match msg.e:
                    case (
                        BinanceUserDataStreamWsEventType.ORDER_TRADE_UPDATE
                    ):  # futures order update
                        self._parse_order_trade_update(raw)
                    case (
                        BinanceUserDataStreamWsEventType.EXECUTION_REPORT
                    ):  # spot order update
                        self._parse_execution_report(raw)
                    case (
                        BinanceUserDataStreamWsEventType.ACCOUNT_UPDATE
                    ):  # futures account update
                        self._parse_account_update(raw)
                    case (
                        BinanceUserDataStreamWsEventType.OUT_BOUND_ACCOUNT_POSITION
                    ):  # spot account update
                        self._parse_out_bound_account_position(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _parse_order_trade_update(self, raw: bytes) -> Order:
        res = self._ws_msg_futures_order_update_decoder.decode(raw)
        self._log.debug(f"Order trade update: {res}")

        event_data = res.o
        event_unit = res.fs

        # Only portfolio margin has "UM" and "CM" event business unit
        if event_unit == BinanceBusinessUnit.UM:
            id = event_data.s + "_linear"
            symbol = self._market_id[id]
        elif event_unit == BinanceBusinessUnit.CM:
            id = event_data.s + "_inverse"
            symbol = self._market_id[id]
        else:
            id = event_data.s + self.market_type
            symbol = self._market_id[id]

        # we use the last filled quantity to calculate the cost, instead of the accumulated filled quantity
        type = event_data.o
        if type.is_market:
            cost = Decimal(event_data.l) * Decimal(event_data.ap)
            cum_cost = Decimal(event_data.z) * Decimal(event_data.ap)
        elif type.is_limit:
            price = Decimal(event_data.ap) or Decimal(
                event_data.p
            )  # if average price is 0 or empty, use price
            cost = Decimal(event_data.l) * price
            cum_cost = Decimal(event_data.z) * price

        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            status=BinanceEnumParser.parse_order_status(event_data.X),
            id=str(event_data.i),
            amount=Decimal(event_data.q),
            filled=Decimal(event_data.z),
            client_order_id=event_data.c,
            timestamp=res.E,
            type=BinanceEnumParser.parse_futures_order_type(event_data.o, event_data.f),
            side=BinanceEnumParser.parse_order_side(event_data.S),
            time_in_force=BinanceEnumParser.parse_time_in_force(event_data.f),
            price=float(event_data.p),
            average=float(event_data.ap),
            last_filled_price=float(event_data.L),
            last_filled=float(event_data.l),
            remaining=Decimal(event_data.q) - Decimal(event_data.z),
            fee=Decimal(event_data.n),
            fee_currency=event_data.N,
            cum_cost=cum_cost,
            cost=cost,
            reduce_only=event_data.R,
            position_side=BinanceEnumParser.parse_position_side(event_data.ps),
        )

        self.order_submit(order)

    def _parse_execution_report(self, raw: bytes) -> Order:
        event_data = self._ws_msg_spot_order_update_decoder.decode(raw)
        self._log.debug(f"Execution report: {event_data}")

        market_type = self.market_type or "_spot"
        id = event_data.s + market_type
        symbol = self._market_id[id]

        # Calculate average price only if filled amount is non-zero
        average = (
            float(event_data.Z) / float(event_data.z)
            if float(event_data.z) != 0
            else None
        )

        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            status=BinanceEnumParser.parse_order_status(event_data.X),
            id=str(event_data.i),
            amount=Decimal(event_data.q),
            filled=Decimal(event_data.z),
            client_order_id=event_data.c,
            timestamp=event_data.E,
            type=BinanceEnumParser.parse_spot_order_type(event_data.o),
            side=BinanceEnumParser.parse_order_side(event_data.S),
            time_in_force=BinanceEnumParser.parse_time_in_force(event_data.f),
            price=float(event_data.p),
            average=average,
            last_filled_price=float(event_data.L),
            last_filled=float(event_data.l),
            remaining=Decimal(event_data.q) - Decimal(event_data.z),
            fee=Decimal(event_data.n),
            fee_currency=event_data.N,
            cum_cost=Decimal(event_data.Z),
            cost=Decimal(event_data.Y),
        )

        self.order_submit(order)

    def _parse_account_update(self, raw: bytes):
        res = self._ws_msg_futures_account_update_decoder.decode(raw)
        self._log.debug(f"Account update: {res}")

        balances = res.a.parse_to_balances()
        self._cache._apply_balance(account_type=self._account_type, balances=balances)

        event_unit = res.fs
        for position in res.a.P:
            if event_unit == BinanceBusinessUnit.UM:
                id = position.s + "_linear"
                symbol = self._market_id[id]
            elif event_unit == BinanceBusinessUnit.CM:
                id = position.s + "_inverse"
                symbol = self._market_id[id]
            else:
                id = position.s + self.market_type
                symbol = self._market_id[id]

            signed_amount = Decimal(position.pa)
            side = position.ps.parse_to_position_side()
            if signed_amount == 0:
                side = None  # 0 means no position side
            else:
                if side == PositionSide.FLAT:
                    if signed_amount > 0:
                        side = PositionSide.LONG
                    elif signed_amount < 0:
                        side = PositionSide.SHORT
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                side=side,
                entry_price=float(position.ep),
                unrealized_pnl=float(position.up),
                realized_pnl=float(position.cr),
            )
            self._cache._apply_position(position)

    def _parse_out_bound_account_position(self, raw: bytes):
        res = self._ws_msg_spot_account_update_decoder.decode(raw)
        self._log.debug(f"Out bound account position: {res}")

        balances = res.parse_to_balances()
        self._cache._apply_balance(account_type=self._account_type, balances=balances)

    async def _execute_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        """Execute order request based on account type and market.

        Args:
            market: BinanceMarket object
            symbol: Trading symbol
            params: Order parameters

        Returns:
            API response

        Raises:
            ValueError: If market type is not supported for the account type
        """
        if self._account_type.is_spot:
            if not market.spot:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_api_v3_order(**params)
        elif self._account_type.is_isolated_margin_or_margin:
            if not market.margin:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_sapi_v1_margin_order(**params)
        elif self._account_type.is_linear:
            if not market.linear:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_fapi_v1_order(**params)
        elif self._account_type.is_inverse:
            if not market.inverse:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_dapi_v1_order(**params)
        elif self._account_type.is_portfolio_margin:
            if market.margin:
                return await self._api_client.post_papi_v1_margin_order(**params)
            elif market.linear:
                return await self._api_client.post_papi_v1_um_order(**params)
            elif market.inverse:
                return await self._api_client.post_papi_v1_cm_order(**params)

    async def _execute_modify_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._account_type.is_spot_or_margin:
            raise ValueError(
                "Modify order is not supported for `spot` or `margin` account"
            )

        elif self._account_type.is_linear:
            return await self._api_client.put_fapi_v1_order(**params)
        elif self._account_type.is_inverse:
            return await self._api_client.put_dapi_v1_order(**params)
        elif self._account_type.is_portfolio_margin:
            if market.inverse:
                return await self._api_client.put_papi_v1_cm_order(**params)
            elif market.linear:
                return await self._api_client.put_papi_v1_um_order(**params)
            else:
                raise ValueError(f"Modify order is not supported for {symbol}")

    async def _execute_cancel_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._account_type.is_spot:
            if not market.spot:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_api_v3_order(**params)
        elif self._account_type.is_isolated_margin_or_margin:
            if not market.margin:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_sapi_v1_margin_order(**params)
        elif self._account_type.is_linear:
            if not market.linear:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_fapi_v1_order(**params)
        elif self._account_type.is_inverse:
            if not market.inverse:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_dapi_v1_order(**params)
        elif self._account_type.is_portfolio_margin:
            if market.margin:
                return await self._api_client.delete_papi_v1_margin_order(**params)
            elif market.linear:
                return await self._api_client.delete_papi_v1_um_order(**params)
            elif market.inverse:
                return await self._api_client.delete_papi_v1_cm_order(**params)

    async def _execute_cancel_all_orders_request(
        self, market: BinanceMarket, params: Dict[str, Any]
    ):
        if self._account_type.is_spot:
            await self._api_client.delete_api_v3_open_orders(**params)
        elif self._account_type.is_isolated_margin_or_margin:
            await self._api_client.delete_sapi_v1_margin_open_orders(**params)
        elif self._account_type.is_linear:
            await self._api_client.delete_fapi_v1_all_open_orders(**params)
        elif self._account_type.is_inverse:
            await self._api_client.delete_dapi_v1_all_open_orders(**params)
        elif self._account_type.is_portfolio_margin:
            if market.margin:
                await self._api_client.delete_papi_v1_margin_all_open_orders(**params)
            elif market.linear:
                await self._api_client.delete_papi_v1_um_all_open_orders(**params)
            elif market.inverse:
                await self._api_client.delete_papi_v1_cm_all_open_orders(**params)

    async def _execute_batch_order_request(self, batch_orders: list[Dict[str, Any]]):
        if self._account_type.is_linear:
            return await self._api_client.post_fapi_v1_batch_orders(
                batch_orders=batch_orders
            )
        elif self._account_type.is_inverse:
            return await self._api_client.post_dapi_v1_batch_orders(
                batch_orders=batch_orders
            )
        else:
            raise ValueError(
                f"Batch order is not supported for {self._account_type.value} account type"
            )

    async def _execute_order_request_ws(
        self, uuid: str, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._ws_api_client is None:
            raise ValueError(
                f"`create_order_ws` is not supported for {self._account_type.value} account type"
            )

        if market.spot:
            await self._ws_api_client.spot_new_order(id=uuid, **params)
        elif market.linear:
            await self._ws_api_client.usdm_new_order(id=uuid, **params)
        else:
            await self._ws_api_client.coinm_new_order(id=uuid, **params)

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
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
        )
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "quantity": amount,
        }

        if type.is_post_only:
            if market.spot:
                params["type"] = BinanceOrderType.LIMIT_MAKER.value
            else:
                params["type"] = BinanceOrderType.LIMIT.value
                params["timeInForce"] = (
                    BinanceTimeInForce.GTX.value
                )  # for future, you need to set ordertype to LIMIT and timeinforce to GTX to place a post only order
        else:
            params["type"] = BinanceEnumParser.to_binance_order_type(type).value

        if type.is_limit or type.is_post_only:
            if not price:
                raise ValueError("Price is required for order")
            params["price"] = price

        if type.is_limit:
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if reduce_only:
            params["reduceOnly"] = "true"

        params.update(kwargs)
        await self._execute_order_request_ws(
            uuid=uuid, market=market, symbol=symbol, params=params
        )

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
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "quantity": amount,
        }

        if type.is_post_only:
            if market.spot:
                params["type"] = BinanceOrderType.LIMIT_MAKER.value
            else:
                params["type"] = BinanceOrderType.LIMIT.value
                params["timeInForce"] = (
                    BinanceTimeInForce.GTX.value
                )  # for future, you need to set ordertype to LIMIT and timeinforce to GTX to place a post only order
        else:
            params["type"] = BinanceEnumParser.to_binance_order_type(type).value

        if type.is_limit or type.is_post_only:
            if not price:
                raise ValueError("Price is required for order")
            params["price"] = price

        if type.is_limit:
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if reduce_only:
            params["reduceOnly"] = "true"

        params.update(kwargs)

        try:
            res = await self._execute_order_request(market, symbol, params)
            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                amount=amount,
                filled=Decimal(0),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                remaining=amount,
                reduce_only=reduce_only,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
                reduce_only=reduce_only,
            )
            return order

    async def _execute_cancel_order_request_ws(
        self, uuid: str, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._ws_api_client is None:
            raise ValueError(
                f"`create_order_ws` is not supported for {self._account_type.value} account type"
            )

        if market.spot:
            await self._ws_api_client.spot_cancel_order(id=uuid, **params)
        elif market.linear:
            await self._ws_api_client.usdm_cancel_order(id=uuid, **params)
        else:
            await self._ws_api_client.coinm_cancel_order(id=uuid, **params)

    async def cancel_order_ws(self, uuid: str, symbol: str, order_id: int, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id
        params = {
            "symbol": id,
            "orderId": order_id,
            **kwargs,
        }
        await self._execute_cancel_order_request_ws(
            uuid, market, symbol, params
        )

    async def cancel_order(self, uuid: str, symbol: str, order_id: int, **kwargs):
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            id = market.id

            params = {
                "symbol": id,
                "order_id": order_id,
                **kwargs,
            }

            res = await self._execute_cancel_order_request(market, symbol, params)

            if market.spot:
                type = BinanceEnumParser.parse_spot_order_type(res.type)
            else:
                type = BinanceEnumParser.parse_futures_order_type(
                    res.type, res.timeInForce
                )

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.CANCELING,
                id=str(res.orderId),
                uuid=uuid,
                amount=res.origQty,
                filled=Decimal(res.executedQty),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=BinanceEnumParser.parse_order_side(res.side),
                time_in_force=BinanceEnumParser.parse_time_in_force(res.timeInForce),
                price=res.price,
                average=res.avgPrice,
                remaining=Decimal(res.origQty) - Decimal(res.executedQty),
                reduce_only=res.reduceOnly,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                id=str(order_id),
                uuid=uuid,
                status=OrderStatus.FAILED,
            )
            return order

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id

            params = {
                "symbol": symbol,
            }
            await self._execute_cancel_all_orders_request(market, params)
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
        order_id: int,
        side: OrderSide,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        if market.spot:
            raise ValueError(
                "Modify order is not supported for `spot` account type, please cancel and create a new order"
            )

        params = {
            "symbol": id,
            "orderId": order_id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "quantity": str(amount) if amount else None,
            "price": str(price) if price else None,
            **kwargs,
        }

        try:
            res = await self._execute_modify_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                uuid=uuid,
                amount=amount,
                filled=Decimal(res.executedQty),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=BinanceEnumParser.parse_futures_order_type(
                    res.type, res.timeInForce
                ),
                side=side,
                time_in_force=BinanceEnumParser.parse_time_in_force(res.timeInForce),
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                remaining=Decimal(res.origQty) - Decimal(res.executedQty),
                reduce_only=res.reduceOnly,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                uuid=uuid,
                symbol=symbol,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                status=OrderStatus.FAILED,
                filled=Decimal("0"),
                remaining=amount,
            )
            return order

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
        tasks = []
        tasks.append(
            self.create_order(
                uuid=uuid,
                symbol=symbol,
                side=side,
                type=type,
                amount=amount,
                price=price,
                time_in_force=time_in_force,
                **kwargs,
            )
        )
        tp_sl_side = OrderSide.SELL if side.is_buy else OrderSide.BUY
        if tp_order_type and tp_trigger_price:
            tasks.append(
                self._create_take_profit_order(
                    uuid=uuid,
                    symbol=symbol,
                    side=tp_sl_side,
                    type=tp_order_type,
                    amount=amount,
                    trigger_price=tp_trigger_price,
                    price=tp_price,
                    trigger_type=tp_trigger_type,
                )
            )
        if sl_order_type and sl_trigger_price:
            tasks.append(
                self._create_stop_loss_order(
                    uuid=uuid,
                    symbol=symbol,
                    side=tp_sl_side,
                    type=sl_order_type,
                    amount=amount,
                    trigger_price=sl_trigger_price,
                    price=sl_price,
                    trigger_type=sl_trigger_type,
                )
            )
        res = await asyncio.gather(*tasks)
        return res[0]

    async def _create_stop_loss_order(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        id = market.id

        if market.inverse or market.linear:
            binance_type = (
                BinanceOrderType.STOP if type.is_limit else BinanceOrderType.STOP_MARKET
            )
        elif market.spot:
            binance_type = (
                BinanceOrderType.STOP_LOSS_LIMIT
                if type.is_limit
                else BinanceOrderType.STOP_LOSS
            )
        elif market.margin:
            # TODO: margin order is not supported yet
            pass

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "type": binance_type.value,
            "quantity": amount,
            "stopPrice": trigger_price,
            "workingType": BinanceEnumParser.to_binance_trigger_type(
                trigger_type
            ).value,
        }

        if type.is_limit:
            if price is None:
                raise ValueError("Price must be provided for limit stop loss orders")

            params["price"] = price
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if position_side:
            params["positionSide"] = BinanceEnumParser.to_binance_position_side(
                position_side
            ).value

        params.update(kwargs)

        try:
            res = await self._execute_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                uuid=uuid,
                amount=amount,
                filled=Decimal(0),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                trigger_price=float(res.stopPrice),
                remaining=amount,
                reduce_only=res.reduceOnly if res.reduceOnly else None,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
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
                trigger_price=trigger_price,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def _create_take_profit_order(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        id = market.id

        if market.inverse or market.linear:
            binance_type = (
                BinanceOrderType.TAKE_PROFIT
                if type.is_limit
                else BinanceOrderType.TAKE_PROFIT_MARKET
            )
        elif market.spot:
            binance_type = (
                BinanceOrderType.TAKE_PROFIT_LIMIT
                if type.is_limit
                else BinanceOrderType.TAKE_PROFIT
            )
        elif market.margin:
            # TODO: margin order is not supported yet
            pass

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "type": binance_type.value,
            "quantity": amount,
            "stopPrice": trigger_price,
            "workingType": BinanceEnumParser.to_binance_trigger_type(
                trigger_type
            ).value,
        }

        if type.is_limit:
            if price is None:
                raise ValueError("Price must be provided for limit take profit orders")

            params["price"] = price
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if position_side:
            params["positionSide"] = BinanceEnumParser.to_binance_position_side(
                position_side
            ).value

        params.update(kwargs)

        try:
            res = await self._execute_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                uuid=uuid,
                id=str(res.orderId),
                amount=amount,
                filled=Decimal(0),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                trigger_price=float(res.stopPrice),
                remaining=amount,
                reduce_only=res.reduceOnly if res.reduceOnly else None,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
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
                trigger_price=trigger_price,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def create_batch_orders(self, orders: list[BatchOrderSubmit]):
        if self._account_type.is_portfolio_margin:
            tasks = [
                self.create_order(
                    uuid=order.uuid,
                    symbol=order.symbol,
                    side=order.side,
                    amount=order.amount,
                    price=order.price,
                    type=order.type,
                    time_in_force=order.time_in_force,
                    reduce_only=order.reduce_only,
                    **order.kwargs,
                )
                for order in orders
            ]
            res = await asyncio.gather(*tasks)

            res_batch_orders = []
            for order, res_order in zip(orders, res):
                res_order.uuid = order.uuid
                res_batch_orders.append(res_order)
            return res_batch_orders

        else:
            batch_orders = []
            for order in orders:
                market = self._market.get(order.symbol)
                if not market:
                    raise ValueError(
                        f"Symbol {order.symbol} formated wrongly, or not supported"
                    )
                id = market.id

                params = {
                    "symbol": id,
                    "side": BinanceEnumParser.to_binance_order_side(order.side).value,
                    "quantity": str(order.amount),
                }

                if order.type.is_post_only:
                    if market.spot:
                        params["type"] = BinanceOrderType.LIMIT_MAKER.value
                    else:
                        params["type"] = BinanceOrderType.LIMIT.value
                        params["timeInForce"] = BinanceTimeInForce.GTX.value
                else:
                    params["type"] = BinanceEnumParser.to_binance_order_type(
                        order.type
                    ).value

                if order.type.is_limit or order.type.is_post_only:
                    if not order.price:
                        raise ValueError("Price is required for limit order")

                    params["price"] = str(order.price)

                if order.type.is_limit:
                    params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                        order.time_in_force
                    ).value

                if order.reduce_only:
                    params["reduceOnly"] = "true"

                params.update(order.kwargs)
                batch_orders.append(params)
            try:
                res = await self._execute_batch_order_request(batch_orders)
                res_batch_orders = []
                for order, res_order in zip(orders, res):
                    if not res_order.code:
                        res_batch_order = Order(
                            exchange=self._exchange_id,
                            symbol=order.symbol,
                            status=OrderStatus.PENDING,
                            id=str(res_order.orderId),
                            uuid=order.uuid,
                            amount=order.amount,
                            filled=Decimal(0),
                            client_order_id=res_order.clientOrderId,
                            timestamp=res_order.updateTime,
                            type=order.type,
                            side=order.side,
                            time_in_force=order.time_in_force,
                            price=float(order.price) if order.price else None,
                            average=float(res_order.avgPrice)
                            if res_order.avgPrice
                            else None,
                            remaining=order.amount,
                            reduce_only=order.reduce_only,
                            position_side=BinanceEnumParser.parse_position_side(
                                res_order.positionSide
                            )
                            if res_order.positionSide
                            else None,
                        )
                    else:
                        res_batch_order = Order(
                            exchange=self._exchange_id,
                            timestamp=self._clock.timestamp_ms(),
                            uuid=order.uuid,
                            symbol=order.symbol,
                            type=order.type,
                            side=order.side,
                            amount=order.amount,
                            price=float(order.price) if order.price else None,
                            time_in_force=order.time_in_force,
                            status=OrderStatus.FAILED,
                            filled=Decimal(0),
                            reduce_only=order.reduce_only,
                            remaining=order.amount,
                        )
                        self._log.error(
                            f"Failed to place order for {order.symbol}: {res_order.msg}: id: {order.uuid}"
                        )
                    res_batch_orders.append(res_batch_order)
                return res_batch_orders

            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(f"Error placing batch orders: {error_msg}")
                res_batch_orders = []
                for order in orders:
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        uuid=order.uuid,
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price) if order.price else None,
                        time_in_force=order.time_in_force,
                        status=OrderStatus.FAILED,
                        filled=Decimal(0),
                        remaining=order.amount,
                    )
                    res_batch_orders.append(res_batch_order)
                return res_batch_orders

    def _apply_position(
        self,
        pos: BinanceFuturesPositionInfo | BinancePortfolioMarginPositionRisk,
        market_type: str | None = None,
    ):
        market_type = market_type or self.market_type
        id = pos.symbol + market_type
        symbol = self._market_id.get(id)
        side = pos.positionSide.parse_to_position_side()
        signed_amount = Decimal(pos.positionAmt)

        if not symbol:
            return

        if signed_amount == 0:
            side = None
        else:
            if side == PositionSide.FLAT:
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT

        if isinstance(pos, BinancePortfolioMarginPositionRisk):
            unrealized_pnl = float(pos.unRealizedProfit)
        elif isinstance(pos, BinanceFuturesPositionInfo):
            unrealized_pnl = float(pos.unrealizedProfit)

        position = Position(
            symbol=symbol,
            exchange=self._exchange_id,
            signed_amount=signed_amount,
            side=side,
            entry_price=float(pos.entryPrice),
            unrealized_pnl=unrealized_pnl,
        )
        if position.is_opened:
            self._cache._apply_position(position)

    def _init_account_balance(self):
        if (
            self._account_type.is_spot
            or self._account_type.is_isolated_margin_or_margin
        ):
            res: BinanceSpotAccountInfo = self._api_client.get_api_v3_account()
        elif self._account_type.is_linear:
            res: BinanceFuturesAccountInfo = self._api_client.get_fapi_v2_account()
        elif self._account_type.is_inverse:
            res: BinanceFuturesAccountInfo = self._api_client.get_dapi_v1_account()

        if self._account_type.is_portfolio_margin:
            balances = []
            res_pm: list[BinancePortfolioMarginBalance] = (
                self._api_client.get_papi_v1_balance()
            )
            for balance in res_pm:
                balances.append(balance.parse_to_balance())
        else:
            balances = res.parse_to_balances()

        self._cache._apply_balance(self._account_type, balances)

        if self._account_type.is_linear or self._account_type.is_inverse:
            for pos in res.positions:
                self._apply_position(pos)

    def _init_position(self):
        # NOTE: Implement in `_init_account_balance`, only portfolio margin need to implement this
        if self._account_type.is_portfolio_margin:
            res_linear: list[BinancePortfolioMarginPositionRisk] = (
                self._api_client.get_papi_v1_um_position_risk()
            )
            res_inverse: list[BinancePortfolioMarginPositionRisk] = (
                self._api_client.get_papi_v1_cm_position_risk()
            )

            for pos in res_linear:
                self._apply_position(pos, market_type="_linear")
            for pos in res_inverse:
                self._apply_position(pos, market_type="_inverse")

    def _position_mode_check(self):
        error_msg = "Please Set Position Mode to `One-Way Mode` in Binance App"

        if self._account_type.is_linear:
            res = self._api_client.get_fapi_v1_positionSide_dual()
            if res["dualSidePosition"]:
                raise PositionModeError(error_msg)

        elif self._account_type.is_inverse:
            res = self._api_client.get_dapi_v1_positionSide_dual()
            if res["dualSidePosition"]:
                raise PositionModeError(error_msg)

        elif self._account_type.is_portfolio_margin:
            res_linear = self._api_client.get_papi_v1_um_positionSide_dual()
            res_inverse = self._api_client.get_papi_v1_cm_positionSide_dual()

            if res_linear["dualSidePosition"]:
                raise PositionModeError(
                    "Please Set Position Mode to `One-Way Mode` in Binance App for USD-M Future"
                )

            if res_inverse["dualSidePosition"]:
                raise PositionModeError(
                    "Please Set Position Mode to `One-Way Mode` in Binance App for Coin-M Future"
                )

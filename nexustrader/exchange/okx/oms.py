import msgspec
import warnings
from typing import Dict, List
from decimal import Decimal
from nexustrader.error import PositionModeError
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.exchange.okx.websockets import OkxWSClient, OkxWSApiClient
from nexustrader.exchange.okx.schema import OkxWsGeneralMsg
from nexustrader.schema import (
    Order,
    Position,
    BatchOrderSubmit,
)
from nexustrader.exchange.okx.schema import (
    OkxMarket,
    OkxWsOrderMsg,
    OkxWsPositionMsg,
    OkxWsAccountMsg,
    OkxBalanceResponse,
    OkxOrderResponse,
    OkxPositionResponse,
    OkxWsApiOrderResponse,
)
from nexustrader.constants import (
    OrderStatus,
    TimeInForce,
    ExchangeType,
    PositionSide,
    TriggerType,
)
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.exchange.okx.rest_api import OkxApiClient
from nexustrader.constants import OrderSide, OrderType
from nexustrader.exchange.okx.constants import (
    OkxTdMode,
    OkxEnumParser,
)
from nexustrader.base import OrderManagementSystem
from nexustrader.core.registry import OrderRegistry


class OkxOrderManagementSystem(OrderManagementSystem):
    _ws_client: OkxWSClient
    _account_type: OkxAccountType
    _market: Dict[str, OkxMarket]
    _market_id: Dict[str, str]
    _api_client: OkxApiClient

    def __init__(
        self,
        account_type: OkxAccountType,
        api_key: str,
        secret: str,
        passphrase: str,
        market: Dict[str, OkxMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: OkxApiClient,
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
            ws_client=OkxWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                clock=clock,
                task_manager=task_manager,
                api_key=api_key,
                secret=secret,
                passphrase=passphrase,
            ),
            exchange_id=exchange_id,
            clock=clock,
            msgbus=msgbus,
        )

        self._ws_api_client = OkxWSApiClient(
            account_type=account_type,
            api_key=api_key,
            secret=secret,
            passphrase=passphrase,
            handler=self._ws_api_msg_handler,
            task_manager=task_manager,
            clock=clock,
            enable_rate_limit=enable_rate_limit,
        )

        self._decoder_ws_general_msg = msgspec.json.Decoder(OkxWsGeneralMsg)
        self._decoder_ws_order_msg = msgspec.json.Decoder(OkxWsOrderMsg, strict=False)
        self._decoder_ws_position_msg = msgspec.json.Decoder(
            OkxWsPositionMsg, strict=False
        )
        self._decoder_ws_account_msg = msgspec.json.Decoder(
            OkxWsAccountMsg, strict=False
        )
        self._ws_msg_ws_api_response_decoder = msgspec.json.Decoder(
            OkxWsApiOrderResponse
        )

    def _ws_api_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_api_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: {str(raw)}")
            return
        try:
            ws_msg: OkxWsGeneralMsg = self._decoder_ws_general_msg.decode(raw)
            if ws_msg.is_event_msg:
                self._handle_event_msg(ws_msg)
            else:
                msg = self._ws_msg_ws_api_response_decoder.decode(raw)
                uuid = msg.id

                tmp_order = self._registry.get_tmp_order(uuid)
                symbol = tmp_order.symbol
                amount = tmp_order.amount
                type = tmp_order.type
                side = tmp_order.side
                price = tmp_order.price
                time_in_force = tmp_order.time_in_force
                reduce_only = tmp_order.reduce_only
                ts = self._clock.timestamp_ms()
                if msg.op.is_place_order:
                    if msg.is_success:
                        ordId = msg.data[0].ordId
                        self._log.debug(
                            f"[{symbol}] new order success: uuid: {uuid} id: {ordId}"
                        )
                        order = Order(
                            exchange=self._exchange_id,
                            symbol=symbol,
                            uuid=uuid,
                            id=ordId,
                            status=OrderStatus.PENDING,
                            amount=amount,
                            type=type,
                            side=side,
                            price=price,
                            time_in_force=time_in_force,
                            reduce_only=reduce_only,
                            timestamp=ts,
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
                            side=side,
                            type=type,
                            price=price,
                            timestamp=ts,
                            time_in_force=time_in_force,
                            reduce_only=reduce_only,
                        )
                        self._cache._order_status_update(order)  # INITIALIZED -> FAILED
                        self._msgbus.send(endpoint="failed", msg=order)
                elif msg.op.is_cancel_order:
                    if msg.is_success:
                        ordId = msg.data[0].ordId
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
                            timestamp=ts,
                            time_in_force=time_in_force,
                            reduce_only=reduce_only,
                        )
                        self._cache._order_status_update(order)  # SOME STATUS -> FAILED
                        self._msgbus.send(endpoint="cancel_failed", msg=order)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding WebSocket API message: {str(raw)} {e}")

    def _position_mode_check(self):
        res = self._api_client.get_api_v5_account_config()
        for data in res.data:
            if not data.posMode.is_one_way_mode:
                raise PositionModeError(
                    "Please Set Position Mode to `One-Way Mode` in OKX App"
                )
            if data.acctLv.is_portfolio_margin:
                warnings.warn(
                    "For Portfolio Margin Account, `Reduce Only` is not supported"
                )
            self._acctLv = data.acctLv

    def _init_account_balance(self):
        res: OkxBalanceResponse = self._api_client.get_api_v5_account_balance()
        for data in res.data:
            self._cache._apply_balance(self._account_type, data.parse_to_balances())

    def _init_position(self):
        res: OkxPositionResponse = self._api_client.get_api_v5_account_positions()
        for data in res.data:
            side = data.posSide.parse_to_position_side()
            if side == PositionSide.FLAT:
                signed_amount = Decimal(data.pos)
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT
                else:
                    side = None
            elif side == PositionSide.LONG:
                signed_amount = Decimal(data.pos)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.pos)

            symbol = self._market_id.get(data.instId)
            if not symbol:
                warnings.warn(f"Symbol {data.instId} not found in market")
                continue
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=float(data.avgPx) if data.avgPx else 0,
                unrealized_pnl=float(data.upl) if data.upl else 0,
                realized_pnl=float(data.realizedPnl) if data.realizedPnl else 0,
            )
            self._cache._apply_position(position)

    def _handle_event_msg(self, msg: OkxWsGeneralMsg):
        if msg.event == "error":
            self._log.error(msg.error_msg)
        elif msg.event == "login":
            self._log.debug(msg.login_msg)
        elif msg.event == "subscribe":
            self._log.debug(f"Subscribed to {msg.subscribe_msg}")

    def _ws_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: {str(raw)}")
            return
        try:
            ws_msg: OkxWsGeneralMsg = self._decoder_ws_general_msg.decode(raw)
            if ws_msg.is_event_msg:
                self._handle_event_msg(ws_msg)
            else:
                channel = ws_msg.arg.channel
                if channel == "orders":
                    self._handle_orders(raw)
                elif channel == "positions":
                    self._handle_positions(raw)
                elif channel == "account":
                    self._handle_account(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_orders(self, raw: bytes):
        msg: OkxWsOrderMsg = self._decoder_ws_order_msg.decode(raw)
        self._log.debug(f"Order update: {str(msg)}")
        for data in msg.data:
            symbol = self._market_id[data.instId]

            market = self._market[symbol]

            if not market.spot:
                ct_val = Decimal(market.info.ctVal)  # contract size
            else:
                ct_val = Decimal("1")

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OkxEnumParser.parse_order_status(data.state),
                id=data.ordId,
                amount=Decimal(data.sz) * ct_val,
                filled=Decimal(data.accFillSz) * ct_val,
                client_order_id=data.clOrdId,
                timestamp=data.uTime,
                type=OkxEnumParser.parse_order_type(data.ordType),
                side=OkxEnumParser.parse_order_side(data.side),
                time_in_force=OkxEnumParser.parse_time_in_force(data.ordType),
                price=float(data.px) if data.px else None,
                average=float(data.avgPx) if data.avgPx else None,
                last_filled_price=float(data.fillPx) if data.fillPx else None,
                last_filled=Decimal(data.fillSz) * ct_val
                if data.fillSz
                else Decimal(0),
                remaining=Decimal(data.sz) * ct_val - Decimal(data.accFillSz) * ct_val,
                fee=Decimal(data.fee),  # accumalated fee
                fee_currency=data.feeCcy,  # accumalated fee currency
                cost=Decimal(data.avgPx) * Decimal(data.fillSz) * ct_val,
                cum_cost=Decimal(data.avgPx) * Decimal(data.accFillSz) * ct_val,
                reduce_only=data.reduceOnly,
                position_side=OkxEnumParser.parse_position_side(data.posSide),
            )
            self.order_submit(order)

    def _handle_positions(self, raw: bytes):
        position_msg = self._decoder_ws_position_msg.decode(raw)
        self._log.debug(f"Okx Position Msg: {str(position_msg)}")

        for data in position_msg.data:
            symbol = self._market_id.get(data.instId)
            if not symbol:
                continue
            market = self._market[symbol]

            if market.info.ctVal:
                ct_val = Decimal(market.info.ctVal)
            else:
                ct_val = Decimal("1")

            side = data.posSide.parse_to_position_side()
            if side == PositionSide.LONG:
                signed_amount = Decimal(data.pos)
            elif side == PositionSide.SHORT:
                signed_amount = -Decimal(data.pos)
            elif side == PositionSide.FLAT:
                # one way mode, posSide always is 'net' from OKX ws msg, and pos amount is signed
                signed_amount = Decimal(data.pos)
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT
                else:
                    side = None
            else:
                self._log.warning(f"Invalid position side: {side}")

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount * ct_val,
                entry_price=float(data.avgPx) if data.avgPx else 0,
                unrealized_pnl=float(data.upl) if data.upl else 0,
                realized_pnl=float(data.realizedPnl) if data.realizedPnl else 0,
            )
            self._log.debug(f"Position updated: {str(position)}")
            self._cache._apply_position(position)

    def _handle_account(self, raw: bytes):
        account_msg: OkxWsAccountMsg = self._decoder_ws_account_msg.decode(raw)
        self._log.debug(f"Account update: {str(account_msg)}")

        for data in account_msg.data:
            balances = data.parse_to_balance()
            self._cache._apply_balance(self._account_type, balances)

    def _get_td_mode(self, market: OkxMarket):
        if (
            not market.spot
            or self._acctLv.is_portfolio_margin
            or self._acctLv.is_multi_currency_margin
        ):
            return OkxTdMode.CROSS
        else:
            return OkxTdMode.CASH

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
        inst_id = market.id

        td_mode = kwargs.pop("td_mode", None) or kwargs.pop("tdMode", None)
        if not td_mode:
            td_mode = self._get_td_mode(market)
        else:
            td_mode = OkxTdMode(td_mode)

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f")
        else:
            sz = str(amount)

        params = {
            "inst_id": inst_id,
            "td_mode": td_mode.value,
            "side": OkxEnumParser.to_okx_order_side(side).value,
            "ord_type": OkxEnumParser.to_okx_order_type(type, time_in_force).value,
            "sz": sz,
            "tag": "f50cdd72d3b6BCDE",
        }

        if type.is_limit or type.is_post_only:
            if not price:
                raise ValueError("Price is required for limit order")
            params["px"] = str(price)
        else:
            if market.spot and not self._acctLv.is_futures and not td_mode.is_isolated:
                params["tgtCcy"] = "base_ccy"

        if (
            market.spot
            and self._acctLv.is_futures
            and (td_mode.is_cross or td_mode.is_isolated)
        ):
            if side == OrderSide.BUY:
                params["ccy"] = market.quote
            else:
                params["ccy"] = market.base

        attachAlgoOrds = {}
        if tp_trigger_price is not None:
            attachAlgoOrds["tpTriggerPx"] = str(tp_trigger_price)
            attachAlgoOrds["tpTriggerPxType"] = OkxEnumParser.to_okx_trigger_type(
                tp_trigger_type
            ).value
            if tp_order_type.is_limit:
                attachAlgoOrds["tpOrdPx"] = str(tp_price)
            else:
                attachAlgoOrds["tpOrdPx"] = "-1"

        if sl_trigger_price is not None:
            attachAlgoOrds["slTriggerPx"] = str(sl_trigger_price)
            attachAlgoOrds["slTriggerPxType"] = OkxEnumParser.to_okx_trigger_type(
                sl_trigger_type
            ).value
            if sl_order_type.is_limit:
                attachAlgoOrds["slOrdPx"] = str(sl_price)
            else:
                attachAlgoOrds["slOrdPx"] = "-1"

        if attachAlgoOrds:
            params["attachAlgoOrds"] = attachAlgoOrds

        params.update(kwargs)

        try:
            res = await self._api_client.post_api_v5_trade_order(**params)
            res = res.data[0]

            order = Order(
                exchange=self._exchange_id,
                id=res.ordId,
                uuid=uuid,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
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

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ):
        if not orders:
            raise ValueError("Orders list cannot be empty")

        batch_orders = []
        for order in orders:
            market = self._market.get(order.symbol)
            if not market:
                raise ValueError(
                    f"Symbol {order.symbol} formated wrongly, or not supported"
                )
            inst_id = market.id

            td_mode = order.kwargs.pop("td_mode", None) or order.kwargs.pop(
                "tdMode", None
            )
            if not td_mode:
                td_mode = self._get_td_mode(market)
            else:
                td_mode = OkxTdMode(td_mode)

            if not market.spot:
                ct_val = Decimal(market.info.ctVal)
                sz = format(order.amount / ct_val, "f")
            else:
                sz = str(order.amount)

            params = {
                "inst_id": inst_id,
                "td_mode": td_mode.value,
                "side": OkxEnumParser.to_okx_order_side(order.side).value,
                "ord_type": OkxEnumParser.to_okx_order_type(
                    order.type, order.time_in_force
                ).value,
                "sz": sz,
            }

            if order.type.is_limit or order.type.is_post_only:
                if not order.price:
                    raise ValueError("Price is required for limit order")
                params["px"] = str(order.price)
            else:
                if (
                    market.spot
                    and not self._acctLv.is_futures
                    and not td_mode.is_isolated
                ):
                    params["tgtCcy"] = "base_ccy"

            if (
                market.spot
                and self._acctLv.is_futures
                and (td_mode.is_cross or td_mode.is_isolated)
            ):
                if order.side == OrderSide.BUY:
                    params["ccy"] = market.quote
                else:
                    params["ccy"] = market.base

            params["reduceOnly"] = order.reduce_only

            params.update(order.kwargs)
            batch_orders.append(params)

        try:
            res = await self._api_client.post_api_v5_trade_batch_orders(
                payload=batch_orders
            )
            res_batch_orders = []
            for order, res_order in zip(orders, res.data):
                if res_order.sCode == "0":
                    order_result = Order(
                        exchange=self._exchange_id,
                        uuid=order.uuid,
                        id=res_order.ordId,
                        client_order_id=res_order.clOrdId,
                        timestamp=int(res_order.ts),
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
                    order_result = Order(
                        exchange=self._exchange_id,
                        uuid=order.uuid,
                        timestamp=self._clock.timestamp_ms(),
                        symbol=order.symbol,
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
                    self._log.error(
                        f"Failed to create order for {order.symbol}: {res_order.sMsg}: {res_order.sCode}: {order.uuid}"
                    )
                res_batch_orders.append(order_result)
            return res_batch_orders
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(
                f"Error creating batch orders: {error_msg} params: {str(orders)}"
            )
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
                )
                for order in orders
            ]
            return res_batch_orders
    
    async def create_order_ws(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal = None,
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
                price=float(price) if price else None,
                time_in_force=time_in_force,
                timestamp=self._clock.timestamp_ms(),
                reduce_only=reduce_only,
            )
        )
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        td_mode = kwargs.pop("td_mode", None) or kwargs.pop("tdMode", None)
        if not td_mode:
            td_mode = self._get_td_mode(market)
        else:
            td_mode = OkxTdMode(td_mode)

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f")
        else:
            sz = str(amount)

        params = {
            "instId": inst_id,
            "tdMode": td_mode.value,
            "side": OkxEnumParser.to_okx_order_side(side).value,
            "ordType": OkxEnumParser.to_okx_order_type(type, time_in_force).value,
            "sz": sz,
        }

        if type.is_limit or type.is_post_only:
            if not price:
                raise ValueError("Price is required for limit order")
            params["px"] = str(price)
        else:
            if market.spot and not self._acctLv.is_futures and not td_mode.is_isolated:
                params["tgtCcy"] = "base_ccy"

        if (
            market.spot
            and self._acctLv.is_futures
            and (td_mode.is_cross or td_mode.is_isolated)
        ):
            if side == OrderSide.BUY:
                params["ccy"] = market.quote
            else:
                params["ccy"] = market.base

        params["reduceOnly"] = reduce_only

        params.update(kwargs)

        await self._ws_api_client.place_order(uuid, **params)

    async def create_order(
        self,
        uuid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        # position_side: PositionSide = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        td_mode = kwargs.pop("td_mode", None) or kwargs.pop("tdMode", None)
        if not td_mode:
            td_mode = self._get_td_mode(market)
        else:
            td_mode = OkxTdMode(td_mode)

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f")
        else:
            sz = str(amount)

        params = {
            "inst_id": inst_id,
            "td_mode": td_mode.value,
            "side": OkxEnumParser.to_okx_order_side(side).value,
            "ord_type": OkxEnumParser.to_okx_order_type(type, time_in_force).value,
            "sz": sz,
            "tag": "f50cdd72d3b6BCDE",
        }

        if type.is_limit or type.is_post_only:
            if not price:
                raise ValueError("Price is required for limit order")
            params["px"] = str(price)
        else:
            if market.spot and not self._acctLv.is_futures and not td_mode.is_isolated:
                params["tgtCcy"] = "base_ccy"

        if (
            market.spot
            and self._acctLv.is_futures
            and (td_mode.is_cross or td_mode.is_isolated)
        ):
            if side == OrderSide.BUY:
                params["ccy"] = market.quote
            else:
                params["ccy"] = market.base

        # if position_side:
        #     params["posSide"] = OkxEnumParser.to_okx_position_side(position_side).value

        params["reduceOnly"] = reduce_only

        params.update(kwargs)

        try:
            res = await self._api_client.post_api_v5_trade_order(**params)
            res = res.data[0]

            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                id=res.ordId,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                # position_side=position_side,
                status=OrderStatus.PENDING,
                filled=Decimal(0),
                remaining=amount,
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
                reduce_only=reduce_only,
                # position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def cancel_order_ws(self, uuid: str, symbol: str, order_id: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        params = {"instId": inst_id, "ordId": order_id, **kwargs}
        await self._ws_api_client.cancel_order(uuid, **params)
        
    async def cancel_order(self, uuid: str, symbol: str, order_id: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        params = {"inst_id": inst_id, "ord_id": order_id, **kwargs}

        try:
            res = await self._api_client.post_api_v5_trade_cancel_order(**params)
            res = res.data[0]
            order = Order(
                uuid=uuid,
                exchange=self._exchange_id,
                id=res.ordId,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
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
        # NOTE: modify order with side is not supported by OKX
        if price is None and amount is None:
            raise ValueError("Either price or amount must be provided")
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        inst_id = market.id

        if not market.spot:
            ct_val = Decimal(market.info.ctVal)  # contract size
            sz = format(amount / ct_val, "f") if amount else None
        else:
            sz = str(amount) if amount else None

        params = {
            "instId": inst_id,
            "ordId": order_id,
            "newPx": str(price) if price else None,
            "newSz": sz,
            **kwargs,
        }

        try:
            res = await self._api_client.post_api_v5_trade_amend_order(**params)
            res = res.data[0]
            order = Order(
                exchange=self._exchange_id,
                id=res.ordId,
                uuid=uuid,
                client_order_id=res.clOrdId,
                timestamp=int(res.ts),
                symbol=symbol,
                status=OrderStatus.PENDING,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                uuid=uuid,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.FAILED,
            )
            return order

    async def get_order(self, symbol: str, order_id: str):
        market = self._market.get(symbol)
        if not market:
            return None
        try:
            res: OkxOrderResponse = await self._api_client.get_api_v5_trade_order(
                inst_id=market.id, ord_id=order_id
            )
            if not res.data:
                return None

            data = res.data[0]
            if not market.spot:
                ct_val = Decimal(market.info.ctVal)  # type: ignore
            else:
                ct_val = Decimal("1")
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OkxEnumParser.parse_order_status(data.state),
                id=data.ordId,
                amount=Decimal(data.sz) * ct_val,
                filled=Decimal(data.accFillSz) * ct_val,
                client_order_id=data.clOrdId,
                timestamp=int(data.uTime),
                type=OkxEnumParser.parse_order_type(data.ordType),
                side=OkxEnumParser.parse_order_side(data.side),
                time_in_force=OkxEnumParser.parse_time_in_force(data.ordType),
                price=float(data.px) if data.px else None,
                average=float(data.avgPx) if data.avgPx else None,
                last_filled_price=float(data.fillPx) if data.fillPx else None,
                last_filled=Decimal(data.fillSz) * ct_val
                if data.fillSz
                else Decimal(0),
                remaining=Decimal(data.sz) * ct_val - Decimal(data.accFillSz) * ct_val,
                fee=Decimal(data.fee),  # accumalated fee
                fee_currency=data.feeCcy,  # accumalated fee currency
                cost=Decimal(data.avgPx) * Decimal(data.fillSz) * ct_val,
                cum_cost=Decimal(data.avgPx) * Decimal(data.accFillSz) * ct_val,
                reduce_only=data.reduceOnly,
                position_side=OkxEnumParser.parse_position_side(data.posSide),
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg}")
            return None

    async def cancel_all_orders(self, symbol: str):
        """
        no cancel all orders in OKX
        """
        pass

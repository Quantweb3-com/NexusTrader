import msgspec
from typing import Dict, List
from decimal import Decimal
from typing import Literal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from nexustrader.error import PositionModeError
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.core.cache import AsyncCache
from nexustrader.base import OrderManagementSystem
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry
from nexustrader.schema import (
    Order,
    Position,
    BatchOrderSubmit,
)
from nexustrader.constants import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    TriggerType,
)
from nexustrader.exchange.bitget.schema import (
    BitgetMarket,
    BitgetWsGeneralMsg,
    BitgetWsUtaGeneralMsg,
    BitgetWsArgMsg,
    BitgetOrderWsMsg,
    BitgetPositionWsMsg,
    BitgetUtaOrderWsMsg,
    BitgetUtaPositionWsMsg,
    BitgetSpotAccountWsMsg,
    BitgetFuturesAccountWsMsg,
    BitgetUtaAccountWsMsg,
    BitgetWsApiGeneralMsg,
    BitgetWsApiArgMsg,
    BitgetWsApiUtaGeneralMsg,
)
from nexustrader.exchange.bitget.rest_api import BitgetApiClient
from nexustrader.exchange.bitget.websockets import BitgetWSClient, BitgetWSApiClient
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetInstType,
    BitgetUtaInstType,
    BitgetEnumParser,
    BitgetPositionSide,
)


class BitgetOrderManagementSystem(OrderManagementSystem):
    _inst_type_map = {
        BitgetInstType.SPOT: "spot",
        BitgetInstType.USDC_FUTURES: "linear",
        BitgetInstType.USDT_FUTURES: "linear",
        BitgetInstType.COIN_FUTURES: "inverse",
    }
    _uta_inst_type_map = {
        BitgetUtaInstType.SPOT: "spot",
        BitgetUtaInstType.USDC_FUTURES: "linear",
        BitgetUtaInstType.USDT_FUTURES: "linear",
        BitgetUtaInstType.COIN_FUTURES: "inverse",
    }
    _ws_client: BitgetWSClient
    _account_type: BitgetAccountType
    _market: Dict[str, BitgetMarket]
    _market_id: Dict[str, str]
    _api_client: BitgetApiClient

    def __init__(
        self,
        account_type: BitgetAccountType,
        api_key: str,
        secret: str,
        passphrase: str,
        market: Dict[str, BitgetMarket],
        market_id: Dict[str, str],
        registry: OrderRegistry,
        cache: AsyncCache,
        api_client: BitgetApiClient,
        exchange_id: ExchangeType,
        clock: LiveClock,
        msgbus: MessageBus,
        task_manager: TaskManager,
        max_slippage: float,
        enable_rate_limit: bool,
    ):
        super().__init__(
            account_type=account_type,
            market=market,
            market_id=market_id,
            registry=registry,
            cache=cache,
            api_client=api_client,
            ws_client=BitgetWSClient(
                account_type=account_type,
                handler=self._ws_uta_msg_handler
                if account_type.is_uta
                else self._ws_msg_handler,
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

        self._ws_api_client = BitgetWSApiClient(
            account_type=account_type,
            api_key=api_key,
            secret=secret,
            passphrase=passphrase,
            handler=self._ws_uta_api_msg_handler
            if account_type.is_uta
            else self._ws_api_msg_handler,
            task_manager=task_manager,
            clock=clock,
            enable_rate_limit=enable_rate_limit,
        )

        self._max_slippage = max_slippage
        self._ws_msg_general_decoder = msgspec.json.Decoder(BitgetWsGeneralMsg)
        self._ws_msg_uta_general_decoder = msgspec.json.Decoder(BitgetWsUtaGeneralMsg)
        self._ws_msg_orders_decoder = msgspec.json.Decoder(BitgetOrderWsMsg)
        self._ws_msg_uta_orders_decoder = msgspec.json.Decoder(BitgetUtaOrderWsMsg)
        self._ws_msg_positions_decoder = msgspec.json.Decoder(BitgetPositionWsMsg)
        self._ws_msg_uta_positions_decoder = msgspec.json.Decoder(
            BitgetUtaPositionWsMsg
        )

        self._ws_msg_spot_account_decoder = msgspec.json.Decoder(BitgetSpotAccountWsMsg)
        self._ws_msg_futures_account_decoder = msgspec.json.Decoder(
            BitgetFuturesAccountWsMsg
        )
        self._ws_msg_uta_account_decoder = msgspec.json.Decoder(BitgetUtaAccountWsMsg)

        self._ws_api_general_decoder = msgspec.json.Decoder(BitgetWsApiGeneralMsg)
        self._ws_api_uta_general_decoder = msgspec.json.Decoder(
            BitgetWsApiUtaGeneralMsg
        )

    def _ws_uta_api_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_api_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return
        try:
            ws_msg = self._ws_api_uta_general_decoder.decode(raw)

            if ws_msg.is_id_msg:
                self._handle_id_messages(ws_msg)
            elif ws_msg.is_error_msg:
                self._log.error(f"login Error: {ws_msg.error_msg}")

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _ws_api_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_api_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return

        try:
            ws_msg = self._ws_api_general_decoder.decode(raw)

            if ws_msg.is_arg_msg:
                self._handle_arg_messages(ws_msg)
            elif ws_msg.is_error_msg:
                self._log.error(f"login Error: {ws_msg.error_msg}")

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_id_messages(self, ws_msg: BitgetWsApiUtaGeneralMsg):
        """Handle argument messages for place and cancel orders"""
        if ws_msg.is_place_order:
            self._handle_uta_place_order_response(ws_msg)
        else:
            self._handle_uta_cancel_order_response(ws_msg)

    def _handle_arg_messages(self, ws_msg: BitgetWsApiGeneralMsg):
        """Handle argument messages for place and cancel orders"""
        for arg_msg in ws_msg.arg:
            if arg_msg.is_place_order:
                self._handle_place_order_response(ws_msg, arg_msg)
            elif arg_msg.is_cancel_order:
                self._handle_cancel_order_response(ws_msg, arg_msg)

    def _handle_uta_place_order_response(self, ws_msg: BitgetWsApiUtaGeneralMsg):
        oid = ws_msg.oid
        tmp_order = self._registry.get_tmp_order(oid)
        ts = self._clock.timestamp_ms()

        if ws_msg.is_success:
            for arg_msg in ws_msg.args:
                ordId = arg_msg.orderId
                self._log.debug(
                    f"[{tmp_order.symbol}] placing order success: oid: {oid} id: {ordId}"
                )
                order = self._create_order_from_tmp(
                    tmp_order, oid, ordId, OrderStatus.PENDING, ts
                )
                self.order_status_update(order)  # INITIALIZED -> PENDING
        else:
            self._log.error(
                f"[{tmp_order.symbol}] new order failed: oid: {oid} {ws_msg.error_msg}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, None, OrderStatus.FAILED, ts
            )
            self.order_status_update(order)

    def _handle_uta_cancel_order_response(self, ws_msg: BitgetWsApiUtaGeneralMsg):
        """Handle cancel order response"""
        oid = ws_msg.id
        tmp_order = self._registry.get_tmp_order(oid)
        ts = self._clock.timestamp_ms()

        if ws_msg.is_success:
            for arg_msg in ws_msg.args:
                ordId = arg_msg.orderId
                self._log.debug(
                    f"[{tmp_order.symbol}] canceling order success: oid: {oid} id: {ordId}"
                )
                order = self._create_order_from_tmp(
                    tmp_order, oid, ordId, OrderStatus.CANCELING, ts
                )
                self.order_status_update(order)  # SOME STATUS -> CANCELING
        else:
            self._log.error(
                f"[{tmp_order.symbol}] canceling order failed: oid: {oid} {ws_msg.error_msg}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, None, OrderStatus.CANCEL_FAILED, ts
            )
            self.order_status_update(order)

    def _handle_place_order_response(
        self, ws_msg: BitgetWsApiGeneralMsg, arg_msg: BitgetWsApiArgMsg
    ):
        """Handle place order response"""
        oid = arg_msg.id
        tmp_order = self._registry.get_tmp_order(oid)
        ts = self._clock.timestamp_ms()

        if ws_msg.is_success:
            ordId = arg_msg.params.orderId
            self._log.debug(
                f"[{tmp_order.symbol}] placing order success: oid: {oid} id: {ordId}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, ordId, OrderStatus.PENDING, ts
            )
            self.order_status_update(order)  # INITIALIZED -> PENDING
        else:
            self._log.error(
                f"[{tmp_order.symbol}] new order failed: oid: {oid} {ws_msg.error_msg}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, None, OrderStatus.FAILED, ts
            )
            self.order_status_update(order)  # INITIALIZED -> FAILED

    def _handle_cancel_order_response(
        self, ws_msg: BitgetWsApiGeneralMsg, arg_msg: BitgetWsApiArgMsg
    ):
        """Handle cancel order response"""
        oid = arg_msg.id
        tmp_order = self._registry.get_tmp_order(oid)
        ts = self._clock.timestamp_ms()

        if ws_msg.is_success:
            ordId = arg_msg.params.orderId
            self._log.debug(
                f"[{tmp_order.symbol}] canceling order success: oid: {oid} id: {ordId}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, ordId, OrderStatus.CANCELING, ts
            )
            self.order_status_update(order)
        else:
            self._log.error(
                f"[{tmp_order.symbol}] canceling order failed: oid: {oid} {ws_msg.error_msg}"
            )
            order = self._create_order_from_tmp(
                tmp_order, oid, None, OrderStatus.CANCEL_FAILED, ts
            )
            self.order_status_update(order)

    def _create_order_from_tmp(
        self,
        tmp_order: Order,
        oid: str,
        order_id: str | None,
        status: OrderStatus,
        timestamp: int,
    ) -> Order:
        """Create Order object from temporary order data"""
        return Order(
            exchange=self._exchange_id,
            symbol=tmp_order.symbol,
            oid=oid,
            eid=order_id,
            side=tmp_order.side,
            status=status,
            amount=tmp_order.amount,
            timestamp=timestamp,
            type=tmp_order.type,
            price=tmp_order.price,
            time_in_force=tmp_order.time_in_force,
            reduce_only=tmp_order.reduce_only,
        )

    def _inst_type_suffix(self, inst_type: BitgetInstType):
        return self._inst_type_map[inst_type]

    def _uta_inst_type_suffix(self, category: BitgetUtaInstType) -> str:
        """Convert UTA category to internal suffix"""
        return self._uta_inst_type_map[category]

    def _get_inst_type(self, market: BitgetMarket):
        if market.spot:
            return "SPOT"
        elif market.linear:
            return "USDT-FUTURES" if market.quote == "USDT" else "USDC-FUTURES"
        elif market.inverse:
            return "COIN-FUTURES"

    def _init_account_balance(self):
        """Initialize account balance"""
        pass

    def _init_position(self):
        """Initialize position"""
        # Bitget has different product types for different instrument types

        if self._account_type.is_uta:
            # For UTA accounts, use the v3 position API
            categories = ["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]

            for category in categories:
                response = self._api_client.get_api_v3_position_current_position(
                    category=category
                )

                if not response.data.list:
                    continue

                for pos_data in response.data.list:
                    # Skip positions with zero total
                    if float(pos_data.total) == 0:
                        continue

                    # Check position mode - only support one-way mode for UTA
                    if pos_data.holdMode != "one_way_mode":
                        raise PositionModeError(
                            f"Only one-way mode is supported for UTA accounts. Current mode: {pos_data.holdMode}"
                        )

                    # Determine suffix based on category
                    if category == "USDT-FUTURES":
                        inst_type_suffix = "linear"
                    elif category == "USDC-FUTURES":
                        inst_type_suffix = "linear"
                    elif category == "COIN-FUTURES":
                        inst_type_suffix = "inverse"

                    # Map symbol from Bitget format to our internal format
                    symbol = self._market_id.get(
                        f"{pos_data.symbol}_{inst_type_suffix}"
                    )

                    if not symbol:
                        self._log.warning(
                            f"Symbol {pos_data.symbol} not found in market mapping"
                        )
                        continue

                    # Convert position side string to BitgetPositionSide enum
                    hold_side = BitgetPositionSide(pos_data.posSide)

                    # Convert to signed amount based on position side
                    signed_amount = Decimal(pos_data.total)
                    if hold_side == BitgetPositionSide.SHORT:
                        signed_amount = -signed_amount

                    # Parse position side
                    position_side = hold_side.parse_to_position_side()

                    # Create Position object
                    position = Position(
                        symbol=symbol,
                        exchange=self._exchange_id,
                        signed_amount=signed_amount,
                        entry_price=float(pos_data.avgPrice),
                        side=position_side,
                        unrealized_pnl=float(pos_data.unrealisedPnl),
                        realized_pnl=float(pos_data.curRealisedPnl),
                    )

                    # Apply position to cache
                    self._cache._apply_position(position)
                    self._log.debug(f"Initialized UTA position: {str(position)}")

        else:
            product_types = ["USDT-FUTURES", "USDC-FUTURES", "COIN-FUTURES"]

            for product_type in product_types:
                # Get all positions for this product type
                response = self._api_client.get_api_v2_mix_position_all_position(
                    productType=product_type
                )

                for pos_data in response.data:
                    # Check position mode - only support one-way mode
                    if pos_data.posMode != "one_way_mode":
                        raise PositionModeError(
                            f"Only one-way position mode is supported. Current mode: {pos_data.posMode}"
                        )

                    # Skip positions with zero amount
                    if float(pos_data.total) == 0:
                        continue

                    # Map symbol from Bitget format to our internal format
                    inst_type = BitgetInstType(product_type)
                    inst_type_suffix = self._inst_type_suffix(inst_type)
                    symbol = self._market_id.get(
                        f"{pos_data.symbol}_{inst_type_suffix}"
                    )

                    if not symbol:
                        self._log.warning(
                            f"Symbol {pos_data.symbol} not found in market mapping"
                        )
                        continue

                    # Convert holdSide string to BitgetPositionSide enum
                    hold_side = BitgetPositionSide(pos_data.holdSide)

                    # Convert to signed amount based on position side
                    signed_amount = Decimal(pos_data.total)
                    if hold_side == BitgetPositionSide.SHORT:
                        signed_amount = -signed_amount

                    # Parse position side
                    position_side = hold_side.parse_to_position_side()

                    # Create Position object
                    position = Position(
                        symbol=symbol,
                        exchange=self._exchange_id,
                        signed_amount=signed_amount,
                        entry_price=float(pos_data.openPriceAvg),
                        side=position_side,
                        unrealized_pnl=float(pos_data.unrealizedPL),
                        realized_pnl=float(pos_data.achievedProfits),
                    )

                    # Apply position to cache
                    self._cache._apply_position(position)
                    self._log.debug(f"Initialized position: {str(position)}")

    def _position_mode_check(self):
        """Check the position mode"""
        # Position mode check is performed in _init_position for each position
        # Only one-way mode is supported
        pass

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
        raise NotImplementedError

    def _price_to_precision(
        self,
        symbol: str,
        price: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        market = self._market[symbol]
        if market.spot:
            return super()._price_to_precision(symbol, price, mode)
        else:
            price: Decimal = Decimal(str(price))
            price_multiplier = Decimal(market.info.priceEndStep)
            multiplier_count = price / price_multiplier

            if mode == "round":
                price = (
                    multiplier_count.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                ) * price_multiplier
            elif mode == "ceil":
                price = (
                    multiplier_count.quantize(Decimal("1"), rounding=ROUND_CEILING)
                ) * price_multiplier
            elif mode == "floor":
                price = (
                    multiplier_count.quantize(Decimal("1"), rounding=ROUND_FLOOR)
                ) * price_multiplier
            return price

    async def create_order_ws(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        **kwargs,
    ):
        """Create an order"""
        self._registry.register_tmp_order(
            order=Order(
                oid=oid,
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.INITIALIZED,
                amount=amount,
                type=type,
                side=side,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                timestamp=self._clock.timestamp_ms(),
                reduce_only=reduce_only,
            )
        )
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found in market data.")

        if self._account_type.is_uta:
            category: str = kwargs.pop("category", self._get_inst_type(market))
            params = {
                "category": category.lower(),
                "symbol": market.id,
                "side": BitgetEnumParser.to_bitget_order_side(side).value,
                "qty": str(amount),
                "clientOid": oid,
            }
            if type.is_limit:
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["timeInForce"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            if reduce_only:
                params["reduceOnly"] = "yes"

            params.update(kwargs)

            await self._ws_api_client.uta_place_order(id=oid, **params)

        else:
            params = {
                "instId": market.id,
                "side": BitgetEnumParser.to_bitget_order_side(side).value,
                "size": str(amount),
                "clientOid": oid,
            }
            if type.is_limit:
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["force"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            params.update(kwargs)

            if market.swap:
                params["marginCoin"] = market.quote
                params["marginMode"] = kwargs.get("marginMode", "crossed")
                params["instType"] = self._get_inst_type(market)
                if reduce_only:
                    params["reduceOnly"] = "YES"
                await self._ws_api_client.future_place_order(id=oid, **params)
            else:
                await self._ws_api_client.spot_place_order(id=oid, **params)

    async def cancel_order_ws(self, oid: str, symbol: str, **kwargs):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        instId = market.id
        if self._account_type.is_uta:
            await self._ws_api_client.uta_cancel_order(id=oid, clientOid=oid)
        else:
            if market.swap:
                await self._ws_api_client.future_cancel_order(
                    id=oid,
                    instId=instId,
                    clientOid=oid,
                    instType=self._get_inst_type(market),
                )
            else:
                await self._ws_api_client.spot_cancel_order(
                    id=oid, instId=instId, clientOid=oid
                )

    async def create_order(
        self,
        oid: str,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        **kwargs,
    ) -> Order:
        """Create an order"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found in market data.")

        if self._account_type.is_uta:
            category = kwargs.pop("category", self._get_inst_type(market))
            params = {
                "category": category,
                "symbol": market.id,
                "qty": str(amount),
                "clientOid": oid,
            }
            if type.is_limit:
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["timeInForce"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["timeInForce"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            if reduce_only:
                params["reduceOnly"] = "yes"

            params.update(kwargs)

            try:
                res = await self._api_client.post_api_v3_trade_place_order(**params)

                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    eid=str(res.data.orderId),
                    oid=oid,
                    status=OrderStatus.PENDING,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=res.requestTime,
                )

            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(
                    f"Error creating order: {error_msg} params: {str(params)}"
                )
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    oid=oid,
                    status=OrderStatus.FAILED,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=self._clock.timestamp_ms(),
                )
            self.order_status_update(order)
            return
        else:
            params = {
                "symbol": market.id,
                "side": BitgetEnumParser.to_bitget_order_side(side).value,
                "size": str(amount),
                "clientOid": oid,
            }
            if type.is_limit:
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    time_in_force
                ).value
                params["orderType"] = "limit"
            elif type.is_post_only:
                params["price"] = str(price)
                params["force"] = "post_only"
                params["orderType"] = "limit"
            elif type.is_market:
                bookl1 = self._cache.bookl1(symbol)
                if not bookl1:
                    raise ValueError(
                        "Please Subscribe to bookl1 first, since market order requires bookl1 data"
                    )
                if side.is_buy:
                    price = self._price_to_precision(
                        symbol, bookl1.ask * (1 + self._max_slippage), mode="ceil"
                    )
                else:
                    price = self._price_to_precision(
                        symbol, bookl1.bid * (1 - self._max_slippage), mode="floor"
                    )
                params["price"] = str(price)
                params["force"] = BitgetEnumParser.to_bitget_time_in_force(
                    TimeInForce.IOC
                ).value
                params["orderType"] = "limit"

            params.update(kwargs)

            try:
                if market.swap:
                    params["marginCoin"] = market.quote
                    params["marginMode"] = kwargs.get("marginMode", "crossed")
                    params["productType"] = self._get_inst_type(market)
                    if reduce_only:
                        params["reduceOnly"] = "YES"

                    res = await self._api_client.post_api_v2_mix_order_place_order(
                        **params
                    )
                else:
                    res = await self._api_client.post_api_v2_spot_trade_place_order(
                        **params
                    )

                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    oid=oid,
                    eid=str(res.data.orderId),
                    status=OrderStatus.PENDING,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=res.requestTime,
                )

            except Exception as e:
                error_msg = f"{e.__class__.__name__}: {str(e)}"
                self._log.error(
                    f"Error creating order: {error_msg} params: {str(params)}"
                )
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    oid=oid,
                    status=OrderStatus.FAILED,
                    side=side,
                    type=type,
                    price=float(price),
                    amount=amount,
                    time_in_force=time_in_force,
                    filled=Decimal(0),
                    remaining=amount,
                    reduce_only=reduce_only,
                    timestamp=self._clock.timestamp_ms(),
                )
            self.order_status_update(order)

    async def create_batch_orders(
        self,
        orders: List[BatchOrderSubmit],
    ) -> List[Order]:
        """Create multiple orders in a batch"""
        raise NotImplementedError

    async def cancel_order(self, oid: str, symbol: str, **kwargs) -> Order:
        """Cancel an order"""
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id
        params = {
            "symbol": id,
            "clientOid": oid,
        }
        params.update(kwargs)
        try:
            if self._account_type.is_uta:
                res = await self._api_client.post_api_v3_trade_cancel_order(
                    clientOid=oid,
                )

            else:
                if market.swap:
                    params["productType"] = self._get_inst_type(market)
                    res = await self._api_client.post_api_v2_mix_order_cancel_order(
                        **params
                    )
                else:
                    res = await self._api_client.post_api_v2_spot_trade_cancel_order(
                        **params
                    )
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                eid=res.data.orderId,
                timestamp=res.requestTime,
                symbol=symbol,
                status=OrderStatus.CANCELING,
            )
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                oid=oid,
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.CANCEL_FAILED,
            )
        self.order_status_update(order)

    async def modify_order(
        self,
        oid: str,
        symbol: str,
        order_id: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ) -> Order:
        """Modify an order"""
        raise NotImplementedError

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders"""
        if not self._account_type.is_uta:
            raise NotImplementedError("Only UTA account type is supported")

        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id
            category = self._get_inst_type(market)

            await self._api_client.post_api_v3_trade_cancel_symbol_order(
                symbol=symbol, category=category
            )

        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)} params: symbol={symbol} category={category}"
            self._log.error(f"Error canceling all orders: {error_msg}")
            return False

    def _ws_uta_msg_handler(self, raw: bytes):
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return
        try:
            ws_msg = self._ws_msg_uta_general_decoder.decode(raw)
            if ws_msg.is_event_data:
                self._handle_event_data(ws_msg)
            elif ws_msg.arg.topic == "order":
                self._handle_uta_order_event(raw)
            elif ws_msg.arg.topic == "position":
                self._handle_uta_position_event(raw)
            elif ws_msg.arg.topic == "account":
                self._handle_uta_account_event(raw)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_uta_account_event(self, raw: bytes):
        msg = self._ws_msg_uta_account_decoder.decode(raw)
        balances = msg.parse_to_balances()
        self._cache._apply_balance(
            account_type=self._account_type,
            balances=balances,
        )
        for balance in balances:
            self._log.debug(
                f"Balance update: {balance.asset} - {balance.free} free, {balance.locked} locked"
            )

    def _handle_uta_position_event(self, raw: bytes):
        msg = self._ws_msg_uta_positions_decoder.decode(raw)
        for data in msg.data:
            # Determine suffix based on marginCoin
            if data.marginCoin in ["USDT", "USDC"]:
                suffix = "linear"
            else:
                suffix = "inverse"

            sym_id = f"{data.symbol}_{suffix}"
            symbol = self._market_id.get(sym_id)

            if not symbol:
                self._log.warning(f"Symbol not found for UTA position: {sym_id}")
                continue

            # Parse position side
            position_side = data.posSide.parse_to_position_side()
            signed_amount = Decimal(data.size)
            if position_side.is_short:
                signed_amount = -signed_amount

            # Create Position object
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                entry_price=float(data.openPriceAvg or 0.0),
                side=position_side,
                unrealized_pnl=float(data.unrealisedPnl or 0.0),
                realized_pnl=float(data.curRealisedPnl or 0.0),
            )

            # Apply position to cache
            self._cache._apply_position(position)
            self._log.debug(f"Position update: {str(position)}")

    def _handle_uta_order_event(self, raw: bytes):
        msg = self._ws_msg_uta_orders_decoder.decode(raw)
        for data in msg.data:
            status = BitgetEnumParser.parse_order_status(data.orderStatus)
            if not status:
                continue
            # Build symbol ID using the helper method
            inst_type_suffix = self._uta_inst_type_suffix(data.category)
            sym_id = f"{data.symbol}_{inst_type_suffix}"

            symbol = self._market_id.get(sym_id)
            if not symbol:
                self._log.warning(f"Symbol not found for {sym_id}")
                continue

            # Parse order data
            timestamp = int(data.updatedTime)

            # Parse order type
            if data.orderType.is_market:
                order_type = OrderType.MARKET
            elif data.timeInForce.is_post_only:
                order_type = OrderType.POST_ONLY
            else:
                order_type = OrderType.LIMIT  # Default fallback

            # Calculate remaining quantity
            remaining = Decimal(data.qty) - Decimal(data.cumExecQty)

            # Calculate average price
            average_price = data.avgPrice or 0
            price = data.price or 0

            # Calculate fee
            total_fee = Decimal(0)
            fee_currency = None
            if data.feeDetail:
                total_fee = sum(Decimal(fee.fee) for fee in data.feeDetail)
                if data.feeDetail:
                    fee_currency = data.feeDetail[0].feeCoin

            order = Order(
                exchange=self._exchange_id,
                eid=data.orderId,
                oid=data.clientOid,
                timestamp=timestamp,
                symbol=symbol,
                type=order_type,
                side=BitgetEnumParser.parse_order_side(data.side),
                price=price,
                average=average_price,
                amount=Decimal(data.qty),
                filled=Decimal(data.cumExecQty),
                remaining=remaining,
                status=status,
                fee=total_fee,
                fee_currency=fee_currency,
                cum_cost=Decimal(data.cumExecValue or 0),
                reduce_only=data.reduceOnly == "yes",
            )
            self._log.debug(f"Order update: {str(order)}")
            self.order_status_update(order)

    def _ws_msg_handler(self, raw: bytes):
        """Handle incoming WebSocket messages"""
        # Process the message based on its type
        if raw == b"pong":
            self._ws_client._transport.notify_user_specific_pong_received()
            self._log.debug(f"Pong received: `{raw.decode()}`")
            return

        try:
            ws_msg = self._ws_msg_general_decoder.decode(raw)
            if ws_msg.is_event_data:
                self._handle_event_data(ws_msg)
            elif ws_msg.arg.channel == "orders":
                self._handle_orders_event(raw, ws_msg.arg)
            elif ws_msg.arg.channel == "positions":
                self._handle_positions_event(raw, ws_msg.arg)
            elif ws_msg.arg.channel == "account":
                self._handle_account_event(raw, ws_msg.arg)

        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _handle_account_event(self, raw: bytes, arg: BitgetWsArgMsg):
        if arg.instType.is_spot:
            msg = self._ws_msg_spot_account_decoder.decode(raw)
        else:
            msg = self._ws_msg_futures_account_decoder.decode(raw)
        self._cache._apply_balance(
            account_type=self._account_type, balances=msg.parse_to_balances()
        )

    def _handle_positions_event(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_msg_positions_decoder.decode(raw)

        # Get existing positions for this specific instrument type
        existing_positions = self._cache.get_all_positions(exchange=self._exchange_id)
        inst_type_suffix = self._inst_type_suffix(arg.instType)

        # Filter existing positions to only include those from this instrument type
        if arg.instType.is_usdt_swap:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].quote == "USDT"
            }
        elif arg.instType.is_usdc_swap:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].quote == "USDC"
            }
        elif arg.instType.is_inverse:
            existing_positions_for_inst_type = {
                symbol: pos
                for symbol, pos in existing_positions.items()
                if self._market[symbol].inverse
            }

        active_symbols = set()

        for data in msg.data:
            sym_id = data.instId
            symbol = self._market_id[f"{sym_id}_{inst_type_suffix}"]
            active_symbols.add(symbol)

            # Convert Bitget position data to Position
            signed_amount = Decimal(data.total)
            if data.holdSide.is_short:
                signed_amount = -signed_amount

            position_side = data.holdSide.parse_to_position_side()

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                entry_price=float(data.openPriceAvg),
                side=position_side,
                unrealized_pnl=float(data.unrealizedPL),
                realized_pnl=float(data.achievedProfits),
            )

            self._cache._apply_position(position)
            self._log.debug(f"Position update: {str(position)}")

        # Close positions that are not in the snapshot (position goes to 0)
        # Only check positions for the current instrument type
        for symbol, existing_position in existing_positions_for_inst_type.items():
            if symbol not in active_symbols:
                # Create a closed position with signed_amount = 0
                closed_position = Position(
                    symbol=symbol,
                    exchange=self._exchange_id,
                    signed_amount=Decimal("0"),
                    entry_price=existing_position.entry_price,
                    side=None,
                    unrealized_pnl=0,
                    realized_pnl=existing_position.realized_pnl,
                )
                self._cache._apply_position(closed_position)
                self._log.debug(f"Position closed: {str(closed_position)}")

    def _handle_event_data(self, msg: BitgetWsGeneralMsg | BitgetWsUtaGeneralMsg):
        if msg.event == "subscribe":
            arg = msg.arg
            self._log.debug(f"Subscribed to {arg.message}")
        elif msg.event == "error":
            code = msg.code
            error_msg = msg.msg
            self._log.error(f"Subscribed error code={code} {error_msg}")
        elif msg.event == "login":
            if msg.code == 0:
                self._log.debug("WebSocket login successful")
            else:
                self._log.error(f"WebSocket login failed: {msg.msg}")

    def _handle_orders_event(self, raw: bytes, arg: BitgetWsArgMsg):
        msg = self._ws_msg_orders_decoder.decode(raw)
        for data in msg.data:
            sym_id = data.instId
            timestamp = int(data.uTime)
            if data.orderType.is_market:
                typ = OrderType.MARKET
            elif data.force.is_post_only:
                typ = OrderType.POST_ONLY
            else:
                typ = OrderType.LIMIT

            status = BitgetEnumParser.parse_order_status(data.status)
            side = BitgetEnumParser.parse_order_side(data.side)

            if fee_details := data.feeDetail:
                fee = fee_details[0].fee
                fee_currency = fee_details[0].feeCoin
            else:
                fee = 0
                fee_currency = None
            filled = data.accBaseVolume
            last_filled = data.accBaseVolume or 0
            last_filled_price = data.fillPrice or 0
            price = data.price or 0
            average = data.priceAvg or 0

            if arg.instType.is_spot:
                symbol = self._market_id[f"{sym_id}_spot"]
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    eid=str(data.orderId),
                    oid=str(data.clientOid),
                    amount=Decimal(data.newSize),
                    filled=Decimal(filled),
                    timestamp=timestamp,
                    status=status,
                    side=side,
                    type=typ,
                    last_filled=Decimal(last_filled),
                    last_filled_price=float(last_filled_price),
                    remaining=Decimal(data.newSize) - Decimal(data.accBaseVolume),
                    fee=Decimal(fee),
                    fee_currency=fee_currency,
                    price=float(price),
                    average=float(average),
                    cost=Decimal(last_filled) * Decimal(last_filled_price),
                    cum_cost=Decimal(filled) * Decimal(average),
                )
            else:
                symbol = self._market_id[
                    f"{sym_id}_{self._inst_type_suffix(arg.instType)}"
                ]
                order = Order(
                    exchange=self._exchange_id,
                    symbol=symbol,
                    eid=str(data.orderId),
                    oid=str(data.clientOid),
                    amount=Decimal(data.size),
                    filled=Decimal(filled),
                    timestamp=timestamp,
                    status=status,
                    side=side,
                    type=typ,
                    last_filled=Decimal(last_filled),
                    last_filled_price=float(last_filled_price),
                    remaining=Decimal(data.size) - Decimal(data.accBaseVolume),
                    fee=Decimal(fee),
                    fee_currency=fee_currency,
                    average=float(average),
                    price=float(price),
                    cost=Decimal(last_filled) * Decimal(last_filled_price),
                    cum_cost=Decimal(filled) * Decimal(average),
                    reduce_only=data.reduceOnly == "yes",
                )
            self.order_status_update(order)

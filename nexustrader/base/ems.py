import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from typing import Literal
from decimal import Decimal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR

from nexustrader.schema import BaseMarket
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus, LiveClock, Logger
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.constants import (
    AccountType,
    SubmitType,
    WsOrderResultType,
    # OrderType,
    # OrderSide,
    # AlgoOrderStatus,
    # TimeInForce,
)
from nexustrader.error import (
    WsAckRejectedError,
    WsAckTimeoutError,
    WsRequestNotSentError,
)
from nexustrader.schema import (
    InstrumentId,
    OrderSubmit,
    # AlgoOrder,
    TakeProfitAndStopLossOrderSubmit,
    CreateOrderSubmit,
    CancelOrderSubmit,
    CancelAllOrderSubmit,
    ModifyOrderSubmit,
    # TWAPOrderSubmit,
    # CancelTWAPOrderSubmit,
    BatchOrderSubmit,
)
from nexustrader.base.connector import PrivateConnector


class ExecutionManagementSystem(ABC):
    def __init__(
        self,
        market: Dict[str, BaseMarket],
        cache: AsyncCache,
        msgbus: MessageBus,
        clock: LiveClock,
        task_manager: TaskManager,
        registry: OrderRegistry,
        is_mock: bool = False,
    ):
        self._log = Logger(name=type(self).__name__)

        self._market = market
        self._cache = cache
        self._msgbus = msgbus
        self._task_manager = task_manager
        self._registry = registry
        self._clock = clock
        self._order_submit_queues: Dict[
            AccountType, asyncio.Queue[(OrderSubmit, SubmitType)]
        ] = {}
        self._private_connectors: Dict[AccountType, PrivateConnector] | None = None
        self._is_mock = is_mock

    def _build(self, private_connectors: Dict[AccountType, PrivateConnector]):
        self._private_connectors = private_connectors
        self._build_order_submit_queues()
        self._set_account_type()

    def _amount_to_precision(
        self,
        symbol: str,
        amount: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        """
        Convert the amount to the precision of the market
        """
        market = self._market[symbol]
        amount: Decimal = Decimal(str(amount))
        precision = market.precision.amount

        if precision >= 1:
            exp = Decimal(int(precision))
            precision_decimal = Decimal("1")
        else:
            exp = Decimal("1")
            precision_decimal = Decimal(str(precision))

        if mode == "round":
            format_amount = (amount / exp).quantize(
                precision_decimal, rounding=ROUND_HALF_UP
            ) * exp
        elif mode == "ceil":
            format_amount = (amount / exp).quantize(
                precision_decimal, rounding=ROUND_CEILING
            ) * exp
        elif mode == "floor":
            format_amount = (amount / exp).quantize(
                precision_decimal, rounding=ROUND_FLOOR
            ) * exp
        return format_amount

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
    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        pass

    @abstractmethod
    def _build_order_submit_queues(self):
        """
        Build the order submit queues
        """
        pass

    @abstractmethod
    def _set_account_type(self):
        """
        Set the account type
        """
        pass

    @abstractmethod
    def _submit_order(
        self,
        order: OrderSubmit | List[OrderSubmit],
        submit_type: SubmitType,
        account_type: AccountType | None = None,
    ):
        """
        Submit an order
        """
        pass

    async def _modify_order(
        self, order_submit: ModifyOrderSubmit, account_type: AccountType
    ):
        """
        Modify an order
        """
        self._task_manager.create_task(
            self._private_connectors[account_type]._oms.modify_order(
                oid=order_submit.oid,
                symbol=order_submit.symbol,
                price=order_submit.price,
                amount=order_submit.amount,
                side=order_submit.side,
                **order_submit.kwargs,
            )
        )

    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        """
        Cancel all orders
        """
        symbol = order_submit.symbol
        self._task_manager.create_task(
            self._private_connectors[account_type]._oms.cancel_all_orders(symbol)
        )

    async def _cancel_order(
        self, order_submit: CancelOrderSubmit, account_type: AccountType
    ):
        """
        Cancel an order
        """
        self._task_manager.create_task(
            self._private_connectors[account_type]._oms.cancel_order(
                oid=order_submit.oid,
                symbol=order_submit.symbol,
                **order_submit.kwargs,
            )
        )

    def _publish_ws_order_request_result(
        self,
        oid: str,
        symbol: str,
        exchange: str,
        result_type: WsOrderResultType,
        reason: str,
    ):
        """Publish a structured WS order request result event to the message bus."""
        self._msgbus.publish(
            topic="ws_order_request_result",
            msg={
                "oid": oid,
                "symbol": symbol,
                "exchange": exchange,
                "result_type": result_type,
                "reason": reason,
                "timestamp": self._clock.timestamp_ms(),
            },
        )

    async def _create_order_ws_task(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """Background task wrapper for create_order_ws that publishes structured ACK error events."""
        oid = order_submit.oid
        symbol = order_submit.symbol
        exchange = order_submit.instrument_id.exchange.value
        try:
            result = await self._private_connectors[account_type]._oms.create_order_ws(
                oid=oid,
                symbol=symbol,
                side=order_submit.side,
                type=order_submit.type,
                amount=order_submit.amount,
                price=order_submit.price,
                time_in_force=order_submit.time_in_force,
                reduce_only=order_submit.reduce_only,
                **order_submit.kwargs,
            )
            if result is WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
                self._log.info(
                    f"[{symbol}] WS create order ACK timeout confirmed via REST: oid={oid}"
                )
                self._publish_ws_order_request_result(
                    oid=oid,
                    symbol=symbol,
                    exchange=exchange,
                    result_type=WsOrderResultType.ACK_TIMEOUT_CONFIRMED,
                    reason="ACK timeout resolved via REST",
                )
        except WsAckRejectedError as e:
            self._log.warning(f"[{symbol}] WS create order ACK rejected: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.ACK_REJECTED,
                reason=e.reason,
            )
        except WsAckTimeoutError as e:
            self._log.warning(f"[{symbol}] WS create order ACK timeout: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.ACK_TIMEOUT,
                reason=str(e),
            )
        except WsRequestNotSentError as e:
            self._log.warning(f"[{symbol}] WS create order request not sent: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.REQUEST_NOT_SENT,
                reason=str(e),
            )

    async def _cancel_order_ws_task(
        self, order_submit: CancelOrderSubmit, account_type: AccountType
    ):
        """Background task wrapper for cancel_order_ws that publishes structured ACK error events."""
        oid = order_submit.oid
        symbol = order_submit.symbol
        exchange = order_submit.instrument_id.exchange.value
        try:
            result = await self._private_connectors[account_type]._oms.cancel_order_ws(
                oid=oid,
                symbol=symbol,
                **order_submit.kwargs,
            )
            if result is WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
                self._log.info(
                    f"[{symbol}] WS cancel order ACK timeout confirmed via REST: oid={oid}"
                )
                self._publish_ws_order_request_result(
                    oid=oid,
                    symbol=symbol,
                    exchange=exchange,
                    result_type=WsOrderResultType.ACK_TIMEOUT_CONFIRMED,
                    reason="ACK timeout resolved via REST",
                )
        except WsAckRejectedError as e:
            self._log.warning(f"[{symbol}] WS cancel order ACK rejected: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.ACK_REJECTED,
                reason=e.reason,
            )
        except WsAckTimeoutError as e:
            self._log.warning(f"[{symbol}] WS cancel order ACK timeout: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.ACK_TIMEOUT,
                reason=str(e),
            )
        except WsRequestNotSentError as e:
            self._log.warning(f"[{symbol}] WS cancel order request not sent: {e}")
            self._publish_ws_order_request_result(
                oid=oid,
                symbol=symbol,
                exchange=exchange,
                result_type=WsOrderResultType.REQUEST_NOT_SENT,
                reason=str(e),
            )

    async def _cancel_order_ws(
        self, order_submit: CancelOrderSubmit, account_type: AccountType
    ):
        """
        Cancel an order
        """
        self._task_manager.create_task(
            self._cancel_order_ws_task(order_submit, account_type)
        )

    async def _create_order(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """
        Create an order
        """
        if self._should_skip_duplicate_create_submission(
            symbol=order_submit.symbol, oid=order_submit.oid
        ):
            return
        self._registry.register_order(order_submit.oid)
        self._cache.add_inflight_order(order_submit.symbol, order_submit.oid)
        self._task_manager.create_task(
            self._private_connectors[account_type]._oms.create_order(
                oid=order_submit.oid,
                symbol=order_submit.symbol,
                side=order_submit.side,
                type=order_submit.type,
                amount=order_submit.amount,
                price=order_submit.price,
                time_in_force=order_submit.time_in_force,
                reduce_only=order_submit.reduce_only,
                **order_submit.kwargs,
            )
        )

    async def _create_order_ws(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """
        Create an order
        """
        if self._should_skip_duplicate_create_submission(
            symbol=order_submit.symbol, oid=order_submit.oid
        ):
            return
        self._registry.register_order(order_submit.oid)
        self._cache.add_inflight_order(order_submit.symbol, order_submit.oid)
        self._task_manager.create_task(
            self._create_order_ws_task(order_submit, account_type)
        )

    @abstractmethod
    def _get_min_order_amount(
        self, symbol: str, market: BaseMarket, px: float
    ) -> Decimal:
        """
        Get the minimum order amount
        """
        pass

    def _should_skip_duplicate_create_submission(self, symbol: str, oid: str) -> bool:
        if oid in self._cache.get_inflight_orders(symbol):
            self._log.warning(
                f"[{symbol}] skip duplicate create submission for inflight oid={oid}"
            )
            return True

        if self._registry.is_registered(oid):
            self._log.warning(
                f"[{symbol}] skip duplicate create submission for registered oid={oid}"
            )
            return True

        existing = self._cache.get_order(oid)
        if existing is not None:
            self._log.warning(
                f"[{symbol}] skip duplicate create submission for existing oid={oid}"
            )
            return True

        return False

    # async def _auto_maker(self, order_submit: OrderSubmit, account_type: AccountType):
    #     """
    #     Auto maker order: always place the order at the best price
    #     """
    #     pass

    # def _calculate_twap_orders(
    #     self,
    #     symbol: str,
    #     total_amount: Decimal,
    #     duration: float,
    #     wait: float,
    #     min_order_amount: Decimal,
    #     reduce_only: bool = False,
    # ) -> Tuple[List[Decimal], float]:
    #     """
    #     Calculate the amount list and wait time for the twap order

    #     eg:
    #     amount_list = [10, 10, 10]
    #     wait = 10
    #     """
    #     amount_list = []
    #     if total_amount == 0 or total_amount < min_order_amount:
    #         if reduce_only and total_amount > 0:
    #             self._log.info(
    #                 f"TWAP ORDER: {symbol} Total amount is less than min order amount: {total_amount} < {min_order_amount}, reduce_only: {reduce_only}"
    #             )
    #             return [total_amount], 0
    #         self._log.info(
    #             f"TWAP ORDER: {symbol} Total amount is less than min order amount: {total_amount} < {min_order_amount}"
    #         )
    #         return [], 0

    #     interval = duration // wait
    #     base_amount = float(total_amount) / interval

    #     base_amount = max(
    #         min_order_amount, self._amount_to_precision(symbol, base_amount)
    #     )

    #     interval = int(total_amount // base_amount)
    #     remaining = total_amount - interval * base_amount

    #     amount_list = [base_amount] * interval

    #     if remaining >= min_order_amount or (reduce_only and remaining > 0):
    #         amount_list.append(remaining)
    #     else:
    #         amount_list[-1] += remaining

    #     wait = duration / len(amount_list)

    #     self._log.info(f"TWAP ORDER: {symbol} Amount list: {amount_list}, Wait: {wait}")

    #     return amount_list, wait

    # def _cal_limit_order_price(
    #     self, symbol: str, side: OrderSide, market: BaseMarket
    # ) -> Decimal:
    #     """
    #     Calculate the limit order price
    #     """
    #     basis_point = market.precision.price
    #     book = self._cache.bookl1(symbol)

    #     if side.is_buy:
    #         # if the spread is greater than the basis point
    #         if book.spread > basis_point:
    #             price = book.ask - basis_point
    #         else:
    #             price = book.bid
    #     elif side.is_sell:
    #         # if the spread is greater than the basis point
    #         if book.spread > basis_point:
    #             price = book.bid + basis_point
    #         else:
    #             price = book.ask
    #     price = self._price_to_precision(symbol, price)
    #     self._log.debug(
    #         f"CALCULATE LIMIT ORDER PRICE: symbol: {symbol}, side: {side}, price: {price}, ask: {book.ask}, bid: {book.bid}"
    #     )
    #     return price

    # NOTE: TWAP order related code is commented out for now
    # async def _twap_order(
    #     self, order_submit: TWAPOrderSubmit, account_type: AccountType
    # ):
    #     """
    #     Execute the twap order
    #     """
    #     symbol = order_submit.symbol
    #     instrument_id = order_submit.instrument_id
    #     side = order_submit.side
    #     market = self._market[symbol]
    #     position_side = order_submit.position_side
    #     kwargs = order_submit.kwargs
    #     twap_uuid = order_submit.uuid
    #     check_interval = order_submit.check_interval
    #     reduce_only = order_submit.kwargs.get("reduce_only", False)

    #     algo_order = AlgoOrder(
    #         symbol=symbol,
    #         uuid=twap_uuid,
    #         side=side,
    #         amount=order_submit.amount,
    #         duration=order_submit.duration,
    #         wait=order_submit.wait,
    #         status=AlgoOrderStatus.RUNNING,
    #         exchange=instrument_id.exchange,
    #         timestamp=self._clock.timestamp_ms(),
    #         position_side=position_side,
    #     )

    #     self._cache._order_initialized(algo_order)

    #     min_order_amount: Decimal = self._get_min_order_amount(symbol, market)
    #     amount_list, wait = self._calculate_twap_orders(
    #         symbol=symbol,
    #         total_amount=order_submit.amount,
    #         duration=order_submit.duration,
    #         wait=order_submit.wait,
    #         min_order_amount=min_order_amount,
    #         reduce_only=reduce_only,
    #     )

    #     order_id = None
    #     elapsed_time = 0

    #     try:
    #         while amount_list:
    #             if order_id:
    #                 order = self._cache.get_order(order_id)

    #                 is_opened = order.bind_optional(
    #                     lambda order: order.is_opened
    #                 ).value_or(False)
    #                 on_flight = order.bind_optional(
    #                     lambda order: order.on_flight
    #                 ).value_or(False)
    #                 is_closed = order.bind_optional(
    #                     lambda order: order.is_closed
    #                 ).value_or(False)

    #                 # 检查现价单是否已成交，不然的话立刻下市价单成交 或者 把remaining amount加到下一个市价单上
    #                 if is_opened and not on_flight:
    #                     await self._cancel_order(
    #                         order_submit=CancelOrderSubmit(
    #                             symbol=symbol,
    #                             instrument_id=instrument_id,
    #                             submit_type=SubmitType.CANCEL,
    #                             uuid=order_id,
    #                         ),
    #                         account_type=account_type,
    #                     )
    #                 elif is_closed:
    #                     order_id = None
    #                     remaining = order.unwrap().remaining
    #                     if remaining >= min_order_amount or (
    #                         reduce_only and remaining > 0
    #                     ):
    #                         order = await self._create_order(
    #                             order_submit=CreateOrderSubmit(
    #                                 symbol=symbol,
    #                                 instrument_id=instrument_id,
    #                                 submit_type=SubmitType.CREATE,
    #                                 side=side,
    #                                 type=OrderType.MARKET,
    #                                 amount=remaining,
    #                                 position_side=position_side,
    #                                 time_in_force=TimeInForce.IOC,
    #                                 kwargs=kwargs,
    #                             ),
    #                             account_type=account_type,
    #                         )
    #                         if order.success:
    #                             algo_order.orders.append(order.uuid)
    #                             self._cache._order_status_update(algo_order)
    #                         else:
    #                             algo_order.status = AlgoOrderStatus.FAILED
    #                             self._cache._order_status_update(algo_order)
    #                             self._log.error(
    #                                 f"TWAP ORDER FAILED: symbol: {symbol}, side: {side}"
    #                             )
    #                             break
    #                     else:
    #                         if amount_list:
    #                             amount_list[-1] += remaining
    #                 await asyncio.sleep(check_interval)
    #                 elapsed_time += check_interval
    #             else:
    #                 price = self._cal_limit_order_price(
    #                     symbol=symbol,
    #                     side=side,
    #                     market=market,
    #                 )
    #                 amount = amount_list.pop()
    #                 if amount_list:
    #                     order_submit = CreateOrderSubmit(
    #                         symbol=symbol,
    #                         instrument_id=instrument_id,
    #                         submit_type=SubmitType.CREATE,
    #                         type=OrderType.LIMIT,
    #                         side=side,
    #                         amount=amount,
    #                         price=price,
    #                         time_in_force=TimeInForce.GTC,
    #                         position_side=position_side,
    #                         kwargs=kwargs,
    #                     )
    #                 else:
    #                     order_submit = CreateOrderSubmit(
    #                         symbol=symbol,
    #                         instrument_id=instrument_id,
    #                         submit_type=SubmitType.CREATE,
    #                         type=OrderType.MARKET,
    #                         side=side,
    #                         amount=amount,
    #                         time_in_force=TimeInForce.IOC,
    #                         position_side=position_side,
    #                         kwargs=kwargs,
    #                     )
    #                 order = await self._create_order(order_submit, account_type)
    #                 if order.success:
    #                     order_id = order.uuid
    #                     algo_order.orders.append(order_id)
    #                     self._cache._order_status_update(algo_order)
    #                     await asyncio.sleep(wait - elapsed_time)
    #                     elapsed_time = 0
    #                 else:
    #                     algo_order.status = AlgoOrderStatus.FAILED
    #                     self._cache._order_status_update(algo_order)

    #                     self._log.error(
    #                         f"TWAP ORDER FAILED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
    #                     )
    #                     break

    #         algo_order.status = AlgoOrderStatus.FINISHED
    #         self._cache._order_status_update(algo_order)

    #         self._log.info(
    #             f"TWAP ORDER FINISHED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
    #         )
    #     except asyncio.CancelledError:
    #         algo_order.status = AlgoOrderStatus.CANCELING
    #         self._cache._order_status_update(algo_order)

    #         open_orders = self._cache.get_open_orders(symbol=symbol)
    #         for uuid in open_orders.copy():
    #             await self._cancel_order(
    #                 order_submit=CancelOrderSubmit(
    #                     symbol=symbol,
    #                     instrument_id=instrument_id,
    #                     submit_type=SubmitType.CANCEL,
    #                     uuid=uuid,
    #                 ),
    #                 account_type=account_type,
    #             )

    #         algo_order.status = AlgoOrderStatus.CANCELED
    #         self._cache._order_status_update(algo_order)

    #         self._log.info(
    #             f"TWAP ORDER CANCELLED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
    #         )

    # async def _create_twap_order(
    #     self, order_submit: TWAPOrderSubmit, account_type: AccountType
    # ):
    #     """
    #     Create a twap order
    #     """
    #     uuid = order_submit.uuid
    #     self._task_manager.create_task(
    #         self._twap_order(order_submit, account_type), name=uuid
    #     )

    # async def _cancel_twap_order(
    #     self, order_submit: CancelTWAPOrderSubmit, account_type: AccountType
    # ):
    #     """
    #     Cancel a twap order
    #     """
    #     uuid = order_submit.uuid
    #     self._task_manager.cancel_task(uuid)

    async def _create_tp_sl_order(
        self, order_submit: TakeProfitAndStopLossOrderSubmit, account_type: AccountType
    ):
        self._registry.register_order(order_submit.oid)
        self._cache.add_inflight_order(order_submit.symbol, order_submit.oid)
        await self._private_connectors[account_type]._oms.create_tp_sl_order(
            oid=order_submit.oid,
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            tp_order_type=order_submit.tp_order_type,
            tp_trigger_price=order_submit.tp_trigger_price,
            tp_price=order_submit.tp_price,
            tp_trigger_type=order_submit.tp_trigger_type,
            sl_order_type=order_submit.sl_order_type,
            sl_trigger_price=order_submit.sl_trigger_price,
            sl_price=order_submit.sl_price,
            sl_trigger_type=order_submit.sl_trigger_type,
            **order_submit.kwargs,
        )

    async def _handle_submit_order(
        self, account_type: AccountType, queue: asyncio.Queue[(OrderSubmit, SubmitType)]
    ):
        """
        Handle the order submit
        """
        submit_handlers = {
            SubmitType.CANCEL: self._cancel_order,
            SubmitType.CREATE: self._create_order,
            # SubmitType.TWAP: self._create_twap_order,
            # SubmitType.CANCEL_TWAP: self._cancel_twap_order,
            SubmitType.MODIFY: self._modify_order,
            SubmitType.CANCEL_ALL: self._cancel_all_orders,
            SubmitType.BATCH: self._create_batch_orders,
            SubmitType.TAKE_PROFIT_AND_STOP_LOSS: self._create_tp_sl_order,
            SubmitType.CREATE_WS: self._create_order_ws,
            SubmitType.CANCEL_WS: self._cancel_order_ws,
        }

        self._log.debug(f"Handling orders for account type: {account_type}")
        while True:
            (order_submit, submit_type) = await queue.get()
            self._log.debug(f"[ORDER SUBMIT]: {order_submit}")
            handler = submit_handlers[submit_type]
            await handler(order_submit, account_type)
            queue.task_done()

    async def _create_batch_orders(
        self, batch_orders: List[BatchOrderSubmit], account_type: AccountType
    ):
        for order in batch_orders:
            self._registry.register_order(order.oid)
            self._cache.add_inflight_order(order.symbol, order.oid)

        await self._private_connectors[account_type]._oms.create_batch_orders(
            orders=batch_orders,
        )

    async def start(self):
        """
        Start the order submit
        """
        for account_type in self._order_submit_queues.keys():
            self._task_manager.create_task(
                self._handle_submit_order(
                    account_type, self._order_submit_queues[account_type]
                )
            )

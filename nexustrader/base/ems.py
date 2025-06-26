import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from typing import Literal
from decimal import Decimal
from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR

from nexustrader.schema import Order, BaseMarket
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus, LiveClock, Logger
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.constants import (
    AccountType,
    SubmitType,
    OrderType,
    OrderSide,
    AlgoOrderStatus,
    TimeInForce,
)
from nexustrader.schema import (
    OrderSubmit,
    AlgoOrder,
    TakeProfitAndStopLossOrderSubmit,
    CreateOrderSubmit,
    CancelOrderSubmit,
    CancelAllOrderSubmit,
    ModifyOrderSubmit,
    TWAPOrderSubmit,
    CancelTWAPOrderSubmit,
    BatchOrderSubmit,
)
from nexustrader.base.connector import PrivateConnector


class ExecutionManagementSystem(ABC):
    def __init__(
        self,
        market: Dict[str, BaseMarket],
        cache: AsyncCache,
        msgbus: MessageBus,
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
        self._clock = LiveClock()
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
        order_id = self._registry.get_order_id(order_submit.uuid)
        if order_id:
            order: Order = await self._private_connectors[account_type].modify_order(
                symbol=order_submit.symbol,
                order_id=order_id,
                price=order_submit.price,
                amount=order_submit.amount,
                side=order_submit.side,
                **order_submit.kwargs,
            )
            order.uuid = order_submit.uuid
            if order.success:
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="pending", msg=order)
            else:
                self._msgbus.send(endpoint="failed", msg=order)
            return order
        else:
            self._log.error(
                f"Order ID not found for UUID: {order_submit.uuid}, The order may already be canceled or filled or not exist"
            )

    async def _cancel_all_orders(
        self, order_submit: CancelAllOrderSubmit, account_type: AccountType
    ):
        """
        Cancel all orders
        """
        await self._private_connectors[account_type].cancel_all_orders(
            order_submit.symbol
        )

    async def _cancel_order(
        self, order_submit: CancelOrderSubmit, account_type: AccountType
    ):
        """
        Cancel an order
        """
        order_id = self._registry.get_order_id(order_submit.uuid)
        if order_id:
            order: Order = await self._private_connectors[account_type].cancel_order(
                symbol=order_submit.symbol,
                order_id=order_id,
                **order_submit.kwargs,
            )
            order.uuid = order_submit.uuid
            if order.success:
                self._cache._order_status_update(order)  # SOME STATUS -> CANCELING
                self._msgbus.send(endpoint="canceling", msg=order)
            else:
                # self._cache._order_status_update(order) # SOME STATUS -> FAILED
                self._msgbus.send(endpoint="cancel_failed", msg=order)
            return order
        else:
            self._log.error(
                f"Order ID not found for UUID: {order_submit.uuid}, The order may already be canceled or filled or not exist"
            )

    async def _create_order(
        self, order_submit: CreateOrderSubmit, account_type: AccountType
    ):
        """
        Create an order
        """
        order: Order = await self._private_connectors[account_type].create_order(
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            position_side=order_submit.position_side,
            **order_submit.kwargs,
        )
        order.uuid = order_submit.uuid
        if order.success:
            self._cache._order_initialized(order)  # INITIALIZED -> PENDING
            self._msgbus.send(endpoint="pending", msg=order)
            self._registry.register_order(order)
        else:
            self._cache._order_status_update(order)  # INITIALIZED -> FAILED
            self._msgbus.send(endpoint="failed", msg=order)
        return order

    async def _create_stop_loss_order(
        self, order_submit: TakeProfitAndStopLossOrderSubmit, account_type: AccountType
    ):
        """
        Create a stop loss order
        """
        order: Order = await self._private_connectors[
            account_type
        ].create_stop_loss_order(
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            trigger_type=order_submit.trigger_type,
            trigger_price=order_submit.trigger_price,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            position_side=order_submit.position_side,
            **order_submit.kwargs,
        )
        order.uuid = order_submit.uuid
        if order.success:
            self._registry.register_order(order)
            self._cache._order_initialized(order)  # INITIALIZED -> PENDING
            self._msgbus.send(endpoint="pending", msg=order)
        else:
            self._cache._order_status_update(order)  # INITIALIZED -> FAILED
            self._msgbus.send(endpoint="failed", msg=order)
        return order

    async def _create_take_profit_order(
        self, order_submit: TakeProfitAndStopLossOrderSubmit, account_type: AccountType
    ) -> Order:
        """
        Create a take profit order
        """
        order: Order = await self._private_connectors[
            account_type
        ].create_take_profit_order(
            symbol=order_submit.symbol,
            side=order_submit.side,
            type=order_submit.type,
            amount=order_submit.amount,
            trigger_price=order_submit.trigger_price,
            trigger_type=order_submit.trigger_type,
            price=order_submit.price,
            time_in_force=order_submit.time_in_force,
            position_side=order_submit.position_side,
            **order_submit.kwargs,
        )
        order.uuid = order_submit.uuid
        if order.success:
            self._registry.register_order(order)
            self._cache._order_initialized(order)  # INITIALIZED -> PENDING
            self._msgbus.send(endpoint="pending", msg=order)
        else:
            self._cache._order_status_update(order)  # INITIALIZED -> FAILED
            self._msgbus.send(endpoint="failed", msg=order)
        return order

    @abstractmethod
    def _get_min_order_amount(self, symbol: str, market: BaseMarket) -> Decimal:
        """
        Get the minimum order amount
        """
        pass

    async def _auto_maker(self, order_submit: OrderSubmit, account_type: AccountType):
        """
        Auto maker order: always place the order at the best price
        """
        pass

    def _calculate_twap_orders(
        self,
        symbol: str,
        total_amount: Decimal,
        duration: float,
        wait: float,
        min_order_amount: Decimal,
        reduce_only: bool = False,
    ) -> Tuple[List[Decimal], float]:
        """
        Calculate the amount list and wait time for the twap order

        eg:
        amount_list = [10, 10, 10]
        wait = 10
        """
        amount_list = []
        if total_amount == 0 or total_amount < min_order_amount:
            if reduce_only and total_amount > 0:
                self._log.info(
                    f"TWAP ORDER: {symbol} Total amount is less than min order amount: {total_amount} < {min_order_amount}, reduce_only: {reduce_only}"
                )
                return [total_amount], 0
            self._log.info(
                f"TWAP ORDER: {symbol} Total amount is less than min order amount: {total_amount} < {min_order_amount}"
            )
            return [], 0

        interval = duration // wait
        base_amount = float(total_amount) / interval

        base_amount = max(
            min_order_amount, self._amount_to_precision(symbol, base_amount)
        )

        interval = int(total_amount // base_amount)
        remaining = total_amount - interval * base_amount

        amount_list = [base_amount] * interval

        if remaining >= min_order_amount or (reduce_only and remaining > 0):
            amount_list.append(remaining)
        else:
            amount_list[-1] += remaining

        wait = duration / len(amount_list)

        self._log.info(f"TWAP ORDER: {symbol} Amount list: {amount_list}, Wait: {wait}")

        return amount_list, wait

    def _cal_limit_order_price(
        self, symbol: str, side: OrderSide, market: BaseMarket
    ) -> Decimal:
        """
        Calculate the limit order price
        """
        basis_point = market.precision.price
        book = self._cache.bookl1(symbol)

        if side.is_buy:
            # if the spread is greater than the basis point
            if book.spread > basis_point:
                price = book.ask - basis_point
            else:
                price = book.bid
        elif side.is_sell:
            # if the spread is greater than the basis point
            if book.spread > basis_point:
                price = book.bid + basis_point
            else:
                price = book.ask
        price = self._price_to_precision(symbol, price)
        self._log.debug(
            f"CALCULATE LIMIT ORDER PRICE: symbol: {symbol}, side: {side}, price: {price}, ask: {book.ask}, bid: {book.bid}"
        )
        return price

    async def _twap_order(
        self, order_submit: TWAPOrderSubmit, account_type: AccountType
    ):
        """
        Execute the twap order
        """
        symbol = order_submit.symbol
        instrument_id = order_submit.instrument_id
        side = order_submit.side
        market = self._market[symbol]
        position_side = order_submit.position_side
        kwargs = order_submit.kwargs
        twap_uuid = order_submit.uuid
        check_interval = order_submit.check_interval
        reduce_only = order_submit.kwargs.get("reduce_only", False)

        algo_order = AlgoOrder(
            symbol=symbol,
            uuid=twap_uuid,
            side=side,
            amount=order_submit.amount,
            duration=order_submit.duration,
            wait=order_submit.wait,
            status=AlgoOrderStatus.RUNNING,
            exchange=instrument_id.exchange,
            timestamp=self._clock.timestamp_ms(),
            position_side=position_side,
        )

        self._cache._order_initialized(algo_order)

        min_order_amount: Decimal = self._get_min_order_amount(symbol, market)
        amount_list, wait = self._calculate_twap_orders(
            symbol=symbol,
            total_amount=order_submit.amount,
            duration=order_submit.duration,
            wait=order_submit.wait,
            min_order_amount=min_order_amount,
            reduce_only=reduce_only,
        )

        order_id = None
        elapsed_time = 0

        try:
            while amount_list:
                if order_id:
                    order = self._cache.get_order(order_id)

                    is_opened = order.bind_optional(
                        lambda order: order.is_opened
                    ).value_or(False)
                    on_flight = order.bind_optional(
                        lambda order: order.on_flight
                    ).value_or(False)
                    is_closed = order.bind_optional(
                        lambda order: order.is_closed
                    ).value_or(False)

                    # 检查现价单是否已成交，不然的话立刻下市价单成交 或者 把remaining amount加到下一个市价单上
                    if is_opened and not on_flight:
                        await self._cancel_order(
                            order_submit=CancelOrderSubmit(
                                symbol=symbol,
                                instrument_id=instrument_id,
                                submit_type=SubmitType.CANCEL,
                                uuid=order_id,
                            ),
                            account_type=account_type,
                        )
                    elif is_closed:
                        order_id = None
                        remaining = order.unwrap().remaining
                        if remaining >= min_order_amount or (
                            reduce_only and remaining > 0
                        ):
                            order = await self._create_order(
                                order_submit=CreateOrderSubmit(
                                    symbol=symbol,
                                    instrument_id=instrument_id,
                                    submit_type=SubmitType.CREATE,
                                    side=side,
                                    type=OrderType.MARKET,
                                    amount=remaining,
                                    position_side=position_side,
                                    time_in_force=TimeInForce.IOC,
                                    kwargs=kwargs,
                                ),
                                account_type=account_type,
                            )
                            if order.success:
                                algo_order.orders.append(order.uuid)
                                self._cache._order_status_update(algo_order)
                            else:
                                algo_order.status = AlgoOrderStatus.FAILED
                                self._cache._order_status_update(algo_order)
                                self._log.error(
                                    f"TWAP ORDER FAILED: symbol: {symbol}, side: {side}"
                                )
                                break
                        else:
                            if amount_list:
                                amount_list[-1] += remaining
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
                else:
                    price = self._cal_limit_order_price(
                        symbol=symbol,
                        side=side,
                        market=market,
                    )
                    amount = amount_list.pop()
                    if amount_list:
                        order_submit = CreateOrderSubmit(
                            symbol=symbol,
                            instrument_id=instrument_id,
                            submit_type=SubmitType.CREATE,
                            type=OrderType.LIMIT,
                            side=side,
                            amount=amount,
                            price=price,
                            time_in_force=TimeInForce.GTC,
                            position_side=position_side,
                            kwargs=kwargs,
                        )
                    else:
                        order_submit = CreateOrderSubmit(
                            symbol=symbol,
                            instrument_id=instrument_id,
                            submit_type=SubmitType.CREATE,
                            type=OrderType.MARKET,
                            side=side,
                            amount=amount,
                            time_in_force=TimeInForce.IOC,
                            position_side=position_side,
                            kwargs=kwargs,
                        )
                    order = await self._create_order(order_submit, account_type)
                    if order.success:
                        order_id = order.uuid
                        algo_order.orders.append(order_id)
                        self._cache._order_status_update(algo_order)
                        await asyncio.sleep(wait - elapsed_time)
                        elapsed_time = 0
                    else:
                        algo_order.status = AlgoOrderStatus.FAILED
                        self._cache._order_status_update(algo_order)

                        self._log.error(
                            f"TWAP ORDER FAILED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
                        )
                        break

            algo_order.status = AlgoOrderStatus.FINISHED
            self._cache._order_status_update(algo_order)

            self._log.info(
                f"TWAP ORDER FINISHED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
            )
        except asyncio.CancelledError:
            algo_order.status = AlgoOrderStatus.CANCELING
            self._cache._order_status_update(algo_order)

            open_orders = self._cache.get_open_orders(symbol=symbol)
            for uuid in open_orders.copy():
                await self._cancel_order(
                    order_submit=CancelOrderSubmit(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        submit_type=SubmitType.CANCEL,
                        uuid=uuid,
                    ),
                    account_type=account_type,
                )

            algo_order.status = AlgoOrderStatus.CANCELED
            self._cache._order_status_update(algo_order)

            self._log.info(
                f"TWAP ORDER CANCELLED: symbol: {symbol}, side: {side}, uuid: {twap_uuid}"
            )

    async def _create_twap_order(
        self, order_submit: TWAPOrderSubmit, account_type: AccountType
    ):
        """
        Create a twap order
        """
        uuid = order_submit.uuid
        self._task_manager.create_task(
            self._twap_order(order_submit, account_type), name=uuid
        )

    async def _cancel_twap_order(
        self, order_submit: CancelTWAPOrderSubmit, account_type: AccountType
    ):
        """
        Cancel a twap order
        """
        uuid = order_submit.uuid
        self._task_manager.cancel_task(uuid)

    async def _handle_submit_order(
        self, account_type: AccountType, queue: asyncio.Queue[(OrderSubmit, SubmitType)]
    ):
        """
        Handle the order submit
        """
        submit_handlers = {
            SubmitType.CANCEL: self._cancel_order,
            SubmitType.CREATE: self._create_order,
            SubmitType.TWAP: self._create_twap_order,
            SubmitType.CANCEL_TWAP: self._cancel_twap_order,
            SubmitType.STOP_LOSS: self._create_stop_loss_order,
            SubmitType.TAKE_PROFIT: self._create_take_profit_order,
            SubmitType.MODIFY: self._modify_order,
            SubmitType.CANCEL_ALL: self._cancel_all_orders,
            SubmitType.BATCH: self._create_batch_orders,
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
        orders: List[Order] = await self._private_connectors[
            account_type
        ].create_batch_orders(
            orders=batch_orders,
        )
        for order in orders:
            if order.success:
                self._registry.register_order(order)
                self._cache._order_initialized(order)  # INITIALIZED -> PENDING
                self._msgbus.send(endpoint="pending", msg=order)
            else:
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="failed", msg=order)
        return orders

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

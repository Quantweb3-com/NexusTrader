from abc import ABC, abstractmethod
from typing import Dict, List, Literal
from decimal import Decimal
import asyncio

from decimal import ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR
from nexustrader.base.oms import OrderManagementSystem
from nexustrader.base.ws_client import WSClient
from nexustrader.base.api_client import ApiClient
from nexustrader.base.exchange import ExchangeManager
from nexustrader.aggregation import (
    KlineAggregator,
    TimeKlineAggregator,
    VolumeKlineAggregator,
)
from nexustrader.schema import (
    Order,
    BaseMarket,
    Position,
    Balance,
    KlineList,
    Ticker,
    Trade,
)
from nexustrader.constants import ExchangeType, AccountType
from nexustrader.core.cache import AsyncCache
from nexustrader.core.entity import TaskManager
from nexustrader.error import OrderError
from nexustrader.constants import (
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    KlineInterval,
    BookLevel,
    OrderStatus,
)
from nexustrader.core.nautilius_core import LiveClock, MessageBus, UUID4, Logger


class ApiProxy:
    def __init__(self, api_client: ApiClient, task_manager: TaskManager):
        self._api_client = api_client
        self._task_manager = task_manager

    def __getattr__(self, name):
        if not hasattr(self._api_client, name):
            raise AttributeError(f"ApiClient has no attribute '{name}'")

        api_method = getattr(self._api_client, name)
        if not callable(api_method):
            return api_method

        # check whether the method is async
        if not asyncio.iscoroutinefunction(api_method):
            return api_method

        def sync_wrapper(*args, **kwargs):
            return self._task_manager.run_sync(api_method(*args, **kwargs))

        return sync_wrapper


class PublicConnector(ABC):
    def __init__(
        self,
        account_type: AccountType,
        market: Dict[str, BaseMarket],
        market_id: Dict[str, str],
        exchange_id: ExchangeType,
        ws_client: WSClient,
        msgbus: MessageBus,
        clock: LiveClock,
        api_client: ApiClient,
        task_manager: TaskManager,
    ):
        self._log = Logger(name=type(self).__name__)
        self._account_type = account_type
        self._market = market
        self._market_id = market_id
        self._exchange_id = exchange_id
        self._ws_client = ws_client
        self._msgbus = msgbus
        self._api_client = api_client
        self._clock = clock
        self._task_manager = task_manager

        # Aggregator management - key: symbol, value: list of aggregators
        self._aggregators: Dict[str, List[KlineAggregator]] = {}
        self._msgbus.subscribe(
            topic="trade", handler=self._handle_trade_for_aggregators
        )

    @property
    def account_type(self):
        return self._account_type

    @abstractmethod
    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request klines"""
        pass

    @abstractmethod
    def request_ticker(
        self,
        symbol: str,
    ) -> Ticker:
        """Request 24hr ticker data"""
        pass

    @abstractmethod
    def request_all_tickers(
        self,
    ) -> Dict[str, Ticker]:
        """Request 24hr ticker data for multiple symbols"""
        pass

    @abstractmethod
    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        """Request index klines"""
        pass

    @abstractmethod
    async def subscribe_trade(self, symbol: str | List[str]):
        """Subscribe to the trade data"""
        pass

    @abstractmethod
    async def unsubscribe_trade(self, symbol: str | List[str]):
        """Unsubscribe from the trade data"""
        pass

    @abstractmethod
    async def subscribe_bookl1(self, symbol: str | List[str]):
        """Subscribe to the bookl1 data"""
        pass

    @abstractmethod
    async def unsubscribe_bookl1(self, symbol: str | List[str]):
        """Unsubscribe from the bookl1 data"""
        pass

    @abstractmethod
    async def subscribe_kline(
        self,
        symbol: str | List[str],
        interval: KlineInterval,
    ):
        """Subscribe to the kline data

        Args:
            symbol: Symbol(s) to subscribe to
            interval: Kline interval
            use_aggregator: If True, use TimeKlineAggregator instead of exchange native klines
        """
        pass

    @abstractmethod
    async def unsubscribe_kline(
        self,
        symbol: str | List[str],
        interval: KlineInterval,
    ):
        """Unsubscribe from the kline data"""
        pass

    async def subscribe_kline_aggregator(
        self,
        symbol: str,
        interval: KlineInterval,
        build_with_no_updates: bool,
    ):
        """Subscribe to time-based kline data using TimeKlineAggregator

        Args:
            symbol: Symbol to subscribe to
            interval: Kline interval
        """
        # Ensure trade subscription for the symbol
        await self.subscribe_trade(symbol)

        # Create and register time kline aggregator
        aggregator = self._create_time_kline_aggregator(
            symbol, interval, build_with_no_updates
        )
        self._add_aggregator(symbol, aggregator)

        self._log.info(
            f"Time kline aggregator created for {symbol} with interval {interval}"
        )

    async def unsubscribe_kline_aggregator(
        self,
        symbol: str,
        interval: KlineInterval,
    ):
        """Unsubscribe from time-based kline data using TimeKlineAggregator

        Args:
            symbol: Symbol to unsubscribe from
            interval: Kline interval
        """
        aggregators = self._aggregators.get(symbol, [])
        # Create a copy to avoid "list changed size during iteration" error
        for aggregator in aggregators.copy():
            if (
                isinstance(aggregator, TimeKlineAggregator)
                and aggregator.interval == interval
            ):
                aggregator.stop()
                aggregators.remove(aggregator)
                self._log.info(
                    f"Time kline aggregator stopped for {symbol} with interval {interval}"
                )
        if not aggregators:
            self._aggregators.pop(symbol, None)
            await self.unsubscribe_trade(symbol)

    async def subscribe_volume_kline_aggregator(
        self, symbol: str, volume_threshold: float, volume_type: str
    ):
        """Subscribe to volume-based kline data using VolumeKlineAggregator

        Args:
            symbol: Symbol to subscribe to
            volume_threshold: Volume threshold for creating new klines
        """
        # Ensure trade subscription for the symbol
        await self.subscribe_trade(symbol)

        # Create and register volume kline aggregator
        aggregator = self._create_volume_kline_aggregator(
            symbol, volume_threshold, volume_type
        )
        self._add_aggregator(symbol, aggregator)

        self._log.info(
            f"Volume kline aggregator created for {symbol} with threshold {volume_threshold} and type {volume_type}"
        )

    async def unsubscribe_volume_kline_aggregator(
        self, symbol: str, volume_threshold: float, volume_type: str
    ):
        """Unsubscribe from volume-based kline data using VolumeKlineAggregator

        Args:
            symbol: Symbol to unsubscribe from
            volume_threshold: Volume threshold for the kline aggregator
        """
        aggregators = self._aggregators.get(symbol, [])
        # Create a copy to avoid "list changed size during iteration" error
        for aggregator in aggregators.copy():
            if (
                isinstance(aggregator, VolumeKlineAggregator)
                and aggregator.volume_threshold == volume_threshold
            ):
                aggregators.remove(aggregator)
                self._log.info(
                    f"Volume kline aggregator stopped for {symbol} with threshold {volume_threshold} and type {volume_type}"
                )
        if not aggregators:
            self._aggregators.pop(symbol, None)
            await self.unsubscribe_trade(symbol)

    @abstractmethod
    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        """Subscribe to the bookl2 data"""
        pass

    @abstractmethod
    async def unsubscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        """Unsubscribe from the bookl2 data"""
        pass

    @abstractmethod
    async def subscribe_funding_rate(self, symbol: str | List[str]):
        """Subscribe to the funding rate data"""
        pass

    @abstractmethod
    async def unsubscribe_funding_rate(self, symbol: str | List[str]):
        """Unsubscribe from the funding rate data"""
        pass

    @abstractmethod
    async def subscribe_index_price(self, symbol: str | List[str]):
        """Subscribe to the index price data"""
        pass

    @abstractmethod
    async def unsubscribe_index_price(self, symbol: str | List[str]):
        """Unsubscribe from the index price data"""
        pass

    @abstractmethod
    async def subscribe_mark_price(self, symbol: str | List[str]):
        """Subscribe to the mark price data"""
        pass

    @abstractmethod
    async def unsubscribe_mark_price(self, symbol: str | List[str]):
        """Unsubscribe from the mark price data"""
        pass

    def _create_time_kline_aggregator(
        self,
        symbol: str,
        interval: KlineInterval,
        build_with_no_updates: bool,
    ) -> TimeKlineAggregator:
        """Create a time-based kline aggregator."""
        return TimeKlineAggregator(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            msgbus=self._msgbus,
            clock=self._clock,
            build_with_no_updates=build_with_no_updates,
        )

    def _create_volume_kline_aggregator(
        self,
        symbol: str,
        volume_threshold: float,
        volume_type: str,
    ) -> VolumeKlineAggregator:
        """Create a volume-based kline aggregator."""

        return VolumeKlineAggregator(
            exchange=self._exchange_id,
            symbol=symbol,
            msgbus=self._msgbus,
            volume_threshold=volume_threshold,
            volume_type=volume_type,
        )

    def _add_aggregator(self, symbol: str, aggregator) -> None:
        """Add an aggregator for a symbol."""
        if symbol not in self._aggregators:
            self._aggregators[symbol] = []
        self._aggregators[symbol].append(aggregator)

    def _handle_trade_for_aggregators(self, trade: Trade) -> None:
        """Route trade data to all aggregators for this symbol."""
        aggregators = self._aggregators.get(trade.symbol)
        if aggregators:
            for aggregator in aggregators:
                aggregator.handle_trade(trade)

    async def disconnect(self):
        """Disconnect from the exchange"""
        # Stop all aggregators
        for aggregators in self._aggregators.values():
            for aggregator in aggregators:
                if hasattr(aggregator, "stop"):
                    aggregator.stop()
        self._aggregators.clear()

        self._ws_client.disconnect()  # not needed to await
        await self._api_client.close_session()


class PrivateConnector(ABC):
    def __init__(
        self,
        account_type: AccountType,
        market: Dict[str, BaseMarket],
        api_client: ApiClient,
        task_manager: TaskManager,
        oms: OrderManagementSystem,
    ):
        self._log = Logger(name=type(self).__name__)
        self._account_type = account_type
        self._market = market
        self._api_client = api_client
        self._oms = oms
        self._task_manager = task_manager
        self._api_proxy = ApiProxy(self._api_client, self._task_manager)

    @property
    def account_type(self):
        return self._account_type

    @property
    def api(self):
        return self._api_proxy

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
    async def connect(self):
        """Connect to the exchange"""
        pass

    async def disconnect(self):
        """Disconnect from the exchange"""
        self._oms._ws_client.disconnect()
        await self._api_client.close_session()


class MockLinearConnector:
    """
    open long -> cache.update_position
    open short -> cache.update_position

    close long -> cache.update_position -> cache.update_balance -> realized_pnl
    close short -> cache.update_position -> cache.update_balance -> realized_pnl
    """

    def __init__(
        self,
        initial_balance: Dict[str, float],
        account_type: AccountType,  # LINEAR_MOCK
        exchange: ExchangeManager,
        msgbus: MessageBus,
        clock: LiveClock,
        cache: AsyncCache,
        task_manager: TaskManager,
        overwrite_balance: bool = False,
        overwrite_position: bool = False,
        fee_rate: float = 0.0005,
        quote_currency: str = "USDT",
        update_interval: int = 60,  # seconds
        leverage: int = 1,
    ):
        self._account_type = account_type
        self._market = exchange.market
        self._market_id = exchange.market_id
        self._exchange_id = exchange.exchange_id
        self._cache = cache
        self._msgbus = msgbus
        self._fee_rate = fee_rate
        self._initial_balance = initial_balance
        self._overwrite_balance = overwrite_balance
        self._overwrite_position = overwrite_position
        self._quote_currency = quote_currency
        self._update_interval = update_interval
        self._clock = clock
        self._task_manager = task_manager
        self._leverage = leverage
        self._log = Logger(name=type(self).__name__)

    async def _init_position(self):
        for _, position in self._cache._get_all_positions_from_db(
            self._exchange_id
        ).items():
            if not self._overwrite_position:
                self._cache._apply_position(position)
        await self._cache.sync_positions()

    async def _init_balance(self):
        balances = []
        if not self._overwrite_balance:
            balances = self._cache._get_all_balances_from_db(self._account_type)

        if not balances:
            balances = [
                Balance(asset=asset, free=Decimal(str(amount)), locked=Decimal(0))
                for asset, amount in self._initial_balance.items()
            ]

        self._cache._apply_balance(self._account_type, balances)
        await self._cache.sync_balances()

    async def cancel_order(self, symbol: str, order_id: str, **kwargs) -> Order:
        """Cancel an order"""
        pass

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders"""
        pass

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        **kwargs,
    ) -> Order:
        try:
            if amount <= 0:
                raise OrderError(f"Invalid order amount {amount}")

            if price is not None and price <= 0:
                raise OrderError(f"Invalid order price {price}")

            market = self._market.get(symbol)
            if not market:
                raise OrderError(f"Symbol {symbol} not found")

            if not market.linear:
                raise OrderError(f"Symbol {symbol} is not a linear contract")

            if market.quote not in self._cache.get_balance(self._account_type).balances:
                raise OrderError(
                    f"Symbol {symbol}: Not enough balance for {market.quote}."
                )

            book = self._cache.bookl1(symbol)
            if not book:
                raise OrderError(
                    f"Please subscribe to the bookl1 data for {symbol} or data not ready"
                )

            quote_balance = float(
                self._cache.get_balance(self._account_type).balance_total[
                    self._quote_currency
                ]
            )

            position = self._cache.get_position(symbol).value_or(None)
            if position:
                # If position exists, check direction
                if (side.is_buy and position.side.is_long) or (
                    side.is_sell and position.side.is_short
                ):
                    # Same direction, add
                    total_notional = self.total_notional + float(amount) * book.mid
                else:
                    # Opposite direction, subtract
                    total_notional = self.total_notional - float(amount) * book.mid
            else:
                # No existing position, just add
                total_notional = self.total_notional + float(amount) * book.mid

            if abs(total_notional) / quote_balance > self._leverage:
                raise OrderError(
                    f"Symbol {symbol}: Not enough margin for leverage: {self._leverage}"
                )

            if side == OrderSide.BUY:  # NOTE: taker order
                price = book.ask
            else:
                price = book.bid

            fee = amount * Decimal(str(price)) * Decimal(str(self._fee_rate))
            fee_currency = market.quote

            reduce_only = kwargs.get("reduce_only", False)

            cost = amount * Decimal(str(price))

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=UUID4().value,
                amount=amount,
                filled=Decimal(0),
                timestamp=self._clock.timestamp_ms(),
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=price,
                average=price,
                remaining=amount,
                reduce_only=reduce_only,
                fee=fee,
                fee_currency=fee_currency,
                cost=cost,
                cum_cost=cost,
            )

            order_filled = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.FILLED,
                id=order.id,
                amount=amount,
                filled=amount,
                timestamp=self._clock.timestamp_ms(),
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=price,
                average=price,
                remaining=Decimal(0),
                reduce_only=reduce_only,
                fee=fee,
                fee_currency=fee_currency,
                cost=cost,
                cum_cost=cost,
            )

            self._apply_position(order)
            self._msgbus.send(
                endpoint=f"{self._exchange_id.value}.order", msg=order_filled
            )
            return order
        except OrderError as e:
            self._log.error(f"Error creating order: {e}")
            return Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                status=OrderStatus.FAILED,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                filled=Decimal(0),
                remaining=amount,
            )

    @property
    def pnl(self) -> float:
        balances = self._cache.get_balance(self._account_type).balance_total
        return float(str(balances[self._quote_currency]))

    @property
    def unrealized_pnl(self) -> float:
        pnl = 0
        for _, position in self._cache.get_all_positions(self._exchange_id).items():
            pnl += position.unrealized_pnl
        return pnl

    @property
    def total_notional(self) -> float:
        notional = 0
        for symbol, position in self._cache.get_all_positions(
            self._exchange_id
        ).items():
            book = self._cache.bookl1(symbol)
            if not book:
                self._log.warning(
                    f"Please subscribe to the `bookl1` data for {symbol} or data not ready"
                )
                continue
            notional += float(position.amount) * book.mid
        return notional

    def _update_unrealized_pnl(self):
        for symbol, position in self._cache.get_all_positions(
            self._exchange_id
        ).items():
            book = self._cache.bookl1(symbol)
            if not book:
                self._log.warning(
                    f"Please subscribe to the `bookl1` data for {symbol} or data not ready"
                )
                return

            if position.is_long:
                unrealized_pnl = float(position.amount) * (
                    book.mid - position.entry_price
                )
            else:
                unrealized_pnl = float(position.amount) * (
                    position.entry_price - book.mid
                )
            position.unrealized_pnl = unrealized_pnl

    def _apply_fee(self, order: Order):
        """
        apply fee to the balance
        """
        self._cache._mem_account_balance[self._account_type]._update_free(
            order.fee_currency, -order.fee
        )

    def _apply_position(self, order: Order):
        """Update position for perpetual contract"""
        symbol = order.symbol
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} not found in market")

        position = self._cache.get_position(symbol).value_or(None)

        # Handle new position creation
        if not position or position.is_closed:
            if order.is_buy:
                signed_amount = order.amount
                side = PositionSide.LONG
            else:
                signed_amount = -order.amount
                side = PositionSide.SHORT

            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                side=side,
                signed_amount=signed_amount,
                entry_price=order.price,
                unrealized_pnl=0,
                realized_pnl=0,
            )
        else:
            # Calculate new position amount
            is_same_direction = (order.is_buy and position.side.is_long) or (
                order.is_sell and position.side.is_short
            )
            new_amount = position.amount + (
                order.amount if is_same_direction else -order.amount
            )  # -10 / 10 - 15 = -5

            # Calculate realized PnL if closing or reducing position
            if not is_same_direction:
                price_diff = (
                    order.price - position.entry_price
                    if position.is_long
                    else position.entry_price - order.price
                )
                closed_amount = min(position.amount, order.amount)
                realized_pnl = float(closed_amount) * price_diff

                position.realized_pnl += realized_pnl
                self._cache._mem_account_balance[self._account_type]._update_free(
                    market.quote, Decimal(str(realized_pnl))
                )

            # Update position details
            if new_amount > Decimal("0"):
                # Position maintains direction but with updated amount
                if is_same_direction:  # NOTE: add to position
                    # Average entry price when adding to position
                    position.entry_price = (
                        float(order.amount) * order.price
                        + float(position.amount) * position.entry_price
                    ) / float(new_amount)
                position.signed_amount = new_amount if position.is_long else -new_amount
            elif new_amount < Decimal("0"):
                # Position flips direction
                position.side = (
                    PositionSide.SHORT if position.is_long else PositionSide.LONG
                )
                position.signed_amount = -new_amount if position.is_long else new_amount
                position.entry_price = order.price
                position.unrealized_pnl = 0
            else:
                # Position closed completely
                position.side = None
                position.signed_amount = Decimal("0")

        self._cache._apply_position(position)
        self._apply_fee(order)

    async def _handle_pnl_update(self):
        while True:
            pnl, unrealized_pnl = self.pnl, self.unrealized_pnl
            self._log.debug(f"Updating pnl: {pnl}, unrealized_pnl: {unrealized_pnl}")
            await asyncio.sleep(self._update_interval)
            self._update_unrealized_pnl()
            await self._cache._sync_pnl(self._clock.timestamp_ms(), pnl, unrealized_pnl)

    async def connect(self):
        self._log.debug(f"Starting mock connector for {self._account_type}")
        await self._init_position()
        await self._init_balance()
        self._task_manager.create_task(self._handle_pnl_update())

    async def disconnect(self):
        await self._cache._sync_pnl(
            self._clock.timestamp_ms(), self.pnl, self.unrealized_pnl
        )

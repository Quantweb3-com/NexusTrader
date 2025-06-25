import os
import signal
import time
import copy
from datetime import datetime
from typing import Dict, List, Set, Callable, Literal
from decimal import Decimal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from collections import defaultdict
from nexustrader.base import ExchangeManager
from nexustrader.indicator import IndicatorManager, Indicator, IndicatorProxy
from nexustrader.core.entity import TaskManager, DataReady, is_redis_available
from nexustrader.core.cache import AsyncCache
from nexustrader.error import StrategyBuildError
from nexustrader.base import (
    ExecutionManagementSystem,
    PrivateConnector,
    PublicConnector,
)
from nexustrader.core.nautilius_core import MessageBus, LiveClock, Logger
from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    BookL2,
    Order,
    FundingRate,
    IndexPrice,
    MarkPrice,
    InstrumentId,
    BaseMarket,
    AccountBalance,
    CreateOrderSubmit,
    TakeProfitAndStopLossOrderSubmit,
    TWAPOrderSubmit,
    ModifyOrderSubmit,
    CancelOrderSubmit,
    CancelAllOrderSubmit,
    CancelTWAPOrderSubmit,
    KlineList,
    BatchOrder,
    BatchOrderSubmit,
)
from nexustrader.constants import (
    DataType,
    BookLevel,
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
    AccountType,
    SubmitType,
    ExchangeType,
    KlineInterval,
    TriggerType,
)


class Strategy:
    def __init__(self):
        self.log = Logger(name=type(self).__name__)

        self._subscriptions: Dict[
            DataType,
            Dict[KlineInterval, Set[str]] | Set[str] | Dict[BookLevel, Set[str]],
        ] = {
            DataType.BOOKL1: set(),
            DataType.BOOKL2: defaultdict(set),
            DataType.TRADE: set(),
            DataType.KLINE: defaultdict(set),
            DataType.FUNDING_RATE: set(),
            DataType.INDEX_PRICE: set(),
            DataType.MARK_PRICE: set(),
        }

        self._initialized = False
        self._scheduler = AsyncIOScheduler()
        self.indicator = IndicatorProxy()

    def _init_core(
        self,
        exchanges: Dict[ExchangeType, ExchangeManager],
        public_connectors: Dict[AccountType, PublicConnector],
        private_connectors: Dict[AccountType, PrivateConnector],
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        ems: Dict[ExchangeType, ExecutionManagementSystem],
        strategy_id: str = None,
        user_id: str = None,
    ):
        if self._initialized:
            return

        self.cache = cache
        self.clock = LiveClock()
        self._ems = ems
        self._task_manager = task_manager
        self._msgbus = msgbus
        self._private_connectors = private_connectors
        self._public_connectors = public_connectors
        self._exchanges = exchanges
        self._indicator_manager = IndicatorManager(self._msgbus)

        # Initialize state exporter if IDs are provided and Redis is fully available
        self._state_exporter = None
        if strategy_id and user_id and is_redis_available():
            try:
                from nexustrader.cli.monitor.state_exporter import StrategyStateExporter

                self._state_exporter = StrategyStateExporter(
                    strategy_id, user_id, cache
                )
                self.log.debug("CLI monitoring enabled with Redis")
            except Exception as e:
                self.log.debug(
                    f"State exporter initialization failed, CLI monitoring disabled: {e}"
                )
        elif strategy_id and user_id:
            self.log.debug("Redis not available, CLI monitoring disabled")

        self._msgbus.register(endpoint="pending", handler=self.on_pending_order)
        self._msgbus.register(endpoint="accepted", handler=self.on_accepted_order)
        self._msgbus.register(
            endpoint="partially_filled", handler=self.on_partially_filled_order
        )
        self._msgbus.register(endpoint="filled", handler=self.on_filled_order)
        self._msgbus.register(endpoint="canceling", handler=self.on_canceling_order)
        self._msgbus.register(endpoint="canceled", handler=self.on_canceled_order)
        self._msgbus.register(endpoint="failed", handler=self.on_failed_order)
        self._msgbus.register(
            endpoint="cancel_failed", handler=self.on_cancel_failed_order
        )

        self._msgbus.register(endpoint="balance", handler=self.on_balance)

        self._initialized = True

        self._subscriptions_ready: Dict[DataType | str, DataReady] = {}

    @property
    def ready(self):
        return all(
            data_ready.ready for data_ready in self._subscriptions_ready.values()
        )

    def api(self, account_type: AccountType):
        return self._private_connectors[account_type].api

    def register_indicator(
        self,
        symbols: str | List[str],
        indicator: Indicator,
        data_type: DataType,
        account_type: AccountType | None = None,
    ):
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `register_indicator` in `on_start` method"
            )

        if isinstance(symbols, str):
            symbols = [symbols]

        # Create separate indicator instances for each symbol to avoid shared state
        for symbol in symbols:
            # Create a deep copy of the indicator for each symbol
            symbol_indicator = copy.deepcopy(indicator)

            # Register the symbol-specific indicator with the proxy
            self.indicator.register_indicator(indicator.name, symbol, symbol_indicator)

            match data_type:
                case DataType.BOOKL1:
                    self._indicator_manager.add_bookl1_indicator(
                        symbol, symbol_indicator
                    )
                case DataType.BOOKL2:
                    self._indicator_manager.add_bookl2_indicator(
                        symbol, symbol_indicator
                    )
                case DataType.KLINE:
                    self._indicator_manager.add_kline_indicator(
                        symbol, symbol_indicator
                    )
                    # Handle warmup for kline indicators
                    if symbol_indicator.requires_warmup:
                        if account_type is None:
                            raise ValueError(
                                "Account type must be specified for kline indicators requiring warmup"
                            )
                        self._perform_indicator_warmup(
                            symbol, symbol_indicator, account_type
                        )
                case DataType.TRADE:
                    self._indicator_manager.add_trade_indicator(
                        symbol, symbol_indicator
                    )
                case DataType.INDEX_PRICE:
                    self._indicator_manager.add_index_price_indicator(
                        symbol, symbol_indicator
                    )
                case DataType.FUNDING_RATE:
                    self._indicator_manager.add_funding_rate_indicator(
                        symbol, symbol_indicator
                    )
                case DataType.MARK_PRICE:
                    self._indicator_manager.add_mark_price_indicator(
                        symbol, symbol_indicator
                    )
                case _:
                    raise ValueError(f"Invalid data type: {data_type}")

    def request_klines(
        self,
        symbol: str | List[str],
        account_type: AccountType,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> KlineList:
        if isinstance(start_time, datetime):
            start_time = int(start_time.timestamp() * 1000)
        if isinstance(end_time, datetime):
            end_time = int(end_time.timestamp() * 1000)

        connector = self._public_connectors[account_type]

        if isinstance(symbol, str):
            symbol = [symbol]

        klines = KlineList([])
        for sym in symbol:
            res = connector.request_klines(
                symbol=sym,
                interval=interval,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
            )
            klines.extend(res)
        return klines

    def request_index_klines(
        self,
        symbol: str | List[str],
        account_type: AccountType,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | datetime | None = None,
        end_time: int | datetime | None = None,
    ) -> KlineList:
        if isinstance(start_time, datetime):
            start_time = int(start_time.timestamp() * 1000)
        if isinstance(end_time, datetime):
            end_time = int(end_time.timestamp() * 1000)

        connector = self._public_connectors[account_type]

        if isinstance(symbol, str):
            symbol = [symbol]

        klines = KlineList([])
        for sym in symbol:
            res = connector.request_index_klines(
                symbol=sym,
                interval=interval,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
            )
            klines.extend(res)
        return klines

    def _perform_indicator_warmup(
        self, symbol: str, indicator: Indicator, account_type: AccountType
    ):
        """Automatically fetch historical data to warm up an indicator."""
        try:
            # Calculate how much historical data we need
            warmup_microseconds = (
                indicator.warmup_period * indicator.warmup_interval.microseconds
            )
            start_time_ms = self.clock.timestamp_ms() - warmup_microseconds

            # Fetch historical klines
            historical_klines = self.request_klines(
                symbol=symbol,
                account_type=account_type,
                interval=indicator.warmup_interval,
                limit=indicator.warmup_period,
                start_time=start_time_ms,
            )

            # Process historical data for warmup (oldest first)
            for kline in historical_klines.values:
                if kline.symbol == symbol and kline.confirm:
                    indicator._process_warmup_kline(kline)

            self.log.debug(
                f"Warmed up indicator {indicator.name} for {symbol} with {len(historical_klines)} klines"
            )

        except Exception as e:
            self.log.error(
                f"Failed to warm up indicator {indicator.name} for {symbol}: {e}"
            )

    def get_warmup_status(self) -> dict[str, list[dict]]:
        """Get the warmup status of all indicators by symbol."""
        status = {}
        requirements = self._indicator_manager.get_warmup_requirements()

        for symbol, indicator_list in requirements.items():
            status[symbol] = []
            for indicator, period, interval in indicator_list:
                status[symbol].append(
                    {
                        "name": indicator.name,
                        "warmup_period": period,
                        "warmup_interval": interval.value,
                        "is_warmed_up": indicator.is_warmed_up,
                        "data_count": indicator._warmup_data_count,
                    }
                )

        return status

    def wait_for_warmup(self, timeout_seconds: int = 60) -> bool:
        """Wait for all indicators to complete warmup. Returns True if all warmed up."""
        start_time = self.clock.timestamp()
        while self.clock.timestamp() - start_time < timeout_seconds:
            if not self._indicator_manager.has_warmup_pending():
                return True

        return False

    def schedule(
        self,
        func: Callable,
        trigger: Literal["interval", "cron"] = "interval",
        **kwargs,
    ):
        """
        cron: run at a specific time second, minute, hour, day, month, year
        interval: run at a specific interval  seconds, minutes, hours, days, weeks, months, years

        kwargs:
            next_run_time: datetime, when to run the first time
            seconds/minutes/hours/days/weeks: int, interval between runs
            year/month/day/hour/minute/second: int, specific time to run
        """
        if not self._initialized:
            raise RuntimeError(
                "Strategy not initialized, please use `schedule` in `on_start` method"
            )
        self._scheduler.add_job(func, trigger=trigger, **kwargs)

    def market(self, symbol: str) -> BaseMarket:
        instrument_id = InstrumentId.from_str(symbol)
        exchange = self._exchanges[instrument_id.exchange]
        return exchange.market[instrument_id.symbol]

    def min_order_amount(self, symbol: str) -> Decimal:
        instrument_id = InstrumentId.from_str(symbol)
        ems = self._ems[instrument_id.exchange]
        return ems._get_min_order_amount(instrument_id.symbol, self.market(symbol))

    def amount_to_precision(
        self,
        symbol: str,
        amount: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        instrument_id = InstrumentId.from_str(symbol)
        ems = self._ems[instrument_id.exchange]
        return ems._amount_to_precision(instrument_id.symbol, amount, mode)

    def price_to_precision(
        self,
        symbol: str,
        price: float,
        mode: Literal["round", "ceil", "floor"] = "round",
    ) -> Decimal:
        instrument_id = InstrumentId.from_str(symbol)
        ems = self._ems[instrument_id.exchange]
        return ems._price_to_precision(instrument_id.symbol, price, mode)

    def create_batch_orders(
        self,
        orders: List[BatchOrder],
        account_type: AccountType | None = None,
    ):
        batch_orders: list[BatchOrderSubmit] = []
        for order in orders:
            batch_order = BatchOrderSubmit(
                symbol=order.symbol,
                instrument_id=InstrumentId.from_str(order.symbol),
                side=order.side,
                type=order.type,
                amount=order.amount,
                price=order.price,
                time_in_force=order.time_in_force,
                kwargs=order.kwargs,
            )
            batch_orders.append(batch_order)
        self._ems[batch_orders[0].instrument_id.exchange]._submit_order(
            batch_orders, SubmitType.BATCH, account_type
        )
        return [order.uuid for order in batch_orders]

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce | None = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        trigger_price: Decimal | None = None,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        account_type: AccountType | None = None,
        **kwargs,
    ) -> str:
        if type.is_stop_loss or type.is_take_profit:
            submit_type = (
                SubmitType.STOP_LOSS if type.is_stop_loss else SubmitType.TAKE_PROFIT
            )
            order = TakeProfitAndStopLossOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                side=side,
                type=type,
                amount=amount,
                price=price,
                time_in_force=time_in_force,
                position_side=position_side,
                trigger_price=trigger_price,
                trigger_type=trigger_type,
                kwargs=kwargs,
            )
            self._ems[order.instrument_id.exchange]._submit_order(
                order, submit_type, account_type
            )
        else:
            order = CreateOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                side=side,
                type=type,
                amount=amount,
                price=price,
                time_in_force=time_in_force,
                position_side=position_side,
                kwargs=kwargs,
            )
            self._ems[order.instrument_id.exchange]._submit_order(
                order, SubmitType.CREATE, account_type
            )
        return order.uuid

    def cancel_order(
        self, symbol: str, uuid: str, account_type: AccountType | None = None, **kwargs
    ) -> str:
        order = CancelOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            uuid=uuid,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(
            order, SubmitType.CANCEL, account_type
        )
        return order.uuid

    def cancel_all_orders(
        self, symbol: str, account_type: AccountType | None = None
    ) -> str:
        order = CancelAllOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
        )
        self._ems[order.instrument_id.exchange]._submit_order(
            order, SubmitType.CANCEL_ALL, account_type
        )

    def modify_order(
        self,
        symbol: str,
        uuid: str,
        side: OrderSide | None = None,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        account_type: AccountType | None = None,
        **kwargs,
    ) -> str:
        order = ModifyOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            uuid=uuid,
            side=side,
            price=price,
            amount=amount,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(
            order, SubmitType.MODIFY, account_type
        )
        return order.uuid

    def create_twap(
        self,
        symbol: str,
        side: OrderSide,
        amount: Decimal,
        duration: int,
        wait: int,
        check_interval: float = 0.1,
        position_side: PositionSide | None = None,
        account_type: AccountType | None = None,
        **kwargs,
    ) -> str:
        order = TWAPOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            side=side,
            amount=amount,
            duration=duration,
            wait=wait,
            check_interval=check_interval,
            position_side=position_side,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(
            order, SubmitType.TWAP, account_type
        )
        return order.uuid

    def cancel_twap(
        self, symbol: str, uuid: str, account_type: AccountType | None = None
    ) -> str:
        order = CancelTWAPOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            uuid=uuid,
        )
        self._ems[order.instrument_id.exchange]._submit_order(
            order, SubmitType.CANCEL_TWAP, account_type
        )
        return order.uuid

    def subscribe_bookl1(
        self, symbols: str | List[str], ready_timeout: int = 60, ready: bool = True
    ):
        """
        Subscribe to level 1 book data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_bookl1` in `on_start` method"
            )

        self._msgbus.subscribe(topic="bookl1", handler=self._on_bookl1)
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.BOOKL1].add(symbol)

        self._subscriptions_ready[DataType.BOOKL1] = DataReady(
            symbols,
            name="bookl1",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_trade(
        self, symbols: str | List[str], ready_timeout: int = 60, ready: bool = True
    ):
        """
        Subscribe to trade data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_trade` in `on_start` method"
            )

        self._msgbus.subscribe(topic="trade", handler=self._on_trade)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.TRADE].add(symbol)

        self._subscriptions_ready[DataType.TRADE] = DataReady(
            symbols,
            name="trade",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_kline(
        self,
        symbols: str | List[str],
        interval: KlineInterval,
        ready_timeout: int = 60,
        ready: bool = True,
    ):
        """
        Subscribe to kline data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            interval (str): The interval of the kline data
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_kline` in `on_start` method"
            )

        self._msgbus.subscribe(topic="kline", handler=self._on_kline)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.KLINE][interval].add(symbol)

        self._subscriptions_ready[interval.value] = DataReady(
            symbols,
            name=f"kline_{interval.value}",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_bookl2(
        self,
        symbols: str | List[str],
        level: BookLevel,
        ready_timeout: int = 60,
        ready: bool = True,
    ):
        """
        Subscribe to level 2 book data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            level (BookLevel): The level of the book data
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_bookl2` in `on_start` method"
            )

        self._msgbus.subscribe(topic="bookl2", handler=self._on_bookl2)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.BOOKL2][level].add(symbol)

        self._subscriptions_ready[DataType.BOOKL2] = DataReady(
            symbols,
            name="bookl2",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_funding_rate(
        self, symbols: str | List[str], ready_timeout: int = 60, ready: bool = True
    ):
        """
        Subscribe to funding rate data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_funding_rate` in `on_start` method"
            )

        self._msgbus.subscribe(topic="funding_rate", handler=self._on_funding_rate)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.FUNDING_RATE].add(symbol)

        self._subscriptions_ready[DataType.FUNDING_RATE] = DataReady(
            symbols,
            name="funding_rate",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_index_price(
        self, symbols: str | List[str], ready_timeout: int = 60, ready: bool = True
    ):
        """
        Subscribe to index price data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_index_price` in `on_start` method"
            )

        self._msgbus.subscribe(topic="index_price", handler=self._on_index_price)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.INDEX_PRICE].add(symbol)

        self._subscriptions_ready[DataType.INDEX_PRICE] = DataReady(
            symbols,
            name="index_price",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def subscribe_mark_price(
        self, symbols: str | List[str], ready_timeout: int = 60, ready: bool = True
    ):
        """
        Subscribe to mark price data for the given symbols.

        Args:
            symbols (List[str]): The symbols to subscribe to.
            ready_timeout (int): The timeout for the data to be ready.
            ready (bool): default is True. Whether the data is ready. If True, the data will be ready immediately. When you use event driven strategy, you can set it to True. Otherwise, set it to False.
        """
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `subscribe_mark_price` in `on_start` method"
            )

        self._msgbus.subscribe(topic="mark_price", handler=self._on_mark_price)

        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.MARK_PRICE].add(symbol)

        self._subscriptions_ready[DataType.MARK_PRICE] = DataReady(
            symbols,
            name="mark_price",
            timeout=ready_timeout,
            permanently_ready=ready,
        )

    def linear_info(
        self,
        exchange: ExchangeType,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        exchange: ExchangeManager = self._exchanges[exchange]
        return exchange.linear(base, quote, exclude)

    def spot_info(
        self,
        exchange: ExchangeType,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        exchange: ExchangeManager = self._exchanges[exchange]
        return exchange.spot(base, quote, exclude)

    def future_info(
        self,
        exchange: ExchangeType,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        exchange: ExchangeManager = self._exchanges[exchange]
        return exchange.future(base, quote, exclude)

    def inverse_info(
        self,
        exchange: ExchangeType,
        base: str | None = None,
        quote: str | None = None,
        exclude: List[str] | None = None,
    ) -> List[str]:
        exchange: ExchangeManager = self._exchanges[exchange]
        return exchange.inverse(base, quote, exclude)

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def _on_start(self):
        # Start state exporter if available
        if self._state_exporter:
            self._state_exporter.start()
        self.on_start()

    def _on_stop(self):
        # Stop state exporter if available
        if self._state_exporter:
            self._state_exporter.stop()
        self.on_stop()

    def on_trade(self, trade: Trade):
        pass

    def on_bookl1(self, bookl1: BookL1):
        pass

    def on_bookl2(self, bookl2: BookL2):
        pass

    def on_kline(self, kline: Kline):
        pass

    def on_funding_rate(self, funding_rate: FundingRate):
        pass

    def on_index_price(self, index_price: IndexPrice):
        pass

    def on_mark_price(self, mark_price: MarkPrice):
        pass

    def on_pending_order(self, order: Order):
        pass

    def on_accepted_order(self, order: Order):
        pass

    def on_partially_filled_order(self, order: Order):
        pass

    def on_filled_order(self, order: Order):
        pass

    def on_canceling_order(self, order: Order):
        pass

    def on_canceled_order(self, order: Order):
        pass

    def on_failed_order(self, order: Order):
        pass

    def on_cancel_failed_order(self, order: Order):
        pass

    def on_balance(self, balance: AccountBalance):
        pass

    def stop(self):
        time.sleep(0.2)  # wait for 200ms to ensure all messages are processed
        os.kill(os.getpid(), signal.SIGINT)

    def wait(self, seconds: int):
        time.sleep(seconds)

    def _on_trade(self, trade: Trade):
        self.on_trade(trade)
        self._subscriptions_ready[DataType.TRADE].input(trade)

    def _on_bookl2(self, bookl2: BookL2):
        self.on_bookl2(bookl2)
        self._subscriptions_ready[DataType.BOOKL2].input(bookl2)

    def _on_kline(self, kline: Kline):
        self.on_kline(kline)
        self._subscriptions_ready[kline.interval.value].input(kline)

    def _on_funding_rate(self, funding_rate: FundingRate):
        self.on_funding_rate(funding_rate)
        self._subscriptions_ready[DataType.FUNDING_RATE].input(funding_rate)

    def _on_bookl1(self, bookl1: BookL1):
        self.on_bookl1(bookl1)
        self._subscriptions_ready[DataType.BOOKL1].input(bookl1)

    def _on_index_price(self, index_price: IndexPrice):
        self.on_index_price(index_price)
        self._subscriptions_ready[DataType.INDEX_PRICE].input(index_price)

    def _on_mark_price(self, mark_price: MarkPrice):
        self.on_mark_price(mark_price)
        self._subscriptions_ready[DataType.MARK_PRICE].input(mark_price)

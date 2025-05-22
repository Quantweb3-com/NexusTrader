import os
import signal
import time
from datetime import datetime
from typing import Dict, List, Set, Callable, Literal
from decimal import Decimal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from collections import defaultdict
from nexustrader.core.log import SpdLog
from nexustrader.base import ExchangeManager
from nexustrader.indicator import IndicatorManager, Indicator
from nexustrader.core.entity import TaskManager, DataReady
from nexustrader.core.cache import AsyncCache
from nexustrader.error import StrategyBuildError
from nexustrader.base import (
    ExecutionManagementSystem,
    PrivateConnector,
    PublicConnector,
)
from nexustrader.core.nautilius_core import MessageBus, LiveClock
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
        self.log = SpdLog.get_logger(
            name=type(self).__name__, level="DEBUG", flush=True
        )

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

    def _init_core(
        self,
        exchanges: Dict[ExchangeType, ExchangeManager],
        public_connectors: Dict[AccountType, PublicConnector],
        private_connectors: Dict[AccountType, PrivateConnector],
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        ems: Dict[ExchangeType, ExecutionManagementSystem],
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

        self._msgbus.subscribe(topic="trade", handler=self._on_trade)
        self._msgbus.subscribe(topic="bookl1", handler=self._on_bookl1)
        self._msgbus.subscribe(topic="kline", handler=self._on_kline)
        self._msgbus.subscribe(topic="bookl2", handler=self._on_bookl2)
        self._msgbus.subscribe(topic="funding_rate", handler=self._on_funding_rate)
        self._msgbus.subscribe(topic="index_price", handler=self._on_index_price)
        self._msgbus.subscribe(topic="mark_price", handler=self._on_mark_price)

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
        self, symbols: str | List[str], indicator: Indicator, data_type: DataType
    ):
        if not self._initialized:
            raise StrategyBuildError(
                "Strategy not initialized, please use `register_indicator` in `on_start` method"
            )

        if isinstance(symbols, str):
            symbols = [symbols]

        match data_type:
            case DataType.BOOKL1:
                for s in symbols:
                    self._indicator_manager.add_bookl1_indicator(s, indicator)
            case DataType.BOOKL2:
                for s in symbols:
                    self._indicator_manager.add_bookl2_indicator(s, indicator)
            case DataType.KLINE:
                for s in symbols:
                    self._indicator_manager.add_kline_indicator(s, indicator)
            case DataType.TRADE:
                for s in symbols:
                    self._indicator_manager.add_trade_indicator(s, indicator)
            case _:
                raise ValueError(f"Invalid data type: {data_type}")

    def request_klines(
        self,
        symbol: str,
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
        return connector.request_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

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
                submit_type=submit_type,
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
        else:
            order = CreateOrderSubmit(
                symbol=symbol,
                instrument_id=InstrumentId.from_str(symbol),
                submit_type=SubmitType.CREATE,
                side=side,
                type=type,
                amount=amount,
                price=price,
                time_in_force=time_in_force,
                position_side=position_side,
                kwargs=kwargs,
            )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)
        return order.uuid

    def cancel_order(
        self, symbol: str, uuid: str, account_type: AccountType | None = None, **kwargs
    ) -> str:
        order = CancelOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            submit_type=SubmitType.CANCEL,
            uuid=uuid,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)
        return order.uuid

    def cancel_all_orders(
        self, symbol: str, account_type: AccountType | None = None
    ) -> str:
        order = CancelAllOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            submit_type=SubmitType.CANCEL_ALL,
        )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)

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
            submit_type=SubmitType.MODIFY,
            uuid=uuid,
            side=side,
            price=price,
            amount=amount,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)
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
            submit_type=SubmitType.TWAP,
            side=side,
            amount=amount,
            duration=duration,
            wait=wait,
            check_interval=check_interval,
            position_side=position_side,
            kwargs=kwargs,
        )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)
        return order.uuid

    def cancel_twap(
        self, symbol: str, uuid: str, account_type: AccountType | None = None
    ) -> str:
        order = CancelTWAPOrderSubmit(
            symbol=symbol,
            instrument_id=InstrumentId.from_str(symbol),
            submit_type=SubmitType.CANCEL_TWAP,
            uuid=uuid,
        )
        self._ems[order.instrument_id.exchange]._submit_order(order, account_type)
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.BOOKL1].add(symbol)

        self._subscriptions_ready[DataType.BOOKL1] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.TRADE].add(symbol)

        self._subscriptions_ready[DataType.TRADE] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.KLINE][interval].add(symbol)

        self._subscriptions_ready[interval.value] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.BOOKL2][level].add(symbol)

        self._subscriptions_ready[DataType.BOOKL2] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.FUNDING_RATE].add(symbol)

        self._subscriptions_ready[DataType.FUNDING_RATE] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.INDEX_PRICE].add(symbol)

        self._subscriptions_ready[DataType.INDEX_PRICE] = DataReady(
            symbols,
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
        if isinstance(symbols, str):
            symbols = [symbols]

        for symbol in symbols:
            self._subscriptions[DataType.MARK_PRICE].add(symbol)

        self._subscriptions_ready[DataType.MARK_PRICE] = DataReady(
            symbols,
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

import asyncio
from typing import Dict, List, Union
from collections import defaultdict

from nexustrader.schema import SubscriptionSubmit, UnsubscriptionSubmit, InstrumentId
from nexustrader.core.entity import TaskManager, DataReady
from nexustrader.core.nautilius_core import Logger, LiveClock
from nexustrader.constants import AccountType, DataType, KlineInterval
from nexustrader.base.connector import PublicConnector, ExchangeManager
from nexustrader.error import SubscriptionError


class SubscriptionManagementSystem:
    def __init__(
        self,
        exchanges: Dict[str, ExchangeManager],
        public_connectors: Dict[AccountType, PublicConnector],
        task_manager: TaskManager,
        clock: LiveClock,
    ):
        self._log = Logger(name=type(self).__name__)

        self._exchanges = exchanges
        self._public_connectors = public_connectors
        self._task_manager = task_manager
        self._clock = clock

        # Two queues: one for subscribe, one for unsubscribe
        self._subscribe_queue: asyncio.Queue[SubscriptionSubmit] = asyncio.Queue()
        self._unsubscribe_queue: asyncio.Queue[UnsubscriptionSubmit] = asyncio.Queue()

        # Track subscription readiness
        self._subscriptions_ready: Dict[Union[DataType, str], DataReady] = {}

    def _infer_account_type(self, symbol: str) -> AccountType:
        """Infer account type from symbol"""
        instrument_id = InstrumentId.from_str(symbol)
        exchange = self._exchanges.get(instrument_id.exchange)
        if not exchange:
            raise ValueError(f"Exchange {instrument_id.exchange} not found")
        return exchange.instrument_id_to_account_type(instrument_id)

    def _group_symbols_by_account_type(
        self, symbols: List[str]
    ) -> Dict[AccountType, List[str]]:
        """Group symbols by their account type"""
        grouped = defaultdict(list)
        for symbol in symbols:
            account_type = self._infer_account_type(symbol)
            grouped[account_type].append(symbol)
        return dict(grouped)

    @property
    def ready(self) -> bool:
        """Check if all subscriptions are ready"""
        return all(
            data_ready.ready for data_ready in self._subscriptions_ready.values()
        )

    def input(self, sub_key: Union[str, DataType], data):
        """
        Input data to the corresponding DataReady tracker.

        Args:
            sub_key: The subscription key (DataType, interval value, or symbol)
            data: The data object to input
        """
        self._subscriptions_ready[sub_key].input(data)

    def subscribe(
        self,
        symbols: str | List[str],
        data_type: DataType,
        params: Dict | None = None,
        ready_timeout: int = 60,
        ready: bool = True,
    ):
        """
        Subscribe to market data.

        Args:
            symbols: Symbol or list of symbols to subscribe
            data_type: Type of data to subscribe (BOOKL1, KLINE, etc.)
            params: Additional parameters (interval for KLINE, level for BOOKL2, etc.)
            ready_timeout: Timeout in seconds for data to be ready
            ready: Whether to track readiness (True for event-driven strategies)
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        if params is None:
            params = {}

        subscription = SubscriptionSubmit(
            symbols=symbols,
            data_type=data_type,
            params=params,
            ready_timeout=ready_timeout,
            ready=ready,
        )

        self._subscribe_queue.put_nowait(subscription)
        self._log.debug(f"Subscription queued: {data_type} for {symbols}")

    def unsubscribe(
        self,
        symbols: str | List[str],
        data_type: DataType,
        params: Dict | None = None,
    ):
        """
        Unsubscribe from market data.

        Args:
            symbols: Symbol or list of symbols to unsubscribe
            data_type: Type of data to unsubscribe (BOOKL1, KLINE, etc.)
            params: Additional parameters (interval for KLINE, level for BOOKL2, etc.)
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        if params is None:
            params = {}

        unsubscription = UnsubscriptionSubmit(
            symbols=symbols,
            data_type=data_type,
            params=params,
        )

        self._unsubscribe_queue.put_nowait(unsubscription)
        self._log.debug(f"Unsubscription queued: {data_type} for {symbols}")

    async def _subscribe_trade(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to trade data"""
        await self._public_connectors[account_type].subscribe_trade(
            subscription.symbols
        )

        # Register DataReady
        if DataType.TRADE not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.TRADE] = DataReady(
                subscription.symbols,
                name="trade",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )

    async def _subscribe_bookl1(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to bookl1 data"""
        await self._public_connectors[account_type].subscribe_bookl1(
            subscription.symbols
        )

        # Register DataReady
        if DataType.BOOKL1 not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.BOOKL1] = DataReady(
                subscription.symbols,
                name="bookl1",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[DataType.BOOKL1].add_symbols(subscription.symbols)

    async def _subscribe_bookl2(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to bookl2 data"""
        level = subscription.params.get("level")
        if level is None:
            raise ValueError("level is required for BOOKL2 subscription")
        await self._public_connectors[account_type].subscribe_bookl2(
            subscription.symbols, level
        )

        # Register DataReady
        if DataType.BOOKL2 not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.BOOKL2] = DataReady(
                subscription.symbols,
                name="bookl2",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[DataType.BOOKL2].add_symbols(subscription.symbols)

    async def _subscribe_kline(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to kline data"""
        interval: KlineInterval = subscription.params.get("interval")
        if interval is None:
            raise ValueError("interval is required for KLINE subscription")

        use_aggregator = subscription.params.get("use_aggregator", False)
        build_with_no_updates = subscription.params.get("build_with_no_updates", True)

        if use_aggregator:
            for symbol in subscription.symbols:
                await self._public_connectors[account_type].subscribe_kline_aggregator(
                    symbol, interval, build_with_no_updates
                )
        else:
            await self._public_connectors[account_type].subscribe_kline(
                subscription.symbols, interval
            )

        # Register DataReady
        if interval.value not in self._subscriptions_ready:
            self._subscriptions_ready[interval.value] = DataReady(
                subscription.symbols,
                name=f"kline_{interval.value}",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[interval.value].add_symbols(subscription.symbols)

    async def _subscribe_volume_kline(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to volume kline data"""
        volume_threshold = subscription.params.get("volume_threshold")
        if volume_threshold is None:
            raise ValueError(
                "`volume_threshold` is required for `VOLUME_KLINE` subscription"
            )

        volume_type = subscription.params.get("volume_type", "DEFAULT")

        for symbol in subscription.symbols:
            await self._public_connectors[
                account_type
            ].subscribe_volume_kline_aggregator(symbol, volume_threshold, volume_type)

            # Register DataReady for each symbol (volume kline uses symbol as key)
            if symbol in self._subscriptions_ready:
                raise ValueError(
                    f"Symbol {symbol} already subscribed to volume kline with a different threshold. Only one volume threshold per symbol is allowed."
                )
            self._subscriptions_ready[symbol] = DataReady(
                [symbol],
                name=f"volume_kline_{volume_threshold}",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )

    async def _unsubscribe_volume_kline(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from volume kline data"""
        volume_threshold = subscription.params.get("volume_threshold")
        if volume_threshold is None:
            raise ValueError(
                "`volume_threshold` is required for `VOLUME_KLINE` unsubscription"
            )

        volume_type = subscription.params.get("volume_type", "DEFAULT")

        for symbol in subscription.symbols:
            await self._public_connectors[
                account_type
            ].unsubscribe_volume_kline_aggregator(symbol, volume_threshold, volume_type)

    async def _subscribe_funding_rate(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to funding rate data"""
        await self._public_connectors[account_type].subscribe_funding_rate(
            subscription.symbols
        )

        # Register DataReady
        if DataType.FUNDING_RATE not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.FUNDING_RATE] = DataReady(
                subscription.symbols,
                name="funding_rate",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[DataType.FUNDING_RATE].add_symbols(
                subscription.symbols
            )

    async def _subscribe_index_price(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to index price data"""
        await self._public_connectors[account_type].subscribe_index_price(
            subscription.symbols
        )

        # Register DataReady
        if DataType.INDEX_PRICE not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.INDEX_PRICE] = DataReady(
                subscription.symbols,
                name="index_price",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[DataType.INDEX_PRICE].add_symbols(
                subscription.symbols
            )

    async def _subscribe_mark_price(
        self, subscription: SubscriptionSubmit, account_type: AccountType
    ):
        """Subscribe to mark price data"""
        await self._public_connectors[account_type].subscribe_mark_price(
            subscription.symbols
        )

        # Register DataReady
        if DataType.MARK_PRICE not in self._subscriptions_ready:
            self._subscriptions_ready[DataType.MARK_PRICE] = DataReady(
                subscription.symbols,
                name="mark_price",
                clock=self._clock,
                timeout=subscription.ready_timeout,
                permanently_ready=subscription.ready,
            )
        else:
            self._subscriptions_ready[DataType.MARK_PRICE].add_symbols(
                subscription.symbols
            )

    async def _unsubscribe_trade(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from trade data"""
        await self._public_connectors[account_type].unsubscribe_trade(
            unsubscription.symbols
        )

    async def _unsubscribe_bookl1(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from bookl1 data"""
        await self._public_connectors[account_type].unsubscribe_bookl1(
            unsubscription.symbols
        )

    async def _unsubscribe_bookl2(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from bookl2 data"""
        level = unsubscription.params.get("level")
        if level is None:
            raise ValueError("level is required for BOOKL2 unsubscription")

        await self._public_connectors[account_type].unsubscribe_bookl2(
            unsubscription.symbols, level
        )

    async def _unsubscribe_kline(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from kline data"""
        interval = unsubscription.params.get("interval")
        if interval is None:
            raise ValueError("interval is required for KLINE unsubscription")

        use_aggregator = unsubscription.params.get("use_aggregator", False)
        if use_aggregator:
            for symbol in unsubscription.symbols:
                await self._public_connectors[
                    account_type
                ].unsubscribe_kline_aggregator(symbol, interval)
        else:
            await self._public_connectors[account_type].unsubscribe_kline(
                unsubscription.symbols, interval
            )

    async def _unsubscribe_mark_price(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from mark price data"""
        await self._public_connectors[account_type].unsubscribe_mark_price(
            unsubscription.symbols
        )

    async def _unsubscribe_funding_rate(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from funding rate data"""
        await self._public_connectors[account_type].unsubscribe_funding_rate(
            unsubscription.symbols
        )

    async def _unsubscribe_index_price(
        self, unsubscription: UnsubscriptionSubmit, account_type: AccountType
    ):
        """Unsubscribe from index price data"""
        await self._public_connectors[account_type].unsubscribe_index_price(
            unsubscription.symbols
        )

    async def _handle_subscribe(self):
        """Handle subscription requests"""
        self._log.debug("Starting subscription handler")

        while True:
            subscription = await self._subscribe_queue.get()
            self._log.debug(f"[SUBSCRIPTION]: {subscription}")

            grouped = self._group_symbols_by_account_type(subscription.symbols)

            # Process each account type group
            for account_type, symbols in grouped.items():
                # Check if account_type exists in public_connectors
                if account_type not in self._public_connectors:
                    raise SubscriptionError(
                        f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                    )

                # Create a new subscription for this account type
                account_subscription = SubscriptionSubmit(
                    symbols=symbols,
                    data_type=subscription.data_type,
                    params=subscription.params,
                    ready=subscription.ready,
                    ready_timeout=subscription.ready_timeout,
                )

                match subscription.data_type:
                    case DataType.TRADE:
                        await self._subscribe_trade(account_subscription, account_type)
                    case DataType.BOOKL1:
                        await self._subscribe_bookl1(account_subscription, account_type)
                    case DataType.BOOKL2:
                        await self._subscribe_bookl2(account_subscription, account_type)
                    case DataType.KLINE:
                        await self._subscribe_kline(account_subscription, account_type)
                    case DataType.VOLUME_KLINE:
                        await self._subscribe_volume_kline(
                            account_subscription, account_type
                        )
                    case DataType.FUNDING_RATE:
                        await self._subscribe_funding_rate(
                            account_subscription, account_type
                        )
                    case DataType.INDEX_PRICE:
                        await self._subscribe_index_price(
                            account_subscription, account_type
                        )
                    case DataType.MARK_PRICE:
                        await self._subscribe_mark_price(
                            account_subscription, account_type
                        )
            self._subscribe_queue.task_done()

    async def _handle_unsubscribe(self):
        """Handle unsubscription requests"""
        self._log.debug("Starting unsubscription handler")

        while True:
            unsubscription = await self._unsubscribe_queue.get()
            self._log.debug(f"[UNSUBSCRIPTION]: {unsubscription}")

            grouped = self._group_symbols_by_account_type(unsubscription.symbols)
            # Process each account type group
            for account_type, symbols in grouped.items():
                # Check if account_type exists in public_connectors
                if account_type not in self._public_connectors:
                    raise SubscriptionError(
                        f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                    )

                # Create a new subscription for this account type
                account_unsubscription = UnsubscriptionSubmit(
                    symbols=symbols,
                    data_type=unsubscription.data_type,
                    params=unsubscription.params,
                )
                match unsubscription.data_type:
                    case DataType.TRADE:
                        await self._unsubscribe_trade(
                            account_unsubscription, account_type
                        )
                    case DataType.BOOKL1:
                        await self._unsubscribe_bookl1(
                            account_unsubscription, account_type
                        )
                    case DataType.BOOKL2:
                        await self._unsubscribe_bookl2(
                            account_unsubscription, account_type
                        )
                    case DataType.KLINE:
                        await self._unsubscribe_kline(
                            account_unsubscription, account_type
                        )
                    case DataType.MARK_PRICE:
                        await self._unsubscribe_mark_price(
                            account_unsubscription, account_type
                        )
                    case DataType.FUNDING_RATE:
                        await self._unsubscribe_funding_rate(
                            account_unsubscription, account_type
                        )
                    case DataType.INDEX_PRICE:
                        await self._unsubscribe_index_price(
                            account_unsubscription, account_type
                        )
                    case DataType.VOLUME_KLINE:
                        await self._unsubscribe_volume_kline(
                            account_unsubscription, account_type
                        )

            self._unsubscribe_queue.task_done()

    async def start(self):
        """Start the subscription management system"""
        self._task_manager.create_task(self._handle_subscribe())
        self._task_manager.create_task(self._handle_unsubscribe())

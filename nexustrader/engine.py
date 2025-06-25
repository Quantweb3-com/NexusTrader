import asyncio
import platform
from typing import Dict
from collections import defaultdict
import threading
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.config import Config
from nexustrader.strategy import Strategy
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.error import EngineBuildError, SubscriptionError
from nexustrader.base import (
    ExchangeManager,
    PublicConnector,
    PrivateConnector,
    ExecutionManagementSystem,
    OrderManagementSystem,
    MockLinearConnector,
)
from nexustrader.exchange.bybit import (
    BybitExchangeManager,
    BybitPrivateConnector,
    BybitPublicConnector,
    BybitAccountType,
    BybitExecutionManagementSystem,
    BybitOrderManagementSystem,
)
from nexustrader.exchange.binance import (
    BinanceExchangeManager,
    BinanceAccountType,
    BinancePublicConnector,
    BinancePrivateConnector,
    BinanceExecutionManagementSystem,
    BinanceOrderManagementSystem,
)
from nexustrader.exchange.okx import (
    OkxExchangeManager,
    OkxAccountType,
    OkxPublicConnector,
    OkxPrivateConnector,
    OkxExecutionManagementSystem,
    OkxOrderManagementSystem,
)
from nexustrader.core.entity import TaskManager, ZeroMQSignalRecv
from nexustrader.core.nautilius_core import (
    MessageBus,
    TraderId,
    LiveClock,
    set_logging_pyo3,
    nautilus_pyo3,
    Logger,
)
from nexustrader.schema import InstrumentId
from nexustrader.constants import DataType


class Engine:
    @staticmethod
    def set_loop_policy():
        if platform.system() != "Windows":
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    def __init__(self, config: Config):
        self._config = config
        self._is_built = False
        self._scheduler_started = False
        self.set_loop_policy()
        self._loop = asyncio.new_event_loop()
        self._task_manager = TaskManager(self._loop)
        self._auto_flush_thread = None
        self._auto_flush_stop_event = threading.Event()

        self._exchanges: Dict[ExchangeType, ExchangeManager] = {}
        self._public_connectors: Dict[AccountType, PublicConnector] = {}
        self._private_connectors: Dict[AccountType, PrivateConnector] = {}

        trader_id = f"{self._config.strategy_id}-{self._config.user_id}"
        instance_id = nautilus_pyo3.UUID4().value

        self._custom_signal_recv = None

        self._msgbus = MessageBus(
            trader_id=TraderId(trader_id),
            clock=LiveClock(),
        )

        set_logging_pyo3(True)

        # Initialize logging with global reference
        self._log_guard = nautilus_pyo3.init_logging(
            trader_id=nautilus_pyo3.TraderId(trader_id),
            instance_id=nautilus_pyo3.UUID4.from_str(instance_id),
            level_stdout=nautilus_pyo3.LogLevel(self._config.log_config.level_stdout),
            level_file=nautilus_pyo3.LogLevel(self._config.log_config.level_file),
            directory=self._config.log_config.directory,
            file_name=self._config.log_config.file_name,
            file_format=self._config.log_config.file_format,
            is_colored=self._config.log_config.colors,
            print_config=self._config.log_config.print_config,
            component_levels=self._config.log_config.component_levels,
            file_rotate=(
                (
                    self._config.log_config.max_file_size,
                    self._config.log_config.max_backup_count,
                )
                if self._config.log_config.max_file_size > 0
                else None
            ),
            is_bypassed=self._config.log_config.bypass,
        )

        # Create logger instance for Engine
        self._log = Logger(type(self).__name__)

        self._cache: AsyncCache = AsyncCache(
            strategy_id=config.strategy_id,
            user_id=config.user_id,
            msgbus=self._msgbus,
            task_manager=self._task_manager,
            storage_backend=config.storage_backend,
            db_path=config.db_path,
            sync_interval=config.cache_sync_interval,
            expired_time=config.cache_expired_time,
        )

        self._registry = OrderRegistry(
            msgbus=self._msgbus,
            cache=self._cache,
            ttl_maxsize=config.cache_order_maxsize,
            ttl_seconds=config.cache_order_expired_time,
        )

        self._oms: Dict[ExchangeType, OrderManagementSystem] = {}
        self._ems: Dict[ExchangeType, ExecutionManagementSystem] = {}
        self._custom_ems: Dict[ExchangeType, ExecutionManagementSystem] = {}

        self._strategy: Strategy = config.strategy
        self._strategy._init_core(
            cache=self._cache,
            msgbus=self._msgbus,
            task_manager=self._task_manager,
            ems=self._ems,
            exchanges=self._exchanges,
            private_connectors=self._private_connectors,
            public_connectors=self._public_connectors,
            strategy_id=config.strategy_id,
            user_id=config.user_id,
        )

    def _public_connector_check(self):
        # Group connectors by exchange
        exchange_connectors = defaultdict(dict)
        for account_type, connector in self._public_connectors.items():
            exchange_id = ExchangeType(account_type.exchange_id.lower())
            exchange_connectors[exchange_id][account_type] = connector

        # Validate each exchange's connectors
        for exchange_id, connectors in exchange_connectors.items():
            exchange = self._exchanges[exchange_id]
            basic_config = self._config.basic_config.get(exchange_id)

            if not basic_config:
                raise EngineBuildError(
                    f"Basic config for {exchange_id} is not set. Please add `{exchange_id}` in `basic_config`."
                )

            # Validate each connector configuration
            for account_type in connectors.keys():
                exchange.validate_public_connector_config(account_type, basic_config)

            # Validate connector limits
            exchange.validate_public_connector_limits(connectors)

    def _build_public_connectors(self):
        for exchange_id, public_conn_configs in self._config.public_conn_config.items():
            for config in public_conn_configs:
                if exchange_id == ExchangeType.BYBIT:
                    exchange: BybitExchangeManager = self._exchanges[exchange_id]
                    account_type: BybitAccountType = config.account_type
                    public_connector = BybitPublicConnector(
                        account_type=account_type,
                        exchange=exchange,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        enable_rate_limit=config.enable_rate_limit,
                        custom_url=config.custom_url,
                    )
                    self._public_connectors[account_type] = public_connector

                elif exchange_id == ExchangeType.BINANCE:
                    exchange: BinanceExchangeManager = self._exchanges[exchange_id]
                    account_type: BinanceAccountType = config.account_type
                    public_connector = BinancePublicConnector(
                        account_type=account_type,
                        exchange=exchange,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        enable_rate_limit=config.enable_rate_limit,
                        custom_url=config.custom_url,
                    )

                    self._public_connectors[account_type] = public_connector

                elif exchange_id == ExchangeType.OKX:
                    exchange: OkxExchangeManager = self._exchanges[exchange_id]
                    account_type: OkxAccountType = config.account_type
                    exchange.set_public_connector_account_type(account_type)
                    public_connector = OkxPublicConnector(
                        account_type=account_type,
                        exchange=exchange,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        enable_rate_limit=config.enable_rate_limit,
                        custom_url=config.custom_url,
                    )
                    self._public_connectors[account_type] = public_connector
        self._public_connector_check()

    def _build_private_connectors(self):
        if self._config.is_mock:
            for (
                exchange_id,
                mock_conn_configs,
            ) in self._config.private_conn_config.items():
                if not mock_conn_configs:
                    raise EngineBuildError(
                        f"Private connector config for {exchange_id} is not set. Please add `{exchange_id}` in `private_conn_config`."
                    )
                for mock_conn_config in mock_conn_configs:
                    account_type = mock_conn_config.account_type

                    if mock_conn_config.account_type.is_linear_mock:
                        private_connector = MockLinearConnector(
                            initial_balance=mock_conn_config.initial_balance,
                            account_type=account_type,
                            exchange=self._exchanges[exchange_id],
                            msgbus=self._msgbus,
                            cache=self._cache,
                            task_manager=self._task_manager,
                            overwrite_balance=mock_conn_config.overwrite_balance,
                            overwrite_position=mock_conn_config.overwrite_position,
                            fee_rate=mock_conn_config.fee_rate,
                            quote_currency=mock_conn_config.quote_currency,
                            update_interval=mock_conn_config.update_interval,
                            leverage=mock_conn_config.leverage,
                        )
                        self._private_connectors[account_type] = private_connector
                    elif mock_conn_config.account_type.is_inverse_mock:
                        # NOTE: currently not supported
                        raise EngineBuildError(
                            f"Mock connector for {account_type} is not supported."
                        )
                    elif mock_conn_config.account_type.is_spot_mock:
                        # NOTE: currently not supported
                        raise EngineBuildError(
                            f"Mock connector for {account_type} is not supported."
                        )
                    else:
                        raise EngineBuildError(
                            f"Unsupported account type: {account_type} for mock connector."
                        )

        else:
            for (
                exchange_id,
                private_conn_configs,
            ) in self._config.private_conn_config.items():
                if not private_conn_configs:
                    raise EngineBuildError(
                        f"Private connector config for {exchange_id} is not set. Please add `{exchange_id}` in `private_conn_config`."
                    )

                match exchange_id:
                    case ExchangeType.BYBIT:
                        config = private_conn_configs[0]
                        exchange: BybitExchangeManager = self._exchanges[exchange_id]
                        account_type = (
                            BybitAccountType.UNIFIED_TESTNET
                            if exchange.is_testnet
                            else BybitAccountType.UNIFIED
                        )

                        private_connector = BybitPrivateConnector(
                            exchange=exchange,
                            account_type=account_type,
                            cache=self._cache,
                            msgbus=self._msgbus,
                            enable_rate_limit=config.enable_rate_limit,
                            task_manager=self._task_manager,
                        )
                        self._private_connectors[account_type] = private_connector

                    case ExchangeType.OKX:
                        assert len(private_conn_configs) == 1, (
                            "Only one private connector is supported for OKX, please remove the extra private connector config."
                        )

                        config = private_conn_configs[0]
                        exchange: OkxExchangeManager = self._exchanges[exchange_id]
                        account_type = (
                            OkxAccountType.DEMO
                            if exchange.is_testnet
                            else OkxAccountType.LIVE
                        )

                        private_connector = OkxPrivateConnector(
                            exchange=exchange,
                            account_type=account_type,
                            cache=self._cache,
                            msgbus=self._msgbus,
                            enable_rate_limit=config.enable_rate_limit,
                            task_manager=self._task_manager,
                        )
                        self._private_connectors[account_type] = private_connector

                    case ExchangeType.BINANCE:
                        for config in private_conn_configs:
                            exchange: BinanceExchangeManager = self._exchanges[
                                exchange_id
                            ]
                            account_type: BinanceAccountType = config.account_type

                            private_connector = BinancePrivateConnector(
                                exchange=exchange,
                                account_type=account_type,
                                cache=self._cache,
                                msgbus=self._msgbus,
                                enable_rate_limit=config.enable_rate_limit,
                                task_manager=self._task_manager,
                            )
                            self._private_connectors[account_type] = private_connector

    def _build_exchanges(self):
        for exchange_id, basic_config in self._config.basic_config.items():
            config = {
                "apiKey": basic_config.api_key,
                "secret": basic_config.secret,
                "sandbox": basic_config.testnet,
            }
            if basic_config.passphrase:
                config["password"] = basic_config.passphrase

            if exchange_id == ExchangeType.BYBIT:
                self._exchanges[exchange_id] = BybitExchangeManager(config)
            elif exchange_id == ExchangeType.BINANCE:
                self._exchanges[exchange_id] = BinanceExchangeManager(config)
            elif exchange_id == ExchangeType.OKX:
                self._exchanges[exchange_id] = OkxExchangeManager(config)

    def _build_custom_signal_recv(self):
        zmq_config = self._config.zero_mq_signal_config
        if zmq_config:
            if not hasattr(self._strategy, "on_custom_signal"):
                raise EngineBuildError(
                    "Please add `on_custom_signal` method to the strategy."
                )

            self._custom_signal_recv = ZeroMQSignalRecv(
                zmq_config, self._strategy.on_custom_signal, self._task_manager
            )

    def set_custom_ems(self, exchange_id: ExchangeType, ems_class: type) -> None:
        """
        Set a custom ExecutionManagementSystem class for a specific exchange.

        Args:
            exchange_id: The exchange type to set the custom EMS for
            ems_class: A custom EMS class that inherits from ExecutionManagementSystem
        """
        if not issubclass(ems_class, ExecutionManagementSystem):
            raise TypeError(
                "Custom EMS class must inherit from ExecutionManagementSystem"
            )
        self._custom_ems[exchange_id] = ems_class

    def _build_ems(self):
        for exchange_id in self._exchanges.keys():
            # Check if there's a custom EMS for this exchange
            if exchange_id in self._custom_ems:
                exchange = self._exchanges[exchange_id]
                self._ems[exchange_id] = self._custom_ems[exchange_id](
                    market=exchange.market,
                    cache=self._cache,
                    msgbus=self._msgbus,
                    task_manager=self._task_manager,
                    registry=self._registry,
                    is_mock=self._config.is_mock,
                )
                self._ems[exchange_id]._build(self._private_connectors)
                continue

            match exchange_id:
                case ExchangeType.BYBIT:
                    exchange: BybitExchangeManager = self._exchanges[exchange_id]
                    self._ems[exchange_id] = BybitExecutionManagementSystem(
                        market=exchange.market,
                        cache=self._cache,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                        is_mock=self._config.is_mock,
                    )
                    self._ems[exchange_id]._build(self._private_connectors)
                case ExchangeType.BINANCE:
                    exchange: BinanceExchangeManager = self._exchanges[exchange_id]
                    self._ems[exchange_id] = BinanceExecutionManagementSystem(
                        market=exchange.market,
                        cache=self._cache,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                        is_mock=self._config.is_mock,
                    )
                    self._ems[exchange_id]._build(self._private_connectors)
                case ExchangeType.OKX:
                    exchange: OkxExchangeManager = self._exchanges[exchange_id]
                    self._ems[exchange_id] = OkxExecutionManagementSystem(
                        market=exchange.market,
                        cache=self._cache,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                        is_mock=self._config.is_mock,
                    )
                    self._ems[exchange_id]._build(self._private_connectors)

    def _build_oms(self):
        for exchange_id in self._exchanges.keys():
            match exchange_id:
                case ExchangeType.BYBIT:
                    self._oms[exchange_id] = BybitOrderManagementSystem(
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                    )
                case ExchangeType.BINANCE:
                    self._oms[exchange_id] = BinanceOrderManagementSystem(
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                    )
                case ExchangeType.OKX:
                    self._oms[exchange_id] = OkxOrderManagementSystem(
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                    )

    def _build(self):
        self._build_exchanges()
        self._build_public_connectors()
        self._build_private_connectors()
        self._build_ems()
        self._build_oms()
        self._build_custom_signal_recv()
        self._is_built = True

    async def _start_connectors(self):
        for connector in self._private_connectors.values():
            await connector.connect()

        for data_type, sub in self._strategy._subscriptions.items():
            match data_type:
                case DataType.BOOKL1:
                    account_symbols = defaultdict(list)

                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        exchange = self._exchanges[instrument_id.exchange]
                        account_type = exchange.instrument_id_to_account_type(
                            instrument_id
                        )

                        account_symbols[account_type].append(instrument_id.symbol)

                    for account_type, symbols in account_symbols.items():
                        connector = self._public_connectors.get(account_type, None)
                        if connector is None:
                            raise SubscriptionError(
                                f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                            )
                        await connector.subscribe_bookl1(symbols)
                case DataType.TRADE:
                    account_symbols = defaultdict(list)

                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        exchange = self._exchanges[instrument_id.exchange]
                        account_type = exchange.instrument_id_to_account_type(
                            instrument_id
                        )
                        account_symbols[account_type].append(instrument_id.symbol)

                    for account_type, symbols in account_symbols.items():
                        connector = self._public_connectors.get(account_type, None)
                        if connector is None:
                            raise SubscriptionError(
                                f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                            )
                        await connector.subscribe_trade(symbols)
                case DataType.KLINE:
                    account_symbols = defaultdict(list)

                    for interval, symbols in sub.items():
                        for symbol in symbols:
                            instrument_id = InstrumentId.from_str(symbol)
                            exchange = self._exchanges[instrument_id.exchange]
                            account_type = exchange.instrument_id_to_account_type(
                                instrument_id
                            )
                            account_symbols[account_type].append(instrument_id.symbol)

                        for account_type, symbols in account_symbols.items():
                            connector = self._public_connectors.get(account_type, None)
                            if connector is None:
                                raise SubscriptionError(
                                    f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                                )
                            await connector.subscribe_kline(symbols, interval)
                case DataType.BOOKL2:
                    account_symbols = defaultdict(list)

                    for level, symbols in sub.items():
                        for symbol in symbols:
                            instrument_id = InstrumentId.from_str(symbol)
                            exchange = self._exchanges[instrument_id.exchange]
                            account_type = exchange.instrument_id_to_account_type(
                                instrument_id
                            )
                            account_symbols[account_type].append(instrument_id.symbol)

                        for account_type, symbols in account_symbols.items():
                            connector = self._public_connectors.get(account_type, None)
                            if connector is None:
                                raise SubscriptionError(
                                    f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                                )
                            await connector.subscribe_bookl2(symbols, level)
                case DataType.MARK_PRICE:
                    account_symbols = defaultdict(list)

                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        exchange = self._exchanges[instrument_id.exchange]
                        account_type = exchange.instrument_id_to_account_type(
                            instrument_id
                        )

                        account_symbols[account_type].append(instrument_id.symbol)

                    for account_type, symbols in account_symbols.items():
                        connector = self._public_connectors.get(account_type, None)
                        if connector is None:
                            raise SubscriptionError(
                                f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                            )
                        await connector.subscribe_mark_price(symbols)
                case DataType.FUNDING_RATE:
                    account_symbols = defaultdict(list)

                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        exchange = self._exchanges[instrument_id.exchange]
                        account_type = exchange.instrument_id_to_account_type(
                            instrument_id
                        )

                        account_symbols[account_type].append(instrument_id.symbol)

                    for account_type, symbols in account_symbols.items():
                        connector = self._public_connectors.get(account_type, None)
                        if connector is None:
                            raise SubscriptionError(
                                f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                            )
                        await connector.subscribe_funding_rate(symbols)
                case DataType.INDEX_PRICE:
                    account_symbols = defaultdict(list)

                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        exchange = self._exchanges[instrument_id.exchange]
                        account_type = exchange.instrument_id_to_account_type(
                            instrument_id
                        )

                        account_symbols[account_type].append(instrument_id.symbol)

                    for account_type, symbols in account_symbols.items():
                        connector = self._public_connectors.get(account_type, None)
                        if connector is None:
                            raise SubscriptionError(
                                f"Please add `{account_type}` public connector to the `config.public_conn_config`."
                            )
                        await connector.subscribe_index_price(symbols)

    async def _start_ems(self):
        for ems in self._ems.values():
            await ems.start()

    async def _start_oms(self):
        for oms in self._oms.values():
            await oms.start()

    def _start_scheduler(self):
        self._strategy._scheduler.start()
        self._scheduler_started = True

    def _start_auto_flush_thread(self):
        if self._config.log_config.auto_flush_sec > 0:
            self._log.debug(
                f"Starting auto flush thread with interval: {self._config.log_config.auto_flush_sec}s"
            )
            self._auto_flush_thread = threading.Thread(
                target=self._auto_flush_worker, daemon=True
            )
            self._auto_flush_thread.start()
        else:
            self._log.debug("Auto flush disabled (auto_flush_sec = 0)")

    def _auto_flush_worker(self):
        self._log.debug("Auto flush worker thread started")
        while not self._auto_flush_stop_event.wait(
            self._config.log_config.auto_flush_sec
        ):
            self._log.debug("Performing auto logger flush")
            nautilus_pyo3.logger_flush()
        self._log.debug("Auto flush worker thread stopped")

    async def _start(self):
        await self._cache.start()  # NOTE: this must be the first thing to call
        await self._start_oms()
        await self._start_ems()
        await self._start_connectors()
        if self._custom_signal_recv:
            await self._custom_signal_recv.start()
        self._start_scheduler()
        self._start_auto_flush_thread()
        await self._task_manager.wait()

    async def _dispose(self):
        if self._scheduler_started:
            try:
                # Remove all jobs first to prevent new executions
                self._strategy._scheduler.remove_all_jobs()
                # Short delay to allow running jobs to complete
                await asyncio.sleep(0.05)
                # Shutdown without waiting for jobs to complete
                self._strategy._scheduler.shutdown(wait=False)
            except (asyncio.CancelledError, RuntimeError):
                # Suppress expected shutdown exceptions
                pass

        # Stop auto flush thread
        if self._auto_flush_thread and self._auto_flush_thread.is_alive():
            self._log.debug("Stopping auto flush thread")
            self._auto_flush_stop_event.set()
            self._auto_flush_thread.join(timeout=0.1)
            if self._auto_flush_thread.is_alive():
                self._log.warning("Auto flush thread did not stop within timeout")
            else:
                self._log.debug("Auto flush thread stopped successfully")

        for connector in self._public_connectors.values():
            await connector.disconnect()
        for connector in self._private_connectors.values():
            await connector.disconnect()

        await asyncio.sleep(0.1)  # NOTE: wait for the websocket to disconnect

        await self._task_manager.cancel()
        await self._cache.close()

    def start(self):
        self._build()
        self._strategy._on_start()
        self._loop.run_until_complete(self._start())

    def dispose(self):
        self._strategy._on_stop()
        self._loop.run_until_complete(self._dispose())
        self._loop.close()
        nautilus_pyo3.logger_flush()

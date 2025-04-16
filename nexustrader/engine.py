import asyncio
import platform
from typing import Dict
from collections import defaultdict
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
from nexustrader.core.nautilius_core import MessageBus, TraderId, LiveClock
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

        self._exchanges: Dict[ExchangeType, ExchangeManager] = {}
        self._public_connectors: Dict[AccountType, PublicConnector] = {}
        self._private_connectors: Dict[AccountType, PrivateConnector] = {}

        trader_id = f"{self._config.strategy_id}-{self._config.user_id}"

        self._custom_signal_recv = None

        self._msgbus = MessageBus(
            trader_id=TraderId(trader_id),
            clock=LiveClock(),
        )
        
        self._registry = OrderRegistry()
        
        self._cache: AsyncCache = AsyncCache(
            strategy_id=config.strategy_id,
            user_id=config.user_id,
            msgbus=self._msgbus,
            task_manager=self._task_manager,
            registry=self._registry,
            storage_backend=config.storage_backend,
            db_path=config.db_path,
            sync_interval=config.cache_sync_interval,
            expired_time=config.cache_expired_time,
        )


        self._oms: Dict[ExchangeType, OrderManagementSystem] = {}
        self._ems: Dict[ExchangeType, ExecutionManagementSystem] = {}

        self._strategy: Strategy = config.strategy
        self._strategy._init_core(
            cache=self._cache,
            msgbus=self._msgbus,
            task_manager=self._task_manager,
            ems=self._ems,
            exchanges=self._exchanges,
            private_connectors=self._private_connectors,
            public_connectors=self._public_connectors,
        )

    def _public_connector_check(self):
        okx_public_conn_count = 0

        for account_type in self._public_connectors.keys():
            if isinstance(account_type, BybitAccountType):
                if (
                    account_type == BybitAccountType.UNIFIED
                    or account_type == BybitAccountType.UNIFIED_TESTNET
                ):
                    raise EngineBuildError(
                        f"{account_type} is not supported for public connector."
                    )
                bybit_basic_config = self._config.basic_config.get(ExchangeType.BYBIT)
                if not bybit_basic_config:
                    raise EngineBuildError(
                        f"Basic config for {ExchangeType.BYBIT} is not set. Please add `{ExchangeType.BYBIT}` in `basic_config`."
                    )

                else:
                    if bybit_basic_config.testnet != account_type.is_testnet:
                        raise EngineBuildError(
                            f"The `testnet` setting of {ExchangeType.BYBIT} is not consistent with the public connector's account type `{account_type}`."
                        )
            elif isinstance(account_type, BinanceAccountType):
                if (
                    account_type.is_isolated_margin_or_margin
                    or account_type.is_portfolio_margin
                ):
                    raise EngineBuildError(
                        f"{account_type} is not supported for public connector."
                    )
                binance_basic_config = self._config.basic_config.get(
                    ExchangeType.BINANCE
                )
                if not binance_basic_config:
                    raise EngineBuildError(
                        f"Basic config for {ExchangeType.BINANCE} is not set. Please add `{ExchangeType.BINANCE}` in `basic_config`."
                    )
                else:
                    if binance_basic_config.testnet != account_type.is_testnet:
                        raise EngineBuildError(
                            f"The `testnet` setting of {ExchangeType.BINANCE} is not consistent with the public connector's account type `{account_type}`."
                        )

            elif isinstance(account_type, OkxAccountType):
                if okx_public_conn_count > 1:
                    raise EngineBuildError(
                        "Only one public connector is supported for OKX, please remove the extra public connector config."
                    )
                okx_basic_config = self._config.basic_config.get(ExchangeType.OKX)
                if not okx_basic_config:
                    raise EngineBuildError(
                        f"Basic config for {ExchangeType.OKX} is not set. Please add `{ExchangeType.OKX}` in `basic_config`."
                    )
                else:
                    if okx_basic_config.testnet != account_type.is_testnet:
                        raise EngineBuildError(
                            f"The `testnet` setting of {ExchangeType.OKX} is not consistent with the public connector's account type `{account_type}`."
                        )

                okx_public_conn_count += 1
            else:
                raise EngineBuildError(f"Unsupported account type: {account_type}")

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
                        rate_limit=config.rate_limit,
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
                        rate_limit=config.rate_limit,
                        custom_url=config.custom_url,
                    )

                    self._public_connectors[account_type] = public_connector

                elif exchange_id == ExchangeType.OKX:
                    exchange: OkxExchangeManager = self._exchanges[exchange_id]
                    account_type: OkxAccountType = config.account_type
                    public_connector = OkxPublicConnector(
                        account_type=account_type,
                        exchange=exchange,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        rate_limit=config.rate_limit,
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
                        #NOTE: currently not supported
                        pass
                    elif mock_conn_config.account_type.is_spot_mock:
                        #NOTE: currently not supported
                        pass
                    else:
                        raise EngineBuildError(f"Unsupported account type: {account_type} for mock connector.")
            
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
                            rate_limit=config.rate_limit,
                            task_manager=self._task_manager,
                        )
                        self._private_connectors[account_type] = private_connector

                    case ExchangeType.OKX:
                        assert (
                            len(private_conn_configs) == 1
                        ), "Only one private connector is supported for OKX, please remove the extra private connector config."

                        config = private_conn_configs[0]
                        exchange: OkxExchangeManager = self._exchanges[exchange_id]
                        account_type = (
                            OkxAccountType.DEMO if exchange.is_testnet else OkxAccountType.LIVE
                        )

                        private_connector = OkxPrivateConnector(
                            exchange=exchange,
                            account_type=account_type,
                            cache=self._cache,
                            msgbus=self._msgbus,
                            rate_limit=config.rate_limit,
                            task_manager=self._task_manager,
                        )
                        self._private_connectors[account_type] = private_connector

                    case ExchangeType.BINANCE:
                        for config in private_conn_configs:
                            exchange: BinanceExchangeManager = self._exchanges[exchange_id]
                            account_type: BinanceAccountType = config.account_type

                            private_connector = BinancePrivateConnector(
                                exchange=exchange,
                                account_type=account_type,
                                cache=self._cache,
                                msgbus=self._msgbus,
                                rate_limit=config.rate_limit,
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

    def _build_ems(self):
        for exchange_id in self._exchanges.keys():
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
                        cache=self._cache,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                    )
                case ExchangeType.BINANCE:
                    self._oms[exchange_id] = BinanceOrderManagementSystem(
                        cache=self._cache,
                        msgbus=self._msgbus,
                        task_manager=self._task_manager,
                        registry=self._registry,
                    )
                case ExchangeType.OKX:
                    self._oms[exchange_id] = OkxOrderManagementSystem(
                        cache=self._cache,
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

    def _instrument_id_to_account_type(
        self, instrument_id: InstrumentId
    ) -> AccountType:
        match instrument_id.exchange:
            case ExchangeType.BYBIT:
                bybit_basic_config = self._config.basic_config.get(ExchangeType.BYBIT)
                if not bybit_basic_config:
                    raise EngineBuildError(
                        f"Basic config for {ExchangeType.BYBIT} is not set. Please add `{ExchangeType.BYBIT}` in `basic_config`."
                    )

                is_testnet = bybit_basic_config.testnet

                if instrument_id.is_spot:
                    return (
                        BybitAccountType.SPOT_TESTNET
                        if is_testnet
                        else BybitAccountType.SPOT
                    )
                elif instrument_id.is_linear:
                    return (
                        BybitAccountType.LINEAR_TESTNET
                        if is_testnet
                        else BybitAccountType.LINEAR
                    )
                elif instrument_id.is_inverse:
                    return (
                        BybitAccountType.INVERSE_TESTNET
                        if is_testnet
                        else BybitAccountType.INVERSE
                    )
                else:
                    raise ValueError(
                        f"Unsupported instrument type: {instrument_id.type}"
                    )
            case ExchangeType.BINANCE:
                binance_basic_config = self._config.basic_config.get(
                    ExchangeType.BINANCE
                )
                if not binance_basic_config:
                    raise EngineBuildError(
                        f"Basic config for {ExchangeType.BINANCE} is not set. Please add `{ExchangeType.BINANCE}` in `basic_config`."
                    )

                is_testnet = binance_basic_config.testnet

                if instrument_id.is_spot:
                    return (
                        BinanceAccountType.SPOT_TESTNET
                        if is_testnet
                        else BinanceAccountType.SPOT
                    )
                elif instrument_id.is_linear:
                    return (
                        BinanceAccountType.USD_M_FUTURE_TESTNET
                        if is_testnet
                        else BinanceAccountType.USD_M_FUTURE
                    )
                elif instrument_id.is_inverse:
                    return (
                        BinanceAccountType.COIN_M_FUTURE_TESTNET
                        if is_testnet
                        else BinanceAccountType.COIN_M_FUTURE
                    )
                else:
                    raise ValueError(
                        f"Unsupported instrument type: {instrument_id.type}"
                    )
            case ExchangeType.OKX:
                account_types = self._config.public_conn_config.get(ExchangeType.OKX)
                if not account_types:
                    raise EngineBuildError(
                        f"Public connector config for {ExchangeType.OKX} is not set. Please add `{ExchangeType.OKX}` in `public_conn_config`."
                    )

                return account_types[0].account_type

    async def _start_connectors(self):
        for connector in self._private_connectors.values():
            await connector.connect()
        
        for data_type, sub in self._strategy._subscriptions.items():
            match data_type:
                case DataType.BOOKL1:
                    account_symbols = defaultdict(list)
                    
                    for symbol in sub:
                        instrument_id = InstrumentId.from_str(symbol)
                        account_type = self._instrument_id_to_account_type(
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
                        account_type = self._instrument_id_to_account_type(
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
                            account_type = self._instrument_id_to_account_type(
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
                            account_type = self._instrument_id_to_account_type(
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
                    pass  # TODO: implement
                case DataType.FUNDING_RATE:
                    pass  # TODO: implement
                case DataType.INDEX_PRICE:
                    pass  # TODO: implement

    async def _start_ems(self):
        for ems in self._ems.values():
            await ems.start()

    async def _start_oms(self):
        for oms in self._oms.values():
            await oms.start()

    def _start_scheduler(self):
        self._strategy._scheduler.start()
        self._scheduler_started = True

    async def _start(self):
        await self._cache.start() #NOTE: this must be the first thing to call
        await self._start_oms()
        await self._start_ems()
        await self._start_connectors()
        if self._custom_signal_recv:
            await self._custom_signal_recv.start()
        self._start_scheduler()
        await self._task_manager.wait()

    async def _dispose(self):
        if self._scheduler_started:
            self._strategy._scheduler.shutdown()
        for connector in self._public_connectors.values():
            await connector.disconnect()
        for connector in self._private_connectors.values():
            await connector.disconnect()
            
        await asyncio.sleep(0.1) #NOTE: wait for the websocket to disconnect

        await self._task_manager.cancel()
        await self._cache.close()

    def start(self):
        self._build()
        self._strategy.on_start()
        self._loop.run_until_complete(self._start())

    def dispose(self):
        self._loop.run_until_complete(self._dispose())
        self._loop.close()

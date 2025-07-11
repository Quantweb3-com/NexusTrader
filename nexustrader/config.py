from dataclasses import dataclass, field
from typing import Dict, List, Literal
from nexustrader.constants import AccountType, ExchangeType, StorageType
from nexustrader.strategy import Strategy
from zmq.asyncio import Socket


@dataclass
class LogConfig:
    """LogConfig for NexusTrader logging system.

    Attributes:
        level_stdout: The minimum log level to write to stdout (default INFO)
        level_file: The minimum log level to write to a file (default OFF)
        directory: Path to log file directory (uses current directory if None)
        file_name: Custom log file name (with .log or .json suffix)
        file_format: Log file format, 'JSON' for JSON format, None for plain text
        colors: Whether to use ANSI color codes in log output
        print_config: Whether to print logging config on initialization
        component_levels: Per-component log level filters
        max_file_size: Maximum size of log files in bytes before rotation (0 disables rotation)
        max_backup_count: Maximum number of backup log files to keep when rotating
    """

    level_stdout: Literal["DEBUG", "INFO", "WARNING", "ERROR", "OFF", "TRACE"] = "INFO"
    level_file: Literal["DEBUG", "INFO", "WARNING", "ERROR", "OFF", "TRACE"] = "OFF"
    directory: str | None = None
    file_name: str | None = None
    file_format: str | None = None
    colors: bool = True
    print_config: bool = False  # Changed to match default in documentation
    component_levels: Dict[str, str] = field(default_factory=dict)
    max_file_size: int = 0
    max_backup_count: int = 5
    bypass: bool = False  # Added missing field
    auto_flush_sec: int = (
        0  # Auto flush interval in seconds, 0 means disabled, minimum 5 seconds
    )

    def __post_init__(self):
        if self.level_stdout not in [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "OFF",
            "TRACE",
        ]:
            raise ValueError(
                f"Invalid level_stdout: {self.level_stdout}. Must be one of DEBUG, INFO, WARNING, ERROR, OFF, TRACE."
            )
        if self.level_file not in ["DEBUG", "INFO", "WARNING", "ERROR", "OFF", "TRACE"]:
            raise ValueError(
                f"Invalid level_file: {self.level_file}. Must be one of DEBUG, INFO, WARNING, ERROR, OFF, TRACE."
            )

        # If file logging is disabled, set auto_flush_sec to 0
        if self.level_file == "OFF":
            self.auto_flush_sec = 0

        if self.file_format is not None and self.file_format != "JSON":
            raise ValueError("file_format must be None or 'JSON'")

        if self.max_file_size < 0:
            raise ValueError("max_file_size must be non-negative")

        if self.max_backup_count < 0:
            raise ValueError("max_backup_count must be non-negative")

        if self.auto_flush_sec < 0:
            raise ValueError("auto_flush_sec must be non-negative")

        if self.auto_flush_sec > 0 and self.auto_flush_sec < 5:
            raise ValueError("auto_flush_sec must be at least 5 seconds when enabled")


@dataclass
class BasicConfig:
    api_key: str
    secret: str
    testnet: bool = False
    passphrase: str = None


@dataclass
class PublicConnectorConfig:
    account_type: AccountType
    enable_rate_limit: bool = True
    custom_url: str | None = None


@dataclass
class PrivateConnectorConfig:
    account_type: AccountType
    enable_rate_limit: bool = True


@dataclass
class ZeroMQSignalConfig:
    """ZeroMQ Signal Configuration Class.

    Used to configure the ZeroMQ subscriber socket to receive custom trade signals.

    Attributes:
        socket (`zmq.asyncio.Socket`): ZeroMQ asynchronous socket object

    Example:
        >>> from zmq.asyncio import Context
        >>> context = Context()
        >>> socket = context.socket(zmq.SUB)
        >>> socket.connect("ipc:///tmp/zmq_custom_signal")
        >>> socket.setsockopt(zmq.SUBSCRIBE, b"")
        >>> config = ZeroMQSignalConfig(socket=socket)
    """

    socket: Socket


@dataclass
class MockConnectorConfig:
    initial_balance: Dict[str, float | int]
    account_type: AccountType
    fee_rate: float = 0.0005
    quote_currency: str = "USDT"
    overwrite_balance: bool = False
    overwrite_position: bool = False
    update_interval: int = 60
    leverage: float = 1.0

    def __post_init__(self):
        if not self.account_type.is_mock:
            raise ValueError(
                f"Invalid account type: {self.account_type} for mock connector. Must be `LINEAR_MOCK`, `INVERSE_MOCK`, or `SPOT_MOCK`."
            )


@dataclass
class Config:
    """
    Represents the configuration for a trading system.

    This class holds all necessary configuration information including strategy details,
    exchange configurations, connector setups, database settings, and logging preferences.

    Attributes:
        strategy_id (str): Unique identifier for the strategy.
        user_id (str): Identifier for the user running the strategy.
        strategy (Strategy): The trading strategy to be executed.
        basic_config (Dict[ExchangeType, BasicConfig]): Basic configuration for each exchange.
        public_conn_config (Dict[ExchangeType, List[PublicConnectorConfig]]): Public connector configurations by exchange.
        private_conn_config (Dict[ExchangeType, List[PrivateConnectorConfig | MockConnectorConfig]]):
            Private connector configurations by exchange, can include mock connectors.
        zero_mq_signal_config (ZeroMQSignalConfig | None): Configuration for ZeroMQ signal, if used.
        db_path (str): Path to the database file. Defaults to ".keys/cache.db".
        storage_backend (StorageType): Type of storage backend to use. Defaults to SQLITE.
        cache_sync_interval (int): Interval in seconds for cache synchronization. Defaults to 60.
        cache_expired_time (int): Time in seconds after which cache entries expire. Defaults to 3600.
        cache_order_maxsize (int): Maximum size for the order registry cache. Defaults to 72000.
        cache_order_expired_time (int): Time in seconds after which order registry cache entries expire. Defaults to 3600. If you have order longer than 1 hour to close, you should set this to a larger value.
        is_mock (bool): Flag indicating if the system is running in mock mode. Defaults to False.
        log_config (LogConfig): Configuration for logging. Defaults to a new LogConfig instance.
        enable_cli (bool): Flag to enable command-line interface. Defaults to False.

    Notes:
        The __post_init__ method enforces that you cannot mix mock and real private connectors.
        Either all private connectors must be mock or all must be real.
    """

    strategy_id: str
    user_id: str
    strategy: Strategy
    basic_config: Dict[ExchangeType, BasicConfig]
    public_conn_config: Dict[ExchangeType, List[PublicConnectorConfig]]
    private_conn_config: Dict[
        ExchangeType, List[PrivateConnectorConfig | MockConnectorConfig]
    ] = field(default_factory=dict)
    zero_mq_signal_config: ZeroMQSignalConfig | None = None
    db_path: str = ".keys/cache.db"
    storage_backend: StorageType = StorageType.SQLITE
    cache_sync_interval: int = 60
    cache_expired_time: int = 3600
    cache_order_maxsize: int = (
        72000  # cache maxsize for order registry in cache order expired time
    )
    cache_order_expired_time: int = 3600  # cache expired time for order registry
    is_mock: bool = False
    log_config: LogConfig = field(default_factory=LogConfig)
    enable_cli: bool = False

    def __post_init__(self):
        # Check if any connector is mock, then all must be mock
        has_mock = False
        has_private = False

        for connectors in self.private_conn_config.values():
            for connector in connectors:
                if isinstance(connector, MockConnectorConfig):
                    has_mock = True
                elif isinstance(connector, PrivateConnectorConfig):
                    has_private = True

                if has_mock and has_private:
                    raise ValueError(
                        "Cannot mix mock and real private connectors. Use either all mock or all private connectors."
                    )

        self.is_mock = has_mock

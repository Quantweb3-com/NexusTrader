from dataclasses import dataclass, field
from typing import Dict, List
from nexustrader.constants import AccountType, ExchangeType, StorageBackend
from nexustrader.core.entity import RateLimit
from nexustrader.strategy import Strategy
from zmq.asyncio import Socket


@dataclass
class BasicConfig:
    api_key: str
    secret: str
    testnet: bool = False
    passphrase: str = None


@dataclass
class PublicConnectorConfig:
    account_type: AccountType
    rate_limit: RateLimit | None = None
    custom_url: str | None = None


@dataclass
class PrivateConnectorConfig:
    account_type: AccountType
    rate_limit: RateLimit | None = None


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
    storage_backend: StorageBackend = StorageBackend.SQLITE
    cache_sync_interval: int = 60
    cache_expired_time: int = 3600
    cache_order_maxsize: int = (
        72000  # cache maxsize for order registry in cache order expired time
    )
    cache_order_expired_time: int = 3600  # cache expired time for order registry
    is_mock: bool = False

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

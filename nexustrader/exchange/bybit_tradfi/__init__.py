"""
Bybit TradeFi (MetaTrader5) connector for NexusTrader.

This package is intentionally structured so that:
1. Importing this package does NOT import ``MetaTrader5``.
   The MT5 package is only imported when a connector actually calls
   ``BybitTradeFiPrivateConnector.connect()``.

2. Users who do not configure a BYBIT_TRADFI exchange in their ``Config``
   are completely unaffected – this package is never loaded.

3. On non-Windows platforms the package imports cleanly; the runtime
   platform check happens in ``_mt5_bridge.py`` when MT5 is first accessed.

Typical usage
-------------
::

    from nexustrader.exchange.bybit_tradfi import (
        BybitTradeFiAccountType,
    )
    from nexustrader.constants import ExchangeType
    from nexustrader.config import BasicConfig, PublicConnectorConfig, PrivateConnectorConfig

    config = Config(
        strategy=MyStrategy(),
        basic_config={
            ExchangeType.BYBIT_TRADFI: BasicConfig(
                api_key="12345678",       # MT5 login number
                secret="my_password",    # MT5 password
                passphrase="BybitBroker-Demo",  # MT5 server
                testnet=True,            # demo account
            )
        },
        public_conn_config={
            ExchangeType.BYBIT_TRADFI: [
                PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
            ]
        },
        private_conn_config={
            ExchangeType.BYBIT_TRADFI: [
                PrivateConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)
            ]
        },
    )
"""

from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.connector import (
    BybitTradeFiPrivateConnector,
    BybitTradeFiPublicConnector,
)
from nexustrader.exchange.bybit_tradfi.ems import BybitTradeFiExecutionManagementSystem
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager
from nexustrader.exchange.bybit_tradfi.factory import BybitTradeFiFactory
from nexustrader.exchange.bybit_tradfi.oms import BybitTradeFiOrderManagementSystem

__all__ = [
    "BybitTradeFiAccountType",
    "BybitTradeFiExchangeManager",
    "BybitTradeFiPublicConnector",
    "BybitTradeFiPrivateConnector",
    "BybitTradeFiOrderManagementSystem",
    "BybitTradeFiExecutionManagementSystem",
    "BybitTradeFiFactory",
]

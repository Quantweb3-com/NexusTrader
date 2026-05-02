"""
ExchangeFactory for Bybit TradeFi (MT5).

The factory is auto-discovered by the ExchangeRegistry when the
``nexustrader.exchange.bybit_tradfi`` package is imported.
"""

from __future__ import annotations

from typing import Optional

from nexustrader.config import (
    BasicConfig,
    PrivateConnectorConfig,
    PublicConnectorConfig,
)
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.exchange.base_factory import BuildContext, ExchangeFactory
from nexustrader.exchange.bybit_tradfi.constants import BybitTradeFiAccountType
from nexustrader.exchange.bybit_tradfi.connector import (
    BybitTradeFiPrivateConnector,
    BybitTradeFiPublicConnector,
)
from nexustrader.exchange.bybit_tradfi.ems import BybitTradeFiExecutionManagementSystem
from nexustrader.exchange.bybit_tradfi.exchange import BybitTradeFiExchangeManager


class BybitTradeFiFactory(ExchangeFactory):
    """Factory that creates all MT5 components for the Bybit TradeFi connector."""

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BYBIT_TRADFI

    # ------------------------------------------------------------------
    # ExchangeManager
    # ------------------------------------------------------------------

    def create_manager(self, basic_config: BasicConfig) -> BybitTradeFiExchangeManager:
        """
        Build the ExchangeManager.

        ``BasicConfig`` field mapping for MT5:
            api_key    → MT5 account login number (string → converted to int)
            secret     → MT5 account password
            passphrase → MT5 broker server name  (e.g. "BybitBroker-Demo")
            testnet    → True for demo accounts
        """
        login_str = basic_config.api_key or ""
        try:
            login = int(login_str)
        except ValueError:
            login = 0

        config = {
            "login": login,
            "password": basic_config.secret or "",
            "server": basic_config.passphrase or "",
            "sandbox": basic_config.testnet,
            "exchange_id": "bybit_tradfi",
        }
        return BybitTradeFiExchangeManager(config)

    # ------------------------------------------------------------------
    # PublicConnector
    # ------------------------------------------------------------------

    def create_public_connector(
        self,
        config: PublicConnectorConfig,
        exchange: BybitTradeFiExchangeManager,
        context: BuildContext,
    ) -> BybitTradeFiPublicConnector:
        kwargs = {}
        if config.tick_poll_interval is not None:
            kwargs["tick_poll_interval"] = config.tick_poll_interval
        return BybitTradeFiPublicConnector(
            account_type=config.account_type,
            exchange=exchange,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # PrivateConnector
    # ------------------------------------------------------------------

    def create_private_connector(
        self,
        config: PrivateConnectorConfig,
        exchange: BybitTradeFiExchangeManager,
        context: BuildContext,
        account_type: Optional[AccountType] = None,
    ) -> BybitTradeFiPrivateConnector:
        at = account_type or self.get_private_account_type(exchange, config)
        return BybitTradeFiPrivateConnector(
            account_type=at,
            exchange=exchange,
            cache=context.cache,
            registry=context.registry,
            clock=context.clock,
            msgbus=context.msgbus,
            task_manager=context.task_manager,
        )

    # ------------------------------------------------------------------
    # EMS
    # ------------------------------------------------------------------

    def create_ems(
        self,
        exchange: BybitTradeFiExchangeManager,
        context: BuildContext,
    ) -> BybitTradeFiExecutionManagementSystem:
        return BybitTradeFiExecutionManagementSystem(
            exchange=exchange,
            cache=context.cache,
            msgbus=context.msgbus,
            clock=context.clock,
            task_manager=context.task_manager,
            registry=context.registry,
            is_mock=context.is_mock,
        )

    # ------------------------------------------------------------------
    # Account type helpers
    # ------------------------------------------------------------------

    def get_private_account_type(
        self, exchange: BybitTradeFiExchangeManager, config: PrivateConnectorConfig
    ) -> BybitTradeFiAccountType:
        if isinstance(config.account_type, BybitTradeFiAccountType):
            return config.account_type
        # Derive from testnet flag on the exchange manager
        return (
            BybitTradeFiAccountType.DEMO
            if exchange.is_testnet
            else BybitTradeFiAccountType.LIVE
        )

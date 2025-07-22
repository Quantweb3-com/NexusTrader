from nexustrader.exchange.hpyerliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hpyerliquid.websockets import HyperLiquidWSClient
from nexustrader.exchange.hpyerliquid.constanst import HyperLiquidAccountType

from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.base import PublicConnector, PrivateConnector


class HyperLiquidPublicConnector(PublicConnector):
    _ws_client: HyperLiquidWSClient
    _account_type: HyperLiquidAccountType

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        exchange: HyperLiquidExchangeManager,
        msgbus: MessageBus,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=HyperLiquidWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                custom_url=custom_url,
            ),
            msgbus=msgbus,
            task_manager=task_manager,
        )

    def _ws_msg_handler(self, raw: bytes):
        pass

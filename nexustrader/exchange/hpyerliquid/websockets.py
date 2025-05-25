from typing import Any, Callable, List
from aiolimiter import AsyncLimiter

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.exchange.hpyerliquid.constanst import HyperLiquidAccountType


class HyperLiquidWSClient(WSClient):
    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        api_key: str = None,  # In HyperLiquid, api key is the address of the account
    ):
        self._account_type = account_type

from nexustrader.base import OrderManagementSystem
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry


class BinanceOrderManagementSystem(OrderManagementSystem):
    def __init__(
        self,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
    ):
        super().__init__(cache, msgbus, task_manager, registry)
        self._msgbus.register(endpoint="binance.order", handler=self._add_order_msg)
        # self._msgbus.subscribe(topic="binance.position", handler=self._add_position_msg)

    #TODO: some rest-api check logic

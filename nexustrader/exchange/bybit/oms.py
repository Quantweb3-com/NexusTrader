from nexustrader.base import OrderManagementSystem
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry


class BybitOrderManagementSystem(OrderManagementSystem):
    def __init__(
        self,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
    ):
        super().__init__(msgbus, task_manager, registry)
        self._msgbus.register(endpoint="bybit.order", handler=self._add_order_msg)

    # TODO: some rest-api check logic

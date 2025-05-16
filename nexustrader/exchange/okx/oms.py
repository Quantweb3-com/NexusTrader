from nexustrader.base import OrderManagementSystem
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager
from nexustrader.core.registry import OrderRegistry


class OkxOrderManagementSystem(OrderManagementSystem):
    def __init__(
        self,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
    ):
        super().__init__(msgbus, task_manager, registry)
        self._msgbus.register(endpoint="okx.order", handler=self._add_order_msg)

    # TODO: some rest-api check logic

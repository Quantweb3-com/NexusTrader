import asyncio
from abc import ABC

from nexustrader.schema import Order
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus, Logger
from nexustrader.core.registry import OrderRegistry


class OrderManagementSystem(ABC):
    def __init__(
        self,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
    ):
        self._log = Logger(name=type(self).__name__)
        self._msgbus = msgbus
        self._task_manager = task_manager
        self._registry = registry
        self._order_msg_queue: asyncio.Queue[Order] = asyncio.Queue()

    def _add_order_msg(self, order: Order):
        """
        Add an order to the order message queue
        """
        self._order_msg_queue.put_nowait(order)

    async def _handle_order_event(self):
        """
        Handle the order event
        """
        while True:
            try:
                order = await self._order_msg_queue.get()

                # handle the ACCEPTED, PARTIALLY_FILLED, CANCELED, FILLED, EXPIRED arived early than the order submit uuid
                uuid = self._registry.get_uuid(
                    order.id
                )  # check if the order id is registered
                if not uuid:
                    self._log.debug(f"WAIT FOR ORDER ID: {order.id} TO BE REGISTERED")
                    self._registry.add_to_waiting(order)
                else:
                    order.uuid = uuid
                    self._registry.order_status_update(order)
                self._order_msg_queue.task_done()
            except Exception as e:
                self._log.error(f"Error in handle_order_event: {e}")

    async def start(self):
        """
        Start the order management system
        """
        self._log.debug("OrderManagementSystem started")
        self._task_manager.create_task(self._handle_order_event())

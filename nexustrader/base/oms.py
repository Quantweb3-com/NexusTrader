import asyncio
from abc import ABC

from nexustrader.schema import Order
from nexustrader.core.log import SpdLog
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.cache import AsyncCache
from nexustrader.core.registry import OrderRegistry
from nexustrader.constants import OrderStatus



class OrderManagementSystem(ABC):
    def __init__(
        self,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
        order_submit_timeout: float | None = 10,
    ):
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="DEBUG", flush=True
        )
        self._cache = cache
        self._msgbus = msgbus
        self._task_manager = task_manager
        self._registry = registry
        self._order_submit_timeout = order_submit_timeout
        self._order_msg_queue: asyncio.Queue[Order] = asyncio.Queue()
        self._waiting_order_msg_queue: asyncio.Queue[Order] = asyncio.Queue()

    def _add_order_msg(self, order: Order):
        """
        Add an order to the order message queue
        """
        self._order_msg_queue.put_nowait(order)
        
    
    def _order_status_update(self, order: Order):
        match order.status:
            case OrderStatus.ACCEPTED:
                self._log.debug(f"ORDER STATUS ACCEPTED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="accepted", msg=order)
            case OrderStatus.PARTIALLY_FILLED:
                self._log.debug(f"ORDER STATUS PARTIALLY FILLED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="partially_filled", msg=order)
            case OrderStatus.CANCELED:
                self._log.debug(f"ORDER STATUS CANCELED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="canceled", msg=order)
                # self._registry.remove_order(order) #NOTE: order remove should be handle separately
            case OrderStatus.FILLED:
                self._log.debug(f"ORDER STATUS FILLED: {str(order)}")
                self._cache._order_status_update(order)
                self._msgbus.send(endpoint="filled", msg=order)
                # self._registry.remove_order(order) #NOTE: order remove should be handle separately
            case OrderStatus.EXPIRED:
                self._log.debug(f"ORDER STATUS EXPIRED: {str(order)}")
                self._cache._order_status_update(order)
            case _:
                self._log.error(f"ORDER STATUS UNKNOWN: {str(order)}")
    
    async def _handle_waiting_order_event(self):
        """
        Handle the waiting order message
        """
        while True:
            try:
                order = await self._waiting_order_msg_queue.get()
                timeout = await self._registry.wait_for_order_id(order.id, self._order_submit_timeout)
                if not timeout:
                    uuid = self._registry.get_uuid(order.id)
                    order.uuid = uuid
                    self._order_status_update(order)
                self._waiting_order_msg_queue.task_done()
            except Exception as e:
                self._log.error(f"Error in handle_waiting_order_event: {e}")
    

    async def _handle_order_event(self):
        """
        Handle the order event
        """
        while True:
            try:
                order = await self._order_msg_queue.get()

                # handle the ACCEPTED, PARTIALLY_FILLED, CANCELED, FILLED, EXPIRED arived early than the order submit uuid
                uuid = self._registry.get_uuid(order.id) # check if the order id is registered
                if not uuid:
                    self._log.debug(f"WAIT FOR ORDER ID: {order.id} TO BE REGISTERED")
                    self._registry.add_to_waiting(order.id)
                    await self._waiting_order_msg_queue.put(order)
                    # await self._registry.wait_for_order_id(order.id) #NOTE: need to wait for the order id to be registered
                    # uuid = self._registry.get_uuid(order.id)
                else:
                    order.uuid = uuid
                    self._order_status_update(order)
                self._order_msg_queue.task_done()
            except Exception as e:
                self._log.error(f"Error in handle_order_event: {e}")

    async def start(self):
        """
        Start the order management system
        """
        self._log.debug("OrderManagementSystem started")

        # Start order and position event handlers
        self._task_manager.create_task(self._handle_waiting_order_event())
        self._task_manager.create_task(self._handle_order_event())

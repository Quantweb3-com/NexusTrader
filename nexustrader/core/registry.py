import asyncio
from typing import Optional
from nexustrader.core.log import SpdLog
from nexustrader.schema import Order
from typing import Dict

class OrderRegistry:
    def __init__(self):
        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="DEBUG", flush=True
        )
        self._uuid_to_order_id = {}
        self._order_id_to_uuid = {}
        self._futures: Dict[str, asyncio.Future] = {}

    def register_order(self, order: Order) -> None:
        """Register a new order ID to UUID mapping"""
        self._uuid_to_order_id[order.uuid] = order.id
        self._order_id_to_uuid[order.id] = order.uuid
        if order.id in self._futures and not self._futures[order.id].done():
            self._log.debug(f"[ORDER REGISTER]: release the waiting task for order id {order.id}")
            self._futures[order.id].set_result(None) # release the waiting task
        self._log.debug(f"[ORDER REGISTER]: linked order id {order.id} with uuid {order.uuid}")

    def get_order_id(self, uuid: str) -> Optional[str]:
        """Get order ID by UUID"""
        return self._uuid_to_order_id.get(uuid, None)

    def get_uuid(self, order_id: str) -> Optional[str]:
        """Get UUID by order ID"""
        return self._order_id_to_uuid.get(order_id, None)
    
    def add_to_waiting(self, order_id: str) -> None:
        """Add order id to waiting order"""
        if order_id not in self._futures:
            self._futures[order_id] = asyncio.get_running_loop().create_future()

    async def wait_for_order_id(self, order_id: str, timeout: float | None = None) -> bool:
        """Wait for an order ID to be registered"""
        future = self._futures.get(order_id)
        if not future:
            self._log.debug(f"order id {order_id} already registered")
            return False
        
        if future.cancelled():
            self._log.warn(f"order id {order_id} timeout")
            return True
            
        if future.done():
            self._log.debug(f"order id {order_id} already registered")
            self._futures.pop(order_id, None)
            return False
            
        try:
            await asyncio.wait_for(future, timeout)
            self._log.debug(f"order id {order_id} registered")
            return False
        except asyncio.TimeoutError:
            self._log.warn(f"order id {order_id} registered timeout")
            return True
    
    def remove_order(self, order: Order) -> None:
        """Remove order mapping when no longer needed"""
        self._log.debug(f"remove order id {order.id} with uuid {order.uuid}")
        self._order_id_to_uuid.pop(order.id, None)
        self._uuid_to_order_id.pop(order.uuid, None)
        # self._uuid_init_events.pop(order.id, None)

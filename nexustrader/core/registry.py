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
        self._order_id_to_uuid[order.id] = order.uuid
        self._uuid_to_order_id[order.uuid] = order.id
        if order.id in self._futures and not self._futures[order.id].done():
            self._futures[order.id].set_result(None) # release the waiting task
        self._log.debug(f"[ORDER REGISTER]: linked order id {order.id} with uuid {order.uuid}")

    def get_order_id(self, uuid: str) -> Optional[str]:
        """Get order ID by UUID"""
        return self._uuid_to_order_id.get(uuid, None)

    def get_uuid(self, order_id: str) -> Optional[str]:
        """Get UUID by order ID"""
        return self._order_id_to_uuid.get(order_id, None)

    async def wait_for_order_id(self, order_id: str, timeout: float | None = None) -> None:
        """Wait for an order ID to be registered"""
        # await self._uuid_init_events[order_id].wait()
        self._futures[order_id] = asyncio.Future()
        if timeout:
            await asyncio.wait_for(self._futures[order_id], timeout)
            self._log.warn(f"order id {order_id} registered timeout")
        else:
            await self._futures[order_id]
        self._futures.pop(order_id)

    def remove_order(self, order: Order) -> None:
        """Remove order mapping when no longer needed"""
        self._order_id_to_uuid.pop(order.id, None)
        self._uuid_to_order_id.pop(order.uuid, None)
        # self._uuid_init_events.pop(order.id, None)

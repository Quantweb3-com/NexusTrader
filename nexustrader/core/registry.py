from typing import Optional
from nexustrader.schema import Order
from typing import List
from nexustrader.core.nautilius_core import MessageBus, Logger
from nexustrader.core.cache import AsyncCache
from nexustrader.constants import OrderStatus
from cachetools import TTLCache


class OrderRegistry:
    def __init__(
        self,
        msgbus: MessageBus,
        cache: AsyncCache,
        ttl_maxsize: int = 72000,
        ttl_seconds: int = 3600,
    ):
        self._log = Logger(name=type(self).__name__)

        self._msgbus = msgbus
        self._cache = cache
        self._uuid_to_order_id: TTLCache[str, str] = TTLCache(
            maxsize=ttl_maxsize, ttl=ttl_seconds
        )
        self._order_id_to_uuid: TTLCache[str, str] = TTLCache(
            maxsize=ttl_maxsize, ttl=ttl_seconds
        )
        self._waiting_orders: TTLCache[str, List[Order]] = TTLCache(
            maxsize=ttl_maxsize, ttl=ttl_seconds
        )

    def register_order(self, order: Order) -> None:
        """Register a new order ID to UUID mapping"""
        self._uuid_to_order_id[order.uuid] = order.id
        self._order_id_to_uuid[order.id] = order.uuid
        self._log.debug(
            f"[ORDER REGISTER]: linked order id {order.id} with uuid {order.uuid}"
        )

        if order.id not in self._waiting_orders:
            return

        for waiting_order in self._waiting_orders[order.id]:
            waiting_order.uuid = order.uuid
            self.order_status_update(waiting_order)

        self._waiting_orders.pop(order.id)

    def get_order_id(self, uuid: str) -> Optional[str]:
        """Get order ID by UUID"""
        return self._uuid_to_order_id.get(uuid, None)

    def get_uuid(self, order_id: str) -> Optional[str]:
        """Get UUID by order ID"""
        return self._order_id_to_uuid.get(order_id, None)

    def add_to_waiting(self, order: Order) -> None:
        if order.id not in self._waiting_orders:
            self._waiting_orders[order.id] = []
        self._waiting_orders[order.id].append(order)

    def remove_order(self, order: Order) -> None:
        """Remove order mapping when no longer needed"""
        self._log.debug(f"remove order id {order.id} with uuid {order.uuid}")
        self._order_id_to_uuid.pop(order.id, None)
        self._uuid_to_order_id.pop(order.uuid, None)
        # self._uuid_init_events.pop(order.id, None)

    def order_status_update(self, order: Order):
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

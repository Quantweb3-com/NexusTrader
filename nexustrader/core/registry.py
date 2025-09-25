from typing import Optional, Dict
from nexustrader.schema import Order
from nexustrader.core.nautilius_core import Logger


class OrderRegistry:
    def __init__(self):
        self._log = Logger(name=type(self).__name__)
        self._tmp_order: Dict[str, Order] = {}
        self._oids: set[str] = set()

    def register_order(self, oid: str) -> None:
        """Register an order to track its status"""
        self._log.debug(f"[ORDER REGISTER]: {oid}")
        self._oids.add(oid)

    def is_registered(self, oid: str) -> bool:
        """Check if an order is registered"""
        return oid in self._oids

    def unregister_order(self, oid: str) -> None:
        """Remove order mapping when no longer needed"""
        self._log.debug(f"[ORDER UNREGISTER]: {oid}")
        self._oids.discard(oid)

    def register_tmp_order(self, order: Order) -> None:
        """Register a temporary order"""
        self._tmp_order[order.oid] = order
        self._log.debug(f"[TMP ORDER REGISTER]: {order.oid}")

    def unregister_tmp_order(self, oid: str) -> None:
        """Unregister a temporary order"""
        self._log.debug(f"[TMP ORDER UNREGISTER]: {oid}")
        self._tmp_order.pop(oid, None)

    def get_tmp_order(self, oid: str) -> Optional[Order]:
        self._log.debug(f"[TMP ORDER GET]: {oid}")
        return self._tmp_order.get(oid, None)

import asyncio
from abc import ABC

from nexustrader.base.oms import OrderManagementSystem
from nexustrader.schema import Order
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import MessageBus, Logger
from nexustrader.core.registry import OrderRegistry


class HyperLiquidOrderManagementSystem(OrderManagementSystem):
    """Order Management System for Hyperliquid exchange"""

    def __init__(
        self,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
    ):
        pass

    def _add_order_msg(self, order: Order):
        """Add an order to the order message queue"""
        pass

    async def _handle_order_event(self):
        """Handle the order event for Hyperliquid"""
        pass

    async def start(self):
        """Start the Hyperliquid order management system"""
        pass
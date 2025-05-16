import pytest
import asyncio
from nexustrader.schema import Order, ExchangeType
from nexustrader.constants import OrderStatus, OrderSide, OrderType
from nexustrader.core.registry import OrderRegistry


@pytest.fixture
def sample_order():
    return Order(
        id="test-order-1",
        uuid="test-uuid-1",
        exchange=ExchangeType.BINANCE,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        price=50000.0,
        amount=1.0,
        timestamp=1000,
    )


@pytest.mark.asyncio
async def test_order_registration(
    order_registry: OrderRegistry, sample_order: Order
) -> None:
    # Test registration
    order_registry.register_order(sample_order)

    assert order_registry.get_order_id(sample_order.uuid) == sample_order.id
    assert order_registry.get_uuid(sample_order.id) == sample_order.uuid


@pytest.mark.asyncio
async def test_wait_for_order_id(
    order_registry: OrderRegistry, sample_order: Order
) -> None:
    # Start waiting for order ID in background
    wait_task = asyncio.create_task(order_registry.wait_for_order_id(sample_order.id))

    # Register order after small delay
    await asyncio.sleep(0.1)
    order_registry.register_order(sample_order)

    # Wait should complete
    await wait_task


@pytest.mark.asyncio
async def test_remove_order(order_registry: OrderRegistry, sample_order: Order) -> None:
    order_registry.register_order(sample_order)
    order_registry.remove_order(sample_order)

    assert order_registry.get_order_id(sample_order.uuid) is None
    assert order_registry.get_uuid(sample_order.id) is None

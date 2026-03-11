import pytest
from nexustrader.schema import Order, ExchangeType
from nexustrader.constants import OrderStatus, OrderSide, OrderType
from nexustrader.core.registry import OrderRegistry
from decimal import Decimal


@pytest.fixture
def order_registry() -> OrderRegistry:
    return OrderRegistry()


@pytest.fixture
def sample_order():
    return Order(
        oid="test-order-1",
        exchange=ExchangeType.BINANCE,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        price=50000.0,
        amount=Decimal("1.0"),
        timestamp=1000,
    )


def test_order_registration(order_registry: OrderRegistry) -> None:
    oid = "test-oid-1"
    order_registry.register_order(oid)
    assert order_registry.is_registered(oid)


def test_order_unregistration(order_registry: OrderRegistry) -> None:
    oid = "test-oid-2"
    order_registry.register_order(oid)
    assert order_registry.is_registered(oid)
    order_registry.unregister_order(oid)
    assert not order_registry.is_registered(oid)


def test_unregister_nonexistent_order(order_registry: OrderRegistry) -> None:
    # Should not raise
    order_registry.unregister_order("nonexistent-oid")


def test_tmp_order_registration(
    order_registry: OrderRegistry, sample_order: Order
) -> None:
    order_registry.register_tmp_order(sample_order)
    result = order_registry.get_tmp_order(sample_order.oid)
    assert result == sample_order


def test_tmp_order_unregistration(
    order_registry: OrderRegistry, sample_order: Order
) -> None:
    order_registry.register_tmp_order(sample_order)
    order_registry.unregister_tmp_order(sample_order.oid)
    assert order_registry.get_tmp_order(sample_order.oid) is None


def test_get_nonexistent_tmp_order(order_registry: OrderRegistry) -> None:
    assert order_registry.get_tmp_order("nonexistent-oid") is None

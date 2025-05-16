import pytest
import time
from decimal import Decimal
from copy import copy
from nexustrader.schema import (
    Order,
    ExchangeType,
    BookL1,
    Kline,
    Trade,
    Position,
    PositionSide,
    Balance,
)
from nexustrader.constants import OrderStatus, OrderSide, OrderType, KlineInterval
from nexustrader.core.cache import AsyncCache
from nexustrader.exchange.binance.constants import BinanceAccountType


@pytest.fixture
async def async_cache(task_manager, message_bus, order_registry) -> AsyncCache:  # type: ignore
    from nexustrader.core.cache import AsyncCache

    cache = AsyncCache(
        strategy_id="auto-test-strategy",
        user_id="auto-test-user",
        msgbus=message_bus,
        task_manager=task_manager,
        registry=order_registry,
    )
    yield cache
    await cache.close()


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


################ # test cache public data  ###################


async def test_market_data_cache(async_cache: AsyncCache):
    # Test kline update

    kline = Kline(
        symbol="BTCUSDT-PERP.BINANCE",
        exchange=ExchangeType.BINANCE,
        timestamp=int(time.time() * 1000),
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0,
        start=int(time.time() * 1000),
        interval=KlineInterval.MINUTE_1,
        confirm=True,
    )
    async_cache._update_kline_cache(kline)
    assert async_cache.kline("BTCUSDT-PERP.BINANCE", KlineInterval.MINUTE_1) == kline

    # Test bookL1 update
    bookl1 = BookL1(
        symbol="BTCUSDT-PERP.BINANCE",
        exchange=ExchangeType.BINANCE,
        timestamp=int(time.time() * 1000),
        bid=50000.0,
        ask=50100.0,
        bid_size=1.0,
        ask_size=1.0,
    )
    async_cache._update_bookl1_cache(bookl1)
    assert async_cache.bookl1("BTCUSDT-PERP.BINANCE") == bookl1

    # Test trade update
    trade = Trade(
        symbol="BTCUSDT-PERP.BINANCE",
        exchange=ExchangeType.BINANCE,
        timestamp=int(time.time() * 1000),
        price=50000.0,
        size=1.0,
    )
    async_cache._update_trade_cache(trade)
    assert async_cache.trade("BTCUSDT-PERP.BINANCE") == trade


################ # test cache private order data  ###################


async def test_order_management(async_cache: AsyncCache, sample_order: Order):
    # Test order initialization
    sample_order.timestamp = time.time()
    async_cache._order_initialized(sample_order)
    order = async_cache.get_order(sample_order.uuid)
    assert order.unwrap() == sample_order
    assert sample_order.uuid in async_cache.get_open_orders(symbol=sample_order.symbol)
    assert sample_order.uuid in async_cache.get_symbol_orders(sample_order.symbol)

    # Test order status update
    updated_order: Order = copy(sample_order)
    updated_order.status = OrderStatus.FILLED
    async_cache._order_status_update(updated_order)

    assert async_cache.get_order(updated_order.uuid).unwrap() == updated_order
    assert updated_order.uuid not in async_cache.get_open_orders(
        symbol=updated_order.symbol
    )


async def test_cache_cleanup(async_cache: AsyncCache, sample_order: Order):
    sample_order.timestamp = time.time() * 1000
    async_cache._order_initialized(sample_order)
    async_cache._cleanup_expired_data()

    # Order should still exist as it's not expired
    assert async_cache.get_order(sample_order.uuid) is not None

    # Create expired order
    expired_order: Order = copy(sample_order)
    expired_order.uuid = "expired-uuid"
    expired_order.timestamp = 1  # Very old timestamp

    async_cache._order_initialized(expired_order)
    async_cache._cleanup_expired_data()

    # Expired order should be removed
    assert expired_order.uuid not in async_cache._mem_orders


################ # test cache private position data  ###################


async def test_cache_apply_position(async_cache: AsyncCache):
    position = Position(
        symbol="BTCUSDT-PERP.BINANCE",
        exchange=ExchangeType.BINANCE,
        signed_amount=Decimal(0.001),
        entry_price=10660,
        side=PositionSide.LONG,
        unrealized_pnl=0,
        realized_pnl=0,
    )
    await async_cache._init_storage()  # init storage
    async_cache._apply_position(position)
    assert async_cache.get_position(position.symbol).unwrap() == position

    # sync position to sqlite
    await async_cache._sync_to_sqlite()
    balances = async_cache._get_all_positions_from_sqlite(ExchangeType.BINANCE)

    assert "BTCUSDT-PERP.BINANCE" in balances

    position = Position(
        symbol="ETHUSDT-PERP.BINANCE",
        exchange=ExchangeType.BINANCE,
        signed_amount=Decimal("0.001"),
        entry_price=10660,
        side=PositionSide.LONG,
        unrealized_pnl=0,
        realized_pnl=0,
    )
    async_cache._apply_position(position)
    assert async_cache.get_position(position.symbol).unwrap() == position

    # sync position to sqlite
    await async_cache._sync_to_sqlite()
    positions = async_cache._get_all_positions_from_sqlite(ExchangeType.BINANCE)

    assert "ETHUSDT-PERP.BINANCE" in positions


async def test_cache_apply_balance(async_cache: AsyncCache):
    btc = Balance(
        asset="BTC",
        free=Decimal("0.001"),
        locked=Decimal("0.001"),
    )
    usdt = Balance(
        asset="USDT",
        free=Decimal("1000"),
        locked=Decimal("0"),
    )

    balances = [btc, usdt]
    async_cache._apply_balance(BinanceAccountType.SPOT, balances)
    assert (
        async_cache.get_balance(BinanceAccountType.SPOT).balance_total["BTC"]
        == btc.total
    )
    assert (
        async_cache.get_balance(BinanceAccountType.SPOT).balance_total["USDT"]
        == usdt.total
    )

    # sync balance to sqlite
    await async_cache._init_storage()  # init storage
    await async_cache._sync_to_sqlite()
    balances = async_cache._get_balance_from_sqlite(BinanceAccountType.SPOT)

    for balance in balances:
        if balance.asset == "BTC":
            assert balance.free == btc.free
            assert balance.locked == btc.locked
        elif balance.asset == "USDT":
            assert balance.free == usdt.free
            assert balance.locked == usdt.locked

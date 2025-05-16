import pytest
import types
from decimal import Decimal
from typing import List
from nexustrader.exchange.binance import BinanceExecutionManagementSystem
from nexustrader.schema import BaseMarket


@pytest.fixture
def ems(market, cache, message_bus, task_manager, order_registry):
    ems = BinanceExecutionManagementSystem(
        market,
        cache,
        message_bus,
        task_manager,
        order_registry,
        is_mock=False,
    )

    def mock_get_min_order_amount(self, symbol: str, market: BaseMarket) -> Decimal:
        amount_min = market.limits.amount.min * 2
        amount_min = ems._amount_to_precision(symbol, amount_min, mode="ceil")
        return amount_min

    ems._get_min_order_amount = types.MethodType(mock_get_min_order_amount, ems)
    return ems


@pytest.mark.parametrize(
    "total_amount, duration, wait, reduce_only, expected_amounts, expected_wait",
    [
        (Decimal("0.001"), 10, 1, False, [], 0),
        (Decimal("0.001"), 10, 1, True, [Decimal("0.001")], 0),
        (Decimal("0.005"), 10, 1, False, [Decimal("0.002"), Decimal("0.003")], 10 / 2),
        (
            Decimal("0.005"),
            10,
            1,
            True,
            [Decimal("0.002"), Decimal("0.002"), Decimal("0.001")],
            10 / 3,
        ),
        (Decimal("0.005"), 10, 5, False, [Decimal("0.003"), Decimal("0.002")], 10 / 2),
        (Decimal("0.005"), 10, 5, True, [Decimal("0.003"), Decimal("0.002")], 10 / 2),
        (
            Decimal("0.009"),
            10,
            1,
            False,
            [Decimal("0.002")] * 3 + [Decimal("0.003")],
            10 / 4,
        ),
        (
            Decimal("0.009"),
            10,
            1,
            True,
            [Decimal("0.002")] * 4 + [Decimal("0.001")],
            10 / 5,
        ),
    ],
)
def test_cal_twap_orders(
    ems: BinanceExecutionManagementSystem,
    total_amount: Decimal,
    duration: float,
    wait: float,
    reduce_only: bool,
    expected_amounts: List[Decimal],
    expected_wait: float,
):
    symbol = "BTCUSDT-PERP.BINANCE"
    market = ems._market[symbol]
    min_order_amount = ems._get_min_order_amount(
        symbol=symbol,
        market=market,
    )
    amount_list, wait = ems._calculate_twap_orders(
        symbol=symbol,
        total_amount=total_amount,
        duration=duration,
        wait=wait,
        min_order_amount=min_order_amount,
        reduce_only=reduce_only,
    )
    assert amount_list == expected_amounts
    assert wait == expected_wait

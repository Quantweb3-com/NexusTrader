"""
OKX LIVE_1 断网重连 & 订单去重压力测试
========================================
测试目的：
  1. 持续发出不会成交的 USDCUSDT 远价限价买单
  2. 手动断网后观察 WS 重连事件、订单流是否有误报
  3. 验证 idempotency_key 去重机制：同一 key 两次调用 create_order_ws 只产生一个订单
  4. 捕获所有订单生命周期回调，统计异常情况
  5. Ctrl+C 后打印完整测试报告

WS 下单恢复语义说明：
  - REQUEST_NOT_SENT    : WS 断线且 ws_fallback=False，请求未发出（本脚本默认 ws_fallback=True，
                          该事件不会触发；可将 _place_order_no_fallback 计时器打开进行测试）
  - ACK_REJECTED        : 交易所明确拒绝（参数错误、余额不足等）
  - ACK_TIMEOUT         : ACK 超时且 REST 无法确认（状态未知，需人工核查）
  - ACK_TIMEOUT_CONFIRMED : ACK 超时，但 REST 已确认订单成功提交（正常路径，仅用于审计）

使用方法：
  1. 确保 .keys/.secrets.toml 中有 [OKX.LIVE_1] 配置
  2. 运行: python strategy/mystrat/test_okx_live1_ws_reconnect.py
  3. 运行期间可手动断网/恢复网络，观察日志
  4. Ctrl+C 结束后查看测试报告
"""

import os
import signal
import time
from datetime import datetime
from decimal import Decimal

import pytest

from nexustrader.config import (
    BasicConfig,
    Config,
    PrivateConnectorConfig,
    PublicConnectorConfig,
)
from nexustrader.constants import ExchangeType, OrderSide, OrderType, WsOrderResultType
from nexustrader.constants import settings
from nexustrader.engine import Engine
from nexustrader.exchange import OkxAccountType
from nexustrader.schema import AccountBalance, BookL1, Order
from nexustrader.strategy import Strategy

# ── 账户配置 ──────────────────────────────────────────────────────────────────
try:
    OKX_API_KEY = settings.OKX.LIVE_1.API_KEY
    OKX_SECRET = settings.OKX.LIVE_1.SECRET
    OKX_PASSPHRASE = settings.OKX.LIVE_1.PASSPHRASE
except Exception:
    pytest.skip(
        "OKX LIVE_1 credentials are required for this live test",
        allow_module_level=True,
    )

# ── 测试参数 ──────────────────────────────────────────────────────────────────
SYMBOL = "USDCUSDT.OKX"
# USDC/USDT 现货价格约 1.0，挂单价 0.97 远低于市场，绝不成交
ORDER_PRICE = Decimal("0.9700")
ORDER_AMOUNT = Decimal("1")  # OKX USDCUSDT 最小下单量 1 USDC

PLACE_INTERVAL_SEC = 10  # 每 10 秒挂一笔新单（ws_fallback=True，断网时自动走 REST）
DEDUP_INTERVAL_SEC = 13  # 每 13 秒执行一次 idempotency 去重测试
CANCEL_INTERVAL_SEC = 60  # 每 60 秒清仓所有挂单（保底兜底）

MAX_OPEN_ORDERS = 7  # 同时挂单上限：超过时先撤最早一笔，再挂新单


class OkxWsReconnectTest(Strategy):
    def __init__(self):
        super().__init__()
        self._started_at: float = time.time()
        self._has_bookl1: bool = False

        # ── 订单生命周期计数 ─────────────────────────────────────────────────
        self.cnt_submitted: int = 0
        self.cnt_pending: int = 0
        self.cnt_accepted: int = 0
        self.cnt_failed: int = 0
        self.cnt_canceled: int = 0
        self.cnt_cancel_failed: int = 0
        self.cnt_filled: int = 0
        self.cnt_partially_filled: int = 0

        # ── idempotency / 去重 ───────────────────────────────────────────────
        self.cnt_dedup_tests: int = 0  # 执行了几轮去重测试
        self.cnt_dedup_ok: int = 0  # oid 相同（cache 层已去重）
        self.cnt_dedup_miss: int = 0  # oid 不同（预期外）

        # ── WS 层事件 ────────────────────────────────────────────────────────
        self.ws_reconnect_events: list[dict] = []  # on_private_ws_status
        self.ws_resync_events: list[dict] = []  # on_private_ws_resync_diff
        self.ws_order_errors: list[
            dict
        ] = []  # REQUEST_NOT_SENT / ACK_REJECTED / ACK_TIMEOUT
        self.ws_ack_confirmed: list[
            dict
        ] = []  # ACK_TIMEOUT_CONFIRMED（超时后 REST 确认成功）

        # ── 失败订单详情 ─────────────────────────────────────────────────────
        self.failed_order_details: list[str] = []
        self.cancel_failed_details: list[str] = []

    # ─────────────────────────── on_start ────────────────────────────────────

    def on_start(self):
        self.log.info(f"[TEST] 开始测试 symbol={SYMBOL}  order_price={ORDER_PRICE}")
        self.log.info("[TEST] 订阅 BookL1 行情…")
        self.subscribe_bookl1(symbols=[SYMBOL])

        # 每隔 PLACE_INTERVAL_SEC 秒挂一笔普通限价单（ws_fallback=True 默认）
        self.schedule(
            self._place_order,
            trigger="interval",
            seconds=PLACE_INTERVAL_SEC,
        )

        # idempotency 去重测试（与普通挂单错开 3 秒，避免日志混叠）
        self.schedule(
            self._test_idempotency_dedup,
            trigger="interval",
            seconds=DEDUP_INTERVAL_SEC,
        )

        # 定期撤销所有挂单，防止账户积累太多开放委托
        self.schedule(
            self._cancel_all_open,
            trigger="interval",
            seconds=CANCEL_INTERVAL_SEC,
        )

    # ─────────────────────────── 辅助方法 ────────────────────────────────────

    def _get_oldest_oid(self, open_oids: list[str]) -> str | None:
        """返回时间戳最早（最老）的挂单 oid；若无法获取时间戳，返回列表第一个。"""
        best_ts: float = float("inf")
        best_oid: str | None = None
        for oid in open_oids:
            order = self.cache.get_order(oid)
            ts = float(order.timestamp) if (order and order.timestamp) else 0.0
            if ts < best_ts:
                best_ts = ts
                best_oid = oid
        return best_oid or (open_oids[0] if open_oids else None)

    # ─────────────────────────── 定时任务 ────────────────────────────────────

    def _place_order(self):
        """发出一笔不会成交的低价限价买单（WS 通道，ws_fallback=True）。

        当前有效挂单数 ≥ MAX_OPEN_ORDERS 时，先通过 cancel_order_ws 撤销最早
        一笔（cancel_order_ws 内部立即调用 mark_cancel_intent，使该 oid 从
        get_open_orders 结果中排除），然后继续挂新单，保持挂单数不超过上限。
        断网时 cancel/create 均自动走 REST fallback。
        """
        if not self._has_bookl1:
            self.log.warning("[TEST] 尚未收到行情，跳过本轮下单")
            return

        open_oids = list(self.cache.get_open_orders(symbol=SYMBOL))

        if len(open_oids) >= MAX_OPEN_ORDERS:
            oldest_oid = self._get_oldest_oid(open_oids)
            if oldest_oid:
                self.log.info(
                    f"[LIMIT] 当前挂单 {len(open_oids)} ≥ {MAX_OPEN_ORDERS}，"
                    f"先撤最早单 oid={oldest_oid}，再挂新单"
                )
                self.cancel_order_ws(symbol=SYMBOL, oid=oldest_oid)
                # cancel_order_ws 立即调用 mark_cancel_intent，
                # 后续 get_open_orders() 默认不再计入该 oid。

        self.cnt_submitted += 1
        self.log.info(
            f"[PLACE #{self.cnt_submitted}] {SYMBOL} BUY LIMIT "
            f"{ORDER_AMOUNT} @ {ORDER_PRICE}  "
            f"(当前有效挂单: {len(open_oids)}/{MAX_OPEN_ORDERS})"
        )
        self.create_order_ws(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=ORDER_AMOUNT,
            price=ORDER_PRICE,
            # ws_fallback=True 是默认值：断线时静默 fallback 到 REST
        )

    def _test_idempotency_dedup(self):
        """
        用同一个 idempotency_key 连续调用两次 create_order_ws：
          - cache 层去重成功 → 两次返回相同 oid（cnt_dedup_ok + 1）
          - 不同 oid → 说明去重未生效（cnt_dedup_miss + 1）
        注意：这里每轮用一个新 key，测的是 *同轮内* 的去重，
        而非跨轮复用 key（否则 key 已记录，永远返回旧 oid）。
        挂单数已达上限时跳过本轮测试，避免触发 _place_order 的 cancel 逻辑。
        """
        if not self._has_bookl1:
            return
        print("self._has_bookl1", self._has_bookl1)
        open_oids = self.cache.get_open_orders(symbol=SYMBOL)
        if len(open_oids) >= MAX_OPEN_ORDERS:
            self.log.info(
                f"[DEDUP SKIP] 当前挂单 {len(open_oids)} ≥ {MAX_OPEN_ORDERS}，"
                "跳过本轮去重测试"
            )
            return

        self.cnt_dedup_tests += 1
        key = f"dedup_round_{self.cnt_dedup_tests}"

        oid_a = self.create_order_ws(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=ORDER_AMOUNT,
            price=ORDER_PRICE,
            idempotency_key=key,
        )
        self.cnt_submitted += 1

        # 立即用相同 key 再调用一次
        oid_b = self.create_order_ws(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=ORDER_AMOUNT,
            price=ORDER_PRICE,
            idempotency_key=key,
        )
        # oid_b 不额外计入 submitted，因为应被去重

        if oid_a == oid_b:
            self.cnt_dedup_ok += 1
            self.log.info(
                f"[DEDUP OK] round={self.cnt_dedup_tests} "
                f"oid_a={oid_a} == oid_b={oid_b}  ✓ cache 层去重生效"
            )
        else:
            self.cnt_dedup_miss += 1
            self.log.warning(
                f"[DEDUP MISS] round={self.cnt_dedup_tests} "
                f"oid_a={oid_a} != oid_b={oid_b}  ✗ 去重未生效"
            )

    def _cancel_all_open(self):
        """撤销 SYMBOL 下所有开放委托。"""
        print("self._cancel_all_open", self._cancel_all_open)
        open_oids = self.cache.get_open_orders(symbol=SYMBOL)
        if not open_oids:
            self.log.info("[CANCEL] 当前无挂单，无需撤单")
            return
        self.log.info(f"[CANCEL] 批量撤销 {len(open_oids)} 笔挂单…")
        for oid in list(open_oids):
            self.cancel_order_ws(symbol=SYMBOL, oid=oid)

    # ─────────────────────────── 行情回调 ────────────────────────────────────

    def on_bookl1(self, bookl1: BookL1):
        if not self._has_bookl1:
            self._has_bookl1 = True
            self.log.info(
                f"[MARKET] 首次收到 BookL1 — bid={bookl1.bid} ask={bookl1.ask} "
                f"(挂单价 {ORDER_PRICE} 低于 bid {(1 - float(ORDER_PRICE) / float(bookl1.bid)) * 100:.2f}%)"
            )

    # ─────────────────────────── 订单生命周期回调 ────────────────────────────

    def on_pending_order(self, order: Order):
        self.cnt_pending += 1
        self.log.info(f"[PENDING]  oid={order.oid}")

    def on_accepted_order(self, order: Order):
        self.cnt_accepted += 1
        self.log.info(f"[ACCEPTED] oid={order.oid}")

    def on_failed_order(self, order: Order):
        self.cnt_failed += 1
        msg = f"oid={order.oid} status={order.status} reason={order.reason or 'N/A'}"
        self.failed_order_details.append(f"[{_ts()}] {msg}")
        self.log.warning(f"[FAILED]   {msg}")

    def on_canceled_order(self, order: Order):
        self.cnt_canceled += 1
        self.log.info(f"[CANCELED] oid={order.oid}")

    def on_cancel_failed_order(self, order: Order):
        self.cnt_cancel_failed += 1
        msg = f"oid={order.oid} status={order.status} reason={order.reason or 'N/A'}"
        self.cancel_failed_details.append(f"[{_ts()}] {msg}")
        self.log.warning(f"[CANCEL_FAILED] {msg}")

    def on_partially_filled_order(self, order: Order):
        self.cnt_partially_filled += 1
        self.log.error(
            f"[PARTIAL_FILL] oid={order.oid}  价格过高！请检查 ORDER_PRICE 设置"
        )

    def on_filled_order(self, order: Order):
        self.cnt_filled += 1
        self.log.error(
            f"[FILLED !!!] oid={order.oid}  订单意外成交！请立即检查 ORDER_PRICE 设置"
        )

    def on_balance(self, balance: AccountBalance):
        self.log.debug(f"[BALANCE] {balance}")

    # ─────────────────────────── WS 状态回调 ─────────────────────────────────

    def on_private_ws_status(self, status: dict):
        """私有 WS 连接状态变化（断开/重连/重连完成）。"""
        event = {"ts": _ts(), **status}
        self.ws_reconnect_events.append(event)
        self.log.info(f"[WS_STATUS] {event}")

    def on_private_ws_resync_diff(self, payload: dict):
        """WS 重连后的订单对账差异。"""
        event = {"ts": _ts(), **payload}
        self.ws_resync_events.append(event)
        self.log.info(f"[WS_RESYNC_DIFF] {event}")

    def on_ws_order_request_result(self, result: dict):
        """
        WS 下单/撤单请求的结构化结果。
        result_type 说明：
          REQUEST_NOT_SENT      — WS 断线且 ws_fallback=False，请求未发出
          ACK_REJECTED          — 交易所明确拒绝（参数错误、余额不足等）
          ACK_TIMEOUT           — ACK 超时且 REST 也无法确认，状态未知
          ACK_TIMEOUT_CONFIRMED — ACK 超时，但 REST 已确认订单成功提交（非错误）
        """
        result_type = result.get("result_type", "")
        event = {"ts": _ts(), **result}

        if result_type == WsOrderResultType.ACK_TIMEOUT_CONFIRMED:
            # 成功路径：超时后 REST 已确认订单存在，记录审计但不计为错误
            self.ws_ack_confirmed.append(event)
            self.log.info(f"[WS_ACK_CONFIRMED] ACK 超时后 REST 确认成功: {event}")
        else:
            # 真正的错误路径
            self.ws_order_errors.append(event)
            if result_type == WsOrderResultType.REQUEST_NOT_SENT:
                self.log.warning(
                    f"[WS_ERR] 请求未发出（断网且未启用 fallback）: {event}"
                )
            elif result_type == WsOrderResultType.ACK_REJECTED:
                self.log.warning(f"[WS_ERR] 请求被交易所拒绝: {event}")
            elif result_type == WsOrderResultType.ACK_TIMEOUT:
                self.log.warning(f"[WS_ERR] ACK 超时，状态未知，需人工核查: {event}")
            else:
                self.log.warning(f"[WS_ERR] 未知错误: {event}")

    # ─────────────────────────── 测试报告 ────────────────────────────────────

    def print_report(self):
        duration = time.time() - self._started_at
        sep = "=" * 65

        print(f"\n{sep}")
        print("   OKX LIVE_1  WS 断网重连 & 订单去重  测试报告")
        print(f"   Symbol   : {SYMBOL}   挂单价: {ORDER_PRICE}")
        print(f"   总运行时长: {duration:.1f}s")
        print(sep)

        print("\n【一、订单生命周期统计】")
        print(f"  已提交 (submitted)       : {self.cnt_submitted}")
        print(f"  已挂起 (pending)         : {self.cnt_pending}")
        print(f"  已接受 (accepted)        : {self.cnt_accepted}")
        print(f"  下单失败 (failed)        : {self.cnt_failed}")
        print(f"  已撤销 (canceled)        : {self.cnt_canceled}")
        print(f"  撤单失败 (cancel_failed) : {self.cnt_cancel_failed}")
        print(f"  部分成交 (partial_fill)  : {self.cnt_partially_filled}")
        print(f"  完全成交 (filled) ← 异常 : {self.cnt_filled}")

        print("\n【二、Idempotency 去重测试】")
        print(f"  执行轮次     : {self.cnt_dedup_tests}")
        print(
            f"  去重成功 (OK): {self.cnt_dedup_ok}  ✓ oid_a == oid_b，cache 层去重生效"
        )
        print(f"  去重失败(MISS): {self.cnt_dedup_miss}  ✗ oid 不同，预期外")

        print("\n【三、WS 连接事件（断网重连）】")
        if self.ws_reconnect_events:
            for e in self.ws_reconnect_events:
                print(f"  {e}")
        else:
            print("  (无事件 — 未触发断网，或重连未发出 status 事件)")

        print("\n【四、WS 重连对账差异 (resync_diff)】")
        if self.ws_resync_events:
            for e in self.ws_resync_events:
                print(f"  {e}")
        else:
            print("  (无差异 — 断网期间无丢失订单，或未断网)")

        print("\n【五、WS 订单请求错误（真正失败）】")
        if self.ws_order_errors:
            for e in self.ws_order_errors:
                print(f"  {e}")
        else:
            print("  (无错误 — WS 通道始终正常，或断线时 REST fallback 静默处理)")

        print("\n【六、ACK_TIMEOUT_CONFIRMED（超时后 REST 确认成功，供审计）】")
        if self.ws_ack_confirmed:
            for e in self.ws_ack_confirmed:
                print(f"  {e}")
        else:
            print("  (无)")

        print("\n【七、失败订单详情】")
        if self.failed_order_details:
            for m in self.failed_order_details:
                print(f"  {m}")
        else:
            print("  (无)")

        print("\n【八、撤单失败详情】")
        if self.cancel_failed_details:
            for m in self.cancel_failed_details:
                print(f"  {m}")
        else:
            print("  (无)")

        print("\n【综合判断】")
        issues: list[str] = []

        if self.cnt_filled > 0:
            issues.append(
                f"FAIL: {self.cnt_filled} 笔订单意外成交！ORDER_PRICE 设置可能过高"
            )
        if self.cnt_partially_filled > 0:
            issues.append(f"WARN: {self.cnt_partially_filled} 笔部分成交，注意价格设置")
        if self.cnt_dedup_tests > 0 and self.cnt_dedup_miss > 0:
            issues.append(
                f"FAIL: {self.cnt_dedup_miss}/{self.cnt_dedup_tests} 轮去重失败"
            )
        if self.cnt_dedup_tests > 0 and self.cnt_dedup_ok == self.cnt_dedup_tests:
            print(
                f"  ✓ idempotency 去重全部通过 ({self.cnt_dedup_ok}/{self.cnt_dedup_tests})"
            )

        ws_not_sent = [
            e
            for e in self.ws_order_errors
            if e.get("result_type") == WsOrderResultType.REQUEST_NOT_SENT
        ]
        if ws_not_sent:
            print(
                f"  ✓ 断网期间共 {len(ws_not_sent)} 笔请求未发出 (REQUEST_NOT_SENT)，"
                "均已正确上报，无静默丢失"
            )

        ws_rejected = [
            e
            for e in self.ws_order_errors
            if e.get("result_type") == WsOrderResultType.ACK_REJECTED
        ]
        if ws_rejected:
            issues.append(f"WARN: {len(ws_rejected)} 笔被交易所拒绝 (ACK_REJECTED)")

        ws_timeout = [
            e
            for e in self.ws_order_errors
            if e.get("result_type") == WsOrderResultType.ACK_TIMEOUT
        ]
        if ws_timeout:
            issues.append(
                f"WARN: {len(ws_timeout)} 笔 ACK 超时且状态未知 (ACK_TIMEOUT)，需人工核查"
            )

        if self.ws_ack_confirmed:
            print(
                f"  ✓ {len(self.ws_ack_confirmed)} 笔 ACK_TIMEOUT_CONFIRMED — "
                "超时后 REST 确认成功，订单状态已同步"
            )
        if self.ws_reconnect_events:
            print(
                f"  ✓ 检测到 {len(self.ws_reconnect_events)} 次 WS 状态事件（断开/重连）"
            )
        if self.ws_resync_events:
            print(f"  ✓ 检测到 {len(self.ws_resync_events)} 次重连对账差异事件")

        if issues:
            for issue in issues:
                print(f"  ✗ {issue}")
        elif not any(
            [
                ws_not_sent,
                ws_rejected,
                ws_timeout,
                self.ws_reconnect_events,
                self.ws_resync_events,
                issues,
            ]
        ):
            print("  (整个测试期间网络稳定，未触发断网场景。请尝试手动断网后重测)")

        print(sep)


# ── 辅助函数 ──────────────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── 策略 & 引擎配置 ───────────────────────────────────────────────────────────

strategy = OkxWsReconnectTest()

config = Config(
    strategy_id="okx_live1_ws_reconnect_test",
    user_id="quantweb3",
    strategy=strategy,
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.LIVE,
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
                account_type=OkxAccountType.LIVE,
            )
        ]
    },
)

engine = Engine(config)


def _setup_graceful_shutdown():
    """Set up Ctrl+C handling that works on Windows and after WS reconnection.

    Windows does not support loop.add_signal_handler(), so the TaskManager's
    built-in signal handling silently falls back to nothing on this platform.
    We register a plain signal.signal(SIGINT) handler that uses
    loop.call_soon_threadsafe() to set the shutdown event from the OS signal
    handler thread — the only safe way to interact with a running asyncio loop
    from outside it.

    Pressing Ctrl+C a second time forces an immediate hard exit in case the
    graceful shutdown hangs (e.g. an unresponsive WS reconnect loop).
    """
    _first = True

    def _handler(signum, frame):
        nonlocal _first
        if not _first:
            print("\n[SIGINT] 强制退出…", flush=True)
            os._exit(1)
        _first = False
        print("\n[SIGINT] 收到 Ctrl+C，正在优雅停机（再按一次强制退出）…", flush=True)
        try:
            loop = engine._loop
            shutdown_event = engine._task_manager._shutdown_event
            if loop and loop.is_running() and not shutdown_event.is_set():
                loop.call_soon_threadsafe(shutdown_event.set)
        except Exception:
            raise KeyboardInterrupt from None

    signal.signal(signal.SIGINT, _handler)


if __name__ == "__main__":
    _setup_graceful_shutdown()
    try:
        engine.start()
    except KeyboardInterrupt:
        pass
    finally:
        strategy.print_report()
        engine.dispose()

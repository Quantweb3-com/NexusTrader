# Changelog

All notable changes to NexusTrader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.19] - 2026-03-28

### Fixed

- **Bybit WebSocket ping timeout misaligned with official recommendation** — Both `BybitWSClient` and `BybitWSApiClient` were using `ping_idle_timeout=5` and `ping_reply_timeout=2`. Bybit officially recommends a heartbeat every 20 seconds; the 5-second interval was unnecessarily aggressive and the 2-second reply window was too tight for normal network jitter. Updated to `ping_idle_timeout=20` / `ping_reply_timeout=5`.
- **OKX WebSocket ping timeout misaligned with official recommendation** — Both `OkxWSClient` and `OkxWSApiClient` were using `ping_idle_timeout=5` and `ping_reply_timeout=2`. OKX closes the connection if no communication occurs within 30 seconds; the 5-second interval was overly aggressive and `ping_reply_timeout=2` was too tight. Updated to `ping_idle_timeout=30` / `ping_reply_timeout=5`, consistent with Bitget and HyperLiquid.

## [0.3.18] - 2026-03-28

### Fixed

- **Bybit WS API pong never recognized → infinite reconnect loop** — `BybitWSApiClient.user_api_pong_callback` decoded pong frames with `BybitWsApiGeneralMsg`, which requires `retCode` and `retMsg` fields. The actual pong response `{"op": "pong", "connId": "xxx"}` omits both, causing `msgspec.DecodeError` on every pong → callback returned `False` → 2-second timeout → disconnect → 1-second delay → reconnect → repeat forever. Fixed by switching to `BybitWsMessageGeneral` (all fields optional; `is_pong` checks both `op == "pong"` and `ret_msg == "pong"`), consistent with the public WS callback.
- **`BybitWSApiClient` missing `auto_ping_strategy`** — The private WS API client was constructed without `auto_ping_strategy`, defaulting picows to `"ping_when_idle"` while the public `BybitWSClient` uses `"ping_periodically"`. Added `auto_ping_strategy="ping_periodically"` to align behavior.
- **OKX WS clients missing `auto_ping_strategy`** — Both `OkxWSClient` and `OkxWSApiClient` were constructed without `auto_ping_strategy`, defaulting to `"ping_when_idle"`. Added `auto_ping_strategy="ping_periodically"` to both constructors for consistency with other exchanges.

## [0.3.17] - 2026-03-28

### Fixed

- **WebSocket reconnect loop missing `await` on `disconnect()`** — In `WSClient._connection_handler()`, the call to `self.disconnect()` inside the reconnect loop was not `await`ed. Since `disconnect()` is `async def`, the bare call produced a coroutine object that was never executed, generating `RuntimeWarning: coroutine 'WSClient.disconnect' was never awaited` on every reconnect cycle. The stale transport was never torn down, causing resource leaks and potential duplicate connections. Fixed by adding `await`.
- **`Engine.dispose()` deadlock when called from a signal handler** — If user code registered a `signal.signal()` handler that called `engine.dispose()` while `engine.start()` was blocking on `loop.run_until_complete(self._start())`, `dispose()` would attempt another `loop.run_until_complete()` on the already-running event loop, raising `RuntimeError: This event loop is already running`. Fixed by detecting whether the loop is currently running in `dispose()`: if so, the method schedules `task_manager._shutdown_event.set()` via `loop.call_soon_threadsafe()` and returns immediately, allowing `_start()` to unblock naturally and `start()`'s `finally` block to perform the actual disposal after the loop has stopped.

## [0.3.16] - 2026-03-28

### Fixed

- **WebSocket disconnect not properly awaited** — `WSClient.disconnect()` was synchronous; callers that did not `await` it silently dropped the coroutine, leaving the underlying transport open and spawning stray asyncio tasks. Promoted to `async def`: saves a local transport reference before clearing `self._transport`, calls `transport.disconnect()`, then `await asyncio.wait_for(transport.wait_disconnected(), timeout=3.0)` before firing the `on_disconnected` hook. All call sites updated: `PublicConnector` now `await`s `self._ws_client.disconnect()` (previously the call was commented out), `PrivateConnector` now `await`s `self._oms._ws_client.disconnect()`, `OkxPublicConnector` now `await`s `self._business_ws_client.disconnect()`, and `bybit_tradfi._NullWsClientStub.disconnect()` was promoted to `async def` to satisfy the awaitable contract.
- **Engine shutdown leaves pending tasks uncollected** — `Engine._close_event_loop()` cancelled all remaining asyncio tasks but never awaited them, preventing `CancelledError` handlers from running and causing unclean event-loop closure. Fixed by calling `loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))` after cancellation to drain all tasks before `loop.close()`. Post-disconnect sleep increased from 0.2 s to 0.5 s to allow WS transports to finish before the task sweep.
- **Binance historical kline fetch called outside async context** — `BinancePublicConnector._get_index_price_klines()` and `_get_historical_klines()` called the async REST client methods without `_run_sync()`, returning an unawaited coroutine object instead of the actual kline data. Both calls are now wrapped with `self._run_sync()`, consistent with OKX, Bybit, and Bitget.

## [0.3.15] - 2026-03-27

### Fixed

- **Reconnect resync deadlock** — `_resync_after_reconnect()` is launched as an asyncio task inside the running event loop. It previously called the synchronous `_init_account_balance()` / `_init_position()` helpers, which internally use `asyncio.run_coroutine_threadsafe(coro, loop).result()`. Calling `.result()` from the event-loop thread blocks that thread while waiting for a future that can only be resolved by the same loop, causing a permanent deadlock. After reconnect the `resynced` event never fired and the entire event loop froze. Fixed by adding `_async_resync_init()` to the base OMS, which offloads both sync helpers to a thread-pool executor via `asyncio.run_in_executor()`, so the executor thread blocks on `.result()` while the event loop remains free. Applied to OKX, Binance, Bybit, Bitget, and HyperLiquid.
- **Spurious `on_accepted_order` callbacks after reconnect** — After a reconnect, `_resync_after_reconnect()` calls `fetch_open_orders()` and passes the results to `order_status_update()`. Because `ACCEPTED → ACCEPTED` is a valid state transition (needed for modify-order flows), the cache accepted the update and dispatched `on_accepted_order` for every already-open order, causing duplicate callbacks. Any production strategy with hedging, position-sizing, or risk logic in `on_accepted_order` would misfire after every reconnect. Fixed by adding a `silent=True` parameter to `order_status_update()`: when set, the cache is updated but no strategy callbacks are dispatched. `_resync_after_reconnect()` in OKX, Binance, and Bybit now passes `silent=True` whenever the fetched order status matches the currently cached status (no meaningful change). Status transitions that *do* represent real changes (e.g. `PENDING → ACCEPTED`, `ACCEPTED → FILLED`) continue to fire callbacks normally.

## [0.3.14] - 2026-03-27

### Added

- **Order create idempotency controls** — `CreateOrderSubmit` now carries an optional `idempotency_key`, `Strategy.create_order()` / `create_order_ws()` accept `client_oid` and `idempotency_key`, and `AsyncCache` now stores canonical OID mappings so repeated signals can safely reuse the same logical order.
- **Explicit WS ACK error types** — Added `WsRequestNotSentError`, `WsAckTimeoutError`, and `WsAckRejectedError` to distinguish socket-send failures, missing exchange ACKs, and explicit WS rejections.
- **`WsOrderResultType` enum** — New structured result enum (`REQUEST_NOT_SENT`, `ACK_REJECTED`, `ACK_TIMEOUT`, `ACK_TIMEOUT_CONFIRMED`) returned by `create_order_ws()` / `cancel_order_ws()` and published via `on_ws_order_request_result()`.
- **`on_ws_order_request_result()` strategy callback** — New overrideable `Strategy` method that receives a structured dict (`oid`, `symbol`, `exchange`, `result_type`, `reason`, `timestamp`) whenever a WS order/cancel request produces an ACK error or timeout confirmation.
- **Bitget and HyperLiquid REST order lookup helpers** — Both exchanges now expose `fetch_order()` / `fetch_open_orders()` support for open-order recovery, and their REST clients gained the required open-order endpoints.
- **Regression tests for idempotency and WS ACK handling** — Added `test/test_order_idempotency.py`, `test/test_ws_ack.py`, and `test/test_ack_and_reconcile.py` to cover duplicate create suppression, ACK timeout recovery, disconnect rejection, fallback behavior, and reconnect reconciliation.

### Changed

- **WS order/cancel ACK flow unified across exchanges** — OKX, Binance, Bybit, Bitget, and HyperLiquid now register pending ACK futures for WS order operations, reject those waiters on WS API disconnect, wait up to 5 seconds for an ACK, and confirm order state via REST before surfacing an ACK-timeout error.
- **`_send_or_raise()` now raises a domain-specific exception** — `WSClient._send_or_raise()` now raises `WsRequestNotSentError` instead of a generic `ConnectionError`, allowing OMS code to handle WS send failures more precisely.
- **Duplicate create submissions are skipped earlier** — Base EMS now suppresses repeated create requests when the OID is already inflight, registered, or cached; HyperLiquid applies the same guard after converting the client OID into the exchange `cloid` format.
- **Bitget / HyperLiquid WS fallback parity** — `create_order_ws()` and `cancel_order_ws()` on Bitget and HyperLiquid now support the same `ws_fallback=True` behavior already used on OKX, Binance, and Bybit.
- **`fetch_order()` gains `force_refresh` parameter** — `Strategy.fetch_order()` and all OMS `fetch_order()` implementations now accept `force_refresh=True` to bypass the local cache and query the exchange REST API directly, which is used internally by ACK-timeout recovery paths.

### Fixed

- **Duplicate order submission races** — Repeated strategy calls with the same logical order no longer enqueue duplicate exchange submissions while the order is still inflight or already known locally.
- **Silent WS uncertainty after delayed or missing ACKs** — A WS request that was sent successfully but not acknowledged in time is now reconciled through REST before the OMS decides the request failed, reducing false negatives during transient WS issues.
- **Pending ACK waiters left behind on WS disconnect** — Exchange OMS instances now clear and fail all pending ACK futures when the WS API connection drops, preventing hung awaiters and stale in-memory state.
- **Bitget / HyperLiquid reconnect order recovery gaps** — Both exchanges now have open-order resync paths that can reconcile cached open orders against exchange state after reconnect.

## [0.3.13] - 2026-03-27

### Added

- **WebSocket lifecycle hooks** — `WSClient` now exposes `set_lifecycle_hooks(on_connected, on_disconnected, on_reconnected)`. Hooks are fired automatically on each connection state change and can be sync or async callables.
- **Private WS status events** — OMS registers lifecycle hooks on startup and publishes `private_ws_status` (connected / disconnected / reconnected / resynced) and `private_ws_resync_diff` events to the message bus, allowing strategies to react via `on_private_ws_status()` and `on_private_ws_resync_diff()` callbacks.
- **Reconnect order reconciliation** — After a private WebSocket reconnects, OMS automatically re-fetches balances, positions, and open orders, then emits a diff summary. OKX, Binance, and Bybit each have exchange-specific `_resync_after_reconnect()` overrides with conservative missing-order confirmation (configurable via `set_reconnect_reconcile_grace_ms()`).
- **`_send_or_raise()`** — New `WSClient` helper that raises `ConnectionError` instead of silently dropping messages when the socket is unavailable.
- **`ws_fallback` parameter** — `create_order_ws()` and `cancel_order_ws()` on OKX, Binance, and Bybit now accept a `ws_fallback=True` kwarg. When the WS send fails due to a `ConnectionError`, the call automatically retries via REST (fallback=True) or marks the order as `FAILED` / `CANCEL_FAILED` immediately (fallback=False).
- **`fetch_order()` / `fetch_open_orders()` / `fetch_recent_trades()`** — New OMS REST query methods available on all three exchanges, also exposed on `Strategy` for direct use in trading logic.
- **OKX `get_api_v5_trade_orders_pending`** — New REST endpoint wrapper for fetching pending open orders.
- **Binance fetch-order REST wrappers** — New `get_api_v3_order`, `get_fapi_v1_order`, `get_dapi_v1_order`, `get_api_v3_open_orders`, `get_fapi_v1_open_orders`, `get_dapi_v1_open_orders` REST methods.

### Fixed

- **Inactive symbol warnings across all exchanges** — `load_markets()` in OKX, Binance, Bybit, and Bitget now skips instruments where `active=False` (OKX also skips `info.state='preopen'`), eliminating noisy `Symbol Format Error` warnings for delisted or pre-launch instruments with null precision fields.
- **Bitget WS API `_send` → `_send_or_raise`** — `BitgetWSApiClient._submit()` and `_uta_submit()` now use `_send_or_raise()` so a disconnected socket raises `ConnectionError` instead of silently dropping the order request. Consistent with the same fix already applied to OKX, Binance, and Bybit.
- **Test `nautilus_trader` import** — `test/base/__init__.py`, `test/base/conftest.py`, and `test/core/conftest.py` replaced `from nautilus_trader.model.identifiers import TraderId` with `from nexustrader.core.nautilius_core import TraderId`.

### Changed

- **`WSClient._send()`** now returns `bool` (`True` on success, `False` when not connected) instead of `None`.
- **`uv.toml`** — Added `link-mode = "copy"` to suppress hardlink warnings on cross-drive setups (e.g. cache on `C:`, venv on `H:`).

## [0.3.12] - 2026-03-25

### Added

- **`pandas` dependency** — `pandas>=3.0.1` is now a required dependency.

### Fixed

- **Non-Windows platform error handling** — `_check_platform()` in `_mt5_bridge.py` now raises `SystemExit` instead of `RuntimeError` when the system is not Windows, producing a clean exit with a descriptive message instead of an unhandled exception traceback.
- **MT5 `ImportError` on non-Windows** — `BybitTradeFiPrivateConnector.connect()` now wraps the executor call to `mt5_initialize()` in a `try/except ImportError` block, converting a confusing `ImportError` into a clean `SystemExit` with an actionable message.
- **Premature `disconnect()` crash** — Added `_mt5_connected` boolean guard to `BybitTradeFiPrivateConnector`. The `disconnect()` method now returns immediately if the MT5 connection was never established, preventing a crash when the engine shuts down after a failed connect.
- **Synchronous OMS init in constructor** — `BybitTradeFiOrderManagementSystem.__init__` no longer calls synchronous `_init_account_balance()` and `_init_position()` at construction time. These are now deferred to the async `_async_init_balance()` and `_async_init_position()` calls inside `PrivateConnector.connect()`, avoiding potential blocking on the event loop.

### Changed

- **`MetaTrader5` made optional** — The `MetaTrader5` package is now declared under `[project.optional-dependencies] tradfi` (Windows only) rather than as a hard dependency, so the package can be installed and imported on Linux/macOS without errors.
- **Demo strategy platform tips** — All Bybit TradFi demo strategies (`demo_market_data.py`, `demo_multi_symbol.py`, `demo_trading.py`, `xau_arb_market_data.py`) now include a platform-check tip at the top informing users that MT5 requires Windows.

## [0.3.11] - 2026-03-25

### Added

- **Bybit TradeFi (MT5) connector** — full integration with MetaTrader5-based traditional financial markets (Forex, Gold, Indices, Stocks) via the Bybit TradeFi brokerage:
  - `BybitTradeFiPublicConnector` — polling-based market data (BookL1, Trade, Kline, historical klines) backed by the MT5 terminal. No WebSocket required.
  - `BybitTradeFiPrivateConnector` — MT5 terminal initialisation, login, broker connectivity check, market loading, and order lifecycle management.
  - `BybitTradeFiOrderManagementSystem` — full order lifecycle: market orders, limit/pending orders, cancel, modify SL/TP, and polling-based status updates mapped to NexusTrader order states.
  - `BybitTradeFiExchangeManager` — loads tradeable symbols from the connected terminal and converts MT5 symbol names to NexusTrader format (e.g. `XAUUSD.s` → `XAUUSD_s.BYBIT_TRADFI`).
  - `BybitTradeFiExecutionManagementSystem` — routes `create_order` / `cancel_order` calls to the OMS.
  - `ExchangeType.BYBIT_TRADFI` constant and `BybitTradeFiAccountType` enum (`DEMO` / `LIVE`).
  - Optional dependency group: `uv add MetaTrader5` (Windows only).
  - MT5 constants (`TRADE_ACTION_*`, `ORDER_TYPE_*`, `ORDER_FILLING_*`, `ORDER_TIME_*`) are patched onto the module at runtime to handle the known PyPI packaging issue where `__init__.py` is absent.
  - Demo strategies: `strategy/bybit_tradfi/demo_market_data.py` and `strategy/bybit_tradfi/demo_trading.py`.

### Fixed

- **`nexuslog` stdout buffering** — `setup_nautilus_core` now defaults `batch_size=1` so log messages appear immediately instead of being held until 32 entries accumulate. Previously this caused complete silence while waiting for blocking operations (e.g. MT5 `initialize()`).
- **`request_klines` deadlock** — `BybitTradeFiPublicConnector.request_klines()` and related synchronous helpers (`request_ticker`, `request_all_tickers`) now submit work directly to `ThreadPoolExecutor` via `executor.submit().result()` instead of `task_manager.run_sync()`, avoiding a deadlock caused by blocking the event loop thread while waiting for a coroutine scheduled on that same loop.
- **Kline over-emission** — Kline polling previously emitted the current unconfirmed bar on every poll cycle (every 0.5 s). It now only emits when the bar timestamp changes (new bar opened or closed) or when `close` price changes within the current bar.

### Changed

- **MT5 symbol naming** — Internal dots in MT5 symbol names are replaced with underscores in the NexusTrader symbol format to avoid breaking the `symbol.EXCHANGE` parsing convention (e.g. `XAUUSD.s` → `XAUUSD_s.BYBIT_TRADFI`, `TSLA.s` → `TSLA_s.BYBIT_TRADFI`).
- **MT5 message routing** — Market data events now use `msgbus.publish(topic=...)` (consistent with all other connectors) instead of `msgbus.send(endpoint=...)`, so `on_bookl1`, `on_trade`, and `on_kline` strategy callbacks are correctly triggered.

## [0.3.10] - 2026-03-20

### Performance
- **WebSocket startup time reduced from ~12s to ~4-5s**: Eliminated fixed `asyncio.sleep()` delays during WebSocket authentication across all exchanges (Binance, Bybit, OKX, Bitget). Auth now uses `asyncio.Event` to proceed immediately upon server confirmation instead of unconditionally waiting 5 seconds per connection.
- **Parallel WebSocket connection startup**: Private connector `connect()` for Bybit, OKX, and Bitget now connects and authenticates the WS API client and the private WS client concurrently via `asyncio.gather()` instead of sequentially. Binance non-spot accounts similarly parallelize the WS API connection and the REST listen-key request.

### Changed
- **OMS auth response handling**: Each exchange OMS (Binance, Bybit, OKX, Bitget) now explicitly detects WebSocket auth/login responses and signals the corresponding WS client via `notify_auth_success()`, enabling event-driven auth completion.

## [0.3.9] - 2026-03-14

### Fixed
- **Binance `_position_mode_check` regression**: The four REST API calls in `_position_mode_check` (`get_fapi_v1_positionSide_dual`, `get_dapi_v1_positionSide_dual`, `get_papi_v1_um_positionSide_dual`, `get_papi_v1_cm_positionSide_dual`) were not wrapped with `_run_sync()` after the sync-to-async API client migration, causing a `'coroutine' object is not subscriptable` error on startup for Binance linear, inverse, and portfolio margin accounts.

## [0.3.8] - 2026-03-12

### Fixed
- **`Order.reason` now populated on failure**: All exchange OMS implementations (Binance, Bybit, OKX, Bitget, HyperLiquid) now set the `Order.reason` field when creating `FAILED` or `CANCEL_FAILED` orders. Previously the error message was only logged and discarded — strategies receiving `on_failed_order` / `on_cancel_failed_order` callbacks always saw `order.reason = None`. The field is now populated from the exchange error response (REST exceptions, WS API errors, batch order individual failures).

## [0.3.7] - 2026-03-12

### Removed
- **`nautilus-trader` dependency dropped**: NexusTrader no longer depends on `nautilus-trader`. The Rust/Cython build was the primary cause of slow cold-start times (several seconds on import). The dependency is fully replaced by lightweight pure-Python equivalents and `nexuslog`.

### Added
- **`nexustrader/core/nexus_core.py`** — pure-Python implementations of all components previously sourced from `nautilus_trader`:
  - `MessageBus` — in-process pub/sub (fan-out) and point-to-point endpoint routing.
  - `LiveClock` — wall-clock with `asyncio`-based repeating timers (`set_timer` / `cancel_timer`).
  - `TimeEvent` — lightweight dataclass carrying `ts_event` and `ts_init` timestamps in nanoseconds.
  - `TraderId`, `UUID4` — identifier helpers.
  - `hmac_signature` — HMAC-SHA256 hex digest (was `nautilus_pyo3.hmac_signature`).
  - `rsa_signature`, `ed25519_signature` — RSA / Ed25519 signing via `pycryptodome`.
- **`nexuslog`** added as a dependency (`nexuslog>=0.4.0`) to replace the nautilus structured logger.
- **`LogColor` pure-Python enum** in `nexustrader.constants` — replaces the `nautilus_pyo3.LogColor` import; same attribute names (`NORMAL`, `GREEN`, `BLUE`, `MAGENTA`, `CYAN`, `YELLOW`, `RED`).

### Changed
- **`nexustrader/core/nautilius_core.py`** — now imports from `nexus_core`; `Logger` is a thin shim around `nexuslog.getLogger`; `setup_nautilus_core` returns `(msgbus, clock)` instead of the former `(log_guard, msgbus, clock)` three-tuple.
- **`Logger` shim** accepts `**kwargs` (e.g. `color=LogColor.BLUE`) so existing strategy code requires no changes.
- **`Engine`** updated: removed `nautilus_pyo3.logger_flush()` calls; `_log_guard` attribute removed.
- **Installation**: `build-essential` / Rust toolchain no longer required on any platform.

### Performance
- Cold import time reduced from **~several seconds** to **~70 ms**.

## [0.3.6] - 2026-03-12

### Changed
- **Lazy credential validation**: Importing `nexustrader` no longer raises `FileNotFoundError` when `.keys/.secrets.toml` is missing. A warning is emitted instead, allowing public-only, mock, and backtest workflows to run without any credential file.
- **Multi-source credential resolution in `BasicConfig`**: Credentials can now be resolved from three sources in priority order: (1) direct pass, (2) Dynaconf settings via `settings_key` parameter, (3) plain environment variables via `BasicConfig.from_env()`. Directly passed values always take precedence.

### Added
- **`BasicConfig.settings_key` parameter**: Auto-resolves `api_key`, `secret`, and `passphrase` from Dynaconf settings (`.keys/.secrets.toml` or `NEXUS_` prefixed environment variables). Example: `BasicConfig(settings_key="BINANCE.DEMO", testnet=True)`.
- **`BasicConfig.from_env()` classmethod**: Creates a `BasicConfig` by reading `{PREFIX}_API_KEY`, `{PREFIX}_SECRET`, and `{PREFIX}_PASSPHRASE` from environment variables. Supports custom variable name overrides.

### Fixed
- **`BasicConfig.passphrase` type annotation**: Fixed from `str = None` to `str | None = None`.

## [0.3.5] - 2026-03-11

### Changed
- **`Order.oid` / `Order.eid` identifiers**: The internal order identifier has been renamed from `id`/`uuid` to `oid` (Order ID). The exchange-assigned order ID is now accessed via `eid` (Exchange ID). Update any code referencing `order.id`, `order.uuid`, or `order_id` keyword to use `order.oid` / `order.eid`.
- **`OrderRegistry` simplified**: The registry no longer manages a UUID↔ORDER_ID bidirectional mapping. It now tracks active OIDs directly. New API: `register_order(oid)`, `is_registered(oid)`, `unregister_order(oid)`, `register_tmp_order(order)`, `get_tmp_order(oid)`, `unregister_tmp_order(oid)`.
- **`AsyncCache` constructor**: Removed the `registry=` parameter (no longer required). A `clock: LiveClock` parameter is now required for internal cleanup scheduling.
- **`AsyncCache._order_status_update()` replaces `_order_initialized()`**: Internal order lifecycle tracking now uses a single unified `_order_status_update()` method.
- **REST API client sync/async unification**: Exchange REST API clients now expose a unified interface — async methods are transparently callable in a synchronous context via an `__getattr__` wrapper that dispatches to `run_sync()`. Sync rate limiters are stored as `self._limiter_sync` on each subclass rather than being passed to the base class.
- **`Trade` schema**: The `side` field (`OrderSide`) is now required when constructing a `Trade` object.

### Fixed
- **`connector.py` OID bug**: `Order` objects created inside `BaseConnector` incorrectly used `id=` instead of `oid=`, causing order tracking failures. Fixed to use `oid=UUID4().value`.

## [0.3.4] - 2026-02-25

### Changed
- **`cache.get_position()` and `cache.get_order()` now return `Optional[T]` directly**: Removed the `returns` library dependency. Replace any `.value_or(None)` calls with direct `None` checks, and `.bind_optional(lambda o: o.field).value_or(False)` with `o.field if o else False`.
- **`zmq` is now an optional dependency**: Only installed when using ZeroMQ signal integration. Install with `pip install nexustrader[signal]`. Regular users no longer have zmq forced into their environment.
- **Windows platform: signal handler warning suppressed**: The `NotImplementedError` from `asyncio.loop.add_signal_handler()` on Windows is now logged at DEBUG level instead of emitting a `UserWarning`.

### Removed
- **`returns` library removed from dependencies**: The functional programming monad library has been replaced with standard `Optional[T]` return types.
- **Dead dependencies removed**: `streamz`, `pathlib` (stdlib), `bcrypt`, `cython`, and `certifi` have been removed from production dependencies as they had zero usage in the codebase.
- **`pyinstrument` moved to dev dependencies**: The profiling tool is no longer installed in production environments.

## [0.3.3] - 2026-02-25

### Added
- **Batched WebSocket subscriptions**: Initial subscriptions and reconnection resubscriptions now process symbols in batches of 50 with a 0.5s delay between batches, enabling reliable support for thousands of symbols.
- **Inflight order tracking**: Orders submitted to the exchange but not yet acknowledged are tracked per symbol via `cache.get_inflight_orders()` and `cache.wait_for_inflight_orders()`, preventing race conditions during rapid submit/cancel sequences.
- **Synchronous cancel-intent marking**: `cancel_order`, `cancel_order_ws`, and `cancel_all_orders` now mark cancel intent synchronously at the Strategy layer, eliminating state conflicts with incoming exchange updates.
- **Order `reason` field**: The `Order` struct carries an optional `reason` field to capture human-readable failure context for `FAILED` and `CANCEL_FAILED` orders.
- **OMS null-OID guard**: `order_status_update` gracefully skips orders with `oid=None` (e.g. exchange-initiated liquidations), preventing `KeyError` crashes.
- **RetryManager utility**: A generic retry helper with exponential backoff and jitter at `nexustrader.base.retry.RetryManager`.

### Changed
- **Binance Spot**: Migrated from deprecated `listenKey` mechanism to the new `userDataStream.subscribe.signature` WebSocket API (effective 2026-02-20). Futures, Margin, and Portfolio Margin accounts continue using the existing `listenKey` flow.
- **OKX WebSocket order operations**: Adapted to OKX's parameter migration from `instId` to `instIdCode` (Phase 1: 2026-03-26, Phase 2: 2026-03-31). The system uses `instIdCode` when available and falls back to `instId` for backward compatibility.
- Moved `pyinstrument` from production dependencies to dev-only.

## [0.3.1] - 2026-01-15

### Added
- **Windows support**: NexusTrader now runs natively on Windows. `uvloop` is automatically skipped and the standard `asyncio` event loop is used instead.

## [0.2.37] - 2025-12-20

### Changed
- Batch subscription support for initial WebSocket connections.

## [0.2.36] - 2025-12-10

### Fixed
- Convert ticker prices to float in BybitPublicConnector.

### Changed
- Refactored callback-based WebSocket pong handling across all exchanges.
- Removed API key and secret handling from Bybit and Binance funding rate subscribers.

## [0.2.33] - 2025-11-28

### Fixed
- Updated order modification logic in ExecutionManagementSystem.

## [0.2.32] - 2025-11-25

### Fixed
- Updated exception handling to log symbol format errors in exchange managers.

## [0.2.31] - 2025-11-20

### Changed
- Enhanced minimum order amount calculations across exchanges to use price parameter.

## [0.2.30] - 2025-11-15

### Fixed
- Corrected order cancellation response code check in BinanceOrderManagementSystem.
- Updated order cancellation response decoding in BinanceApiClient.

## [0.2.28] - 2025-11-10

### Changed
- Updated order cancellation handling across exchanges.

## [0.2.27] - 2025-11-05

### Added
- Register temporary orders in Bitget and HyperLiquid order management systems.

## [0.2.26] - 2025-11-01

### Added
- Redis direct access property on AsyncCache.

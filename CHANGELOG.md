# Changelog

All notable changes to NexusTrader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.32] - 2026-05-05

### Fixed

- **Post-ACK terminal reconciliation for fast-closing orders** - Binance, Bitget, Bybit, OKX, and HyperLiquid now schedule short REST `fetch_order(..., force_refresh=True)` reconciliation for `MARKET` and `IOC` / `FOK` orders after successful REST or WebSocket create ACKs. If the private order stream misses a fast `FILLED` / `CANCELED` / `EXPIRED` terminal update, NexusTrader writes back the real exchange state instead of leaving the order stuck in `PENDING` / `ACCEPTED` until cache expiry.
- **Order status cache updates have a public API** - Added `AsyncCache.update_order_status()` as the public wrapper around validated order status updates. OMS implementations now use the public cache API instead of calling private `_order_status_update()` directly.
- **Batch create ACK paths use the same terminal reconciliation** - Binance, Bybit, OKX, and HyperLiquid batch create success paths now reuse the post-ACK reconciliation helper for fast-closing orders. Bitget batch create remains unimplemented and Bybit TradFi continues to use the MT5 synchronous / polling model.

### Tests

- Added regression coverage for post-ACK terminal reconciliation, retry behavior, duplicate scheduling suppression, and IOC limit orders.
- Added regression coverage for the public `AsyncCache.update_order_status()` API.
- Verified with `uv run ruff check`, `uv run pytest test -q`, and `py -m compileall`.

## [0.3.31] - 2026-05-04

### Fixed

- **Binance cancel ACK terminal states are dispatched immediately** - Binance WebSocket cancel responses now parse returned order fields such as `status`, `origQty`, `executedQty`, `price`, `avgPrice`, and side/type metadata. When the ACK already contains a terminal state such as `CANCELED` or `FILLED`, NexusTrader updates and dispatches that real state instead of leaving the order stuck in `CANCELING` while waiting for a private user-data event.
- **Cancel success paths now perform short REST reconciliation** - Binance, Bitget, Bybit, OKX, and HyperLiquid now schedule a short delayed REST `fetch_order(..., force_refresh=True)` after successful cancel ACKs that still leave the order in `CANCELING`. If the private order stream misses or delays the terminal event, the REST result writes back the real `FILLED` / `CANCELED` / `EXPIRED` state quickly instead of relying on a long strategy-level timeout.
- **Binance user-data stream expiry is handled explicitly** - Binance `listenKeyExpired` events now trigger user-data stream recovery and reconnect resync. Private connector health also includes the latest order and account update timestamps to make half-stale private streams easier to detect.

### Tests

- Added regression coverage for Binance cancel ACKs that include terminal status.
- Added regression coverage for cancel-success REST reconciliation when cache remains `CANCELING`.
- Added regression coverage for Binance `listenKeyExpired` recovery task scheduling.

## [0.3.30] - 2026-05-04

### Fixed

- **Bybit server-time sync uses curl_cffi response attributes** - Fixed `_sync_time_if_needed()` to read `response.content` and `response.status_code` from `curl_cffi.requests.AsyncSession` responses instead of the aiohttp-style `await response.read()` and `response.status`. This prevents repeated `'Response' object has no attribute 'read'` warnings before signed Bybit REST requests.
- **Bybit time-sync failures now use a short retry backoff** - Failed server-time sync attempts now set a 5 second retry gate, avoiding a warning on every signed request during short network or exchange-side failures while still retrying much sooner than the normal 60 second success interval.
- **Cancel WS `Unknown order` / not-found errors now trigger REST reconciliation** - Binance, Bitget, Bybit, OKX, and HyperLiquid now immediately fetch the order via REST before reporting cancel failure when WebSocket cancel returns an unknown/not-found/already-canceled/already-filled style error. If REST confirms the order is already closed, the real `FILLED` / `CANCELED` / `EXPIRED` state is written back and the cancel ACK wait is resolved, avoiding a long strategy-level timeout before exposure is corrected.

### Tests

- Added regression coverage for Bybit time sync using curl_cffi-style response content.
- Added regression coverage for short retry backoff after failed Bybit time sync.
- Added regression coverage for Binance cancel `Unknown order` reconciliation to closed and still-open REST states.
- Added parameterized regression coverage for Bitget, Bybit, OKX, and HyperLiquid cancel rejection reconciliation to closed, still-open, and missing REST states.

## [0.3.29] - 2026-05-04

### Fixed

- **OKX import dependency is declared** - Added `orjson` to the default project dependencies and `requirements.txt`. `nexustrader.exchange.okx.exchange` imports `orjson` while `nexustrader.engine` imports the exchange package, so fresh installs of `0.3.28` could fail during `import nexustrader.engine` and then be misreported by downstream broad exception handlers as "nexustrader not available."

### Tests

- Verified `import nexustrader.engine`.
- Verified dependency metadata includes `orjson`.

## [0.3.28] - 2026-05-04

### Fixed

- **Linux/macOS base installs no longer require MetaTrader5** - Removed `metatrader5` from the default project dependencies. The MT5 package is now installed only through the `tradfi` extra and only on Windows, preventing Linux installs from failing on the Windows-only wheel.
- **Lockfile metadata matches the Windows-only TradFi dependency** - Updated `uv.lock` so `MetaTrader5` is no longer listed as a base dependency while remaining available for `nexustrader[tradfi]` on Windows.
- **Legacy requirements no longer pull removed build-heavy dependencies** - Synchronized `requirements.txt` with the current production dependency set, removing stale entries such as `nautilus-trader`, `streamz`, `pathlib`, `cython`, and other packages that could break or slow Linux installs.
- **Docker build installs the current project instead of an external private repository** - Simplified the Dockerfile to install NexusTrader from the local build context and added `.dockerignore` to keep virtualenvs, git metadata, caches, keys, and generated artifacts out of the image.

### Documentation

- Updated README and installation docs to use `pip install "nexustrader[tradfi]"` or `uv add "nexustrader[tradfi]"` for Windows TradFi support, and clarified that base Linux/macOS installs do not install `MetaTrader5`.

## [0.3.27] - 2026-05-03

### Fixed

- **Bybit TradFi position cache now stays synchronized with MT5** - The Bybit TradFi OMS now refreshes MT5 positions into `self.cache` after connector startup, on a background polling loop, after immediate market fills, and after pending-order close events. This makes `self.cache.get_position("XAUUSD_s.BYBIT_TRADFI")` usable during live MT5 trading instead of only reflecting the initial startup snapshot.
- **Stale Bybit TradFi positions are cleared when MT5 reports no open position** - MT5 `positions_get()` returning an empty list now removes stale `BYBIT_TRADFI` positions from the cache. A `None` response is treated as an MT5 read failure and does not clear cache state, preventing transient terminal/API errors from falsely flattening positions.
- **Bybit TradFi symbol and side semantics are documented** - Documentation now explains that cache lookups must use NexusTrader symbols such as `XAUUSD_s.BYBIT_TRADFI`, not raw MT5 symbols such as `XAUUSD.s`, and that `Position.side` uses `PositionSide.LONG` / `PositionSide.SHORT` while order direction remains `OrderSide.BUY` / `OrderSide.SELL`.
- **OKX market loading accepts integer `instIdCode` values** - OKX can return numeric `instIdCode` values from the public instruments endpoint. Market metadata decoding now accepts both string and integer values, preserving mappings such as `BTCUSDT-PERP.OKX` to `BTC-USDT-SWAP` for public subscriptions and WebSocket order operations.

### Tests

- Added regression coverage for Bybit TradFi MT5 position refresh writing Nexus symbols into cache.
- Added regression coverage for stale Bybit TradFi position cleanup when MT5 returns no open positions.
- Added regression coverage for OKX raw SWAP market parsing with numeric `instIdCode`.
- Verified with `uv run ruff check` and `uv run pytest`.

## [0.3.26] - 2026-04-30

### Fixed

- **`on_start()` now sees the engine event loop as current** - `Engine.start()` sets the engine loop as the current thread event loop before calling the user `on_start()` hook, so existing code using `asyncio.get_event_loop()` can schedule tasks without reaching into `engine._loop`.
- **`Strategy.set_timer()` compatibility restored** - Reintroduced the old public `set_timer(callback, interval, ...)` API as a deprecated wrapper around `schedule(..., trigger="interval")`, emitting `DeprecationWarning` instead of failing with `AttributeError`.

### Tests

- Added regression coverage for `on_start()` event-loop visibility.
- Added regression coverage for deprecated `Strategy.set_timer()` compatibility.

## [0.3.25] - 2026-04-30

### Fixed

- **Credential file is no longer required at import/startup** - Restored lazy credential validation so importing `nexustrader.constants` no longer raises `FileNotFoundError` when `.keys/.secrets.toml` is absent. Missing TOML credentials now emit a warning while public-only, mock, and direct-credential workflows can continue.
- **Multiple credential sources are supported again** - `BasicConfig` now accepts credentials directly, can resolve them from Dynaconf via `settings_key`, and can read plain environment variables with `BasicConfig.from_env()`. This restores support for TOML files, `NEXUS_` prefixed environment variables, and regular `{PREFIX}_API_KEY` / `{PREFIX}_SECRET` variables without forcing any one source.
- **Public market-data examples are not blocked by secret-file checks** - Public subscription workflows can run without `.keys/.secrets.toml` as long as they do not need private trading credentials.

### Tests

- Verified importing `nexustrader.constants` from a directory without `.keys/.secrets.toml` only warns and exits successfully.
- Verified `BasicConfig.from_env()` resolves ordinary environment variables.
- Verified `BasicConfig(settings_key=...)` resolves `NEXUS_` nested environment variables.
- Verified changed config modules with `ruff check` and `py_compile`.

## [0.3.24] - 2026-04-30

### Added

- **Local compatibility layer for core nautilus-style primitives** - Added lightweight in-repo replacements for the core runtime objects NexusTrader uses, including `MessageBus`, `LiveClock`, `TraderId`, `UUID4`, signature helpers, and minimal HTTP/WebSocket shims. This removes the need for strategies and tests to import those objects from `nautilus-trader` directly.
- **WebSocket health reporting** - Public/private connector WebSocket clients now track connection state, subscription count, last message timestamp/age, message count, reconnect count, and disconnect timestamps through `get_health()`.
- **Direct Binance kline WebSocket subscriptions** - Binance kline subscriptions now support direct combined-stream WebSocket clients with stream chunking, heartbeat handling, receive timeouts, reconnect backoff, and dedicated health reporting.
- **Benchmark scripts and test data** - Added local benchmark helpers for `picows`, `websockets`, `aiosonic`/`aiohttp`, JSON format handling, and clock performance.
- **Release documentation** - Added this project changelog and Sphinx release notes covering historical releases through `0.3.23`.

### Changed

- **Dependency and platform profile simplified** - Project metadata now targets Python `>=3.11,<3.13`, skips `uvloop` on Windows, removes the committed `uv.lock`, and uses a smaller dependency set centered on the currently supported runtime path.
- **Windows event-loop handling** - `Engine` now selects `WindowsSelectorEventLoopPolicy` on Windows so `aiohttp`/`aiodns` works reliably without `uvloop`; non-Windows platforms continue to use `uvloop`.
- **Logging routed through local `SpdLog` wrapper** - Runtime logging paths were moved to the in-repo logging wrapper rather than the previous nautilus setup path.
- **Exchange support surface narrowed and refactored** - Binance, Bybit, and OKX remain the active documented exchange paths. Deprecated/unused factory modules, CLI/web app modules, persistence backends, Bybit TradFi, Bitget, and HyperLiquid implementation/docs were removed or excluded from the main documentation surface.
- **Documentation reorganized** - Sphinx API, concept, exchange, installation, and quickstart docs were updated to match the current supported modules and examples.
- **Example strategies updated** - Binance, Bybit, and OKX examples were refreshed around the current config model, public subscriptions, signal handling, cancel/modify examples, and simplified supported workflows.

### Fixed

- **Bybit ccxt market loading timestamp failures** - Bybit market loading now disables ccxt's private currency prefetch by default, enables time-difference adjustment, and uses a 10 second receive window so startup does not fail on private coin-info timestamp checks.
- **Bybit signed REST timestamp drift** - The Bybit REST client now uses a 10 second receive window and syncs a cached Bybit server-time offset before signed requests.
- **Bybit public subscription examples no longer require private startup calls** - `strategy/bybit/subscribe_bookl2.py` and `strategy/bybit/subscribe_klines.py` now configure public connectors only, avoiding `/v5/account/wallet-balance` initialization for public market-data demos.
- **OKX market loading sandbox parsing failures** - OKX markets are now loaded from raw public instrument endpoints and malformed instruments are skipped without aborting engine startup.
- **Message bus compatibility gaps** - Added compatibility methods such as `MessageBus.register()` and `MessageBus.deregister()` for strategy endpoint handlers and tests.
- **Windows test/runtime compatibility** - Test fixtures and runtime setup now import `TraderId` and related primitives from the local compatibility layer.

### Tests

- Added focused coverage for WebSocket health tracking, local message bus behavior, OKX raw market loading, and Bybit exchange/REST timestamp configuration.
- Updated cache, registry, EMS, and mock connector tests to use the current local runtime primitives.
- Verified focused Bybit fixes with `uv run pytest test\exchange\test_bybit_exchange_config.py test\exchange\test_bybit_rest_api.py -q`.
- Verified changed Bybit modules/examples with `ruff check` and `py_compile`.

## [0.3.23] - 2026-04-13

### Fixed

- **`cancel_all_orders()` skipped already-marked orders on Bitget / HyperLiquid / OKX EMS** - `Strategy.cancel_all_orders()` marks open orders with cancel intent before dispatch. The exchange-specific EMS overrides were still calling `get_open_orders()` without `include_canceling=True`, so the per-order cancel fanout could see an empty set and never submit the actual cancel requests. Those paths now query the full open-order set and fan out correctly.
- **OKX now implements REST batch cancel for `cancel_all_orders()`** - `OkxOrderManagementSystem.cancel_all_orders()` no longer returns a no-op. It now batches client order IDs into the OKX `cancel-batch-orders` REST endpoint, marks successful requests as `CANCELING`, and surfaces per-order `CANCEL_FAILED` states on partial or full failure.
- **Modify-order status updates no longer violate the order state machine** - Binance / Bybit / OKX amend flows previously wrote `PENDING` after a successful modify request. For already-open orders this produced invalid transitions such as `ACCEPTED -> PENDING`, which were rejected by `STATUS_TRANSITIONS` and silently dropped. The amend paths now reuse the cached live status so valid transitions such as `ACCEPTED -> ACCEPTED` and `PARTIALLY_FILLED -> PARTIALLY_FILLED` are accepted.
- **Modify-order cache updates no longer erase live order state** - Bybit / OKX amend success handlers were writing partial `Order` snapshots back into the cache, which could wipe previously known `amount`, `filled`, `remaining`, `side`, `type`, `time_in_force`, and related metadata, especially on price-only amend requests or partially filled orders. The amend handlers now preserve cached execution state and only overwrite fields that were actually changed; Binance also preserves the effective amount when only price is amended.

## [0.3.22] - 2026-04-04

### Changed

- **Logging backend replaced: `nexuslog` → `loguru`** — The Rust-backed `nexuslog` package has been replaced with [`loguru`](https://github.com/Delgan/loguru) — a pure-Python, zero-build-dependency logger. The `Logger` shim interface is fully backward-compatible.
- **Time-based log rotation added** — `setup_nautilus_core()` / `setup_nexus_core()` now accepts a `filename` parameter that, when set, enables loguru's built-in time-rotating sink (default: midnight rotation, 30-day retention, async non-blocking via `enqueue=True`). Configurable via `rotation_when`, `rotation_interval`, and `rotation_backup_count`.
- **`TRACE` level now fully supported** — loguru natively supports `TRACE` (level 5). `logger.trace()` calls are emitted at true TRACE severity, not remapped to DEBUG.

## [0.3.20] - 2026-04-02

### Changed

- **Bybit TradFi: default tick poll interval reduced from 100 ms to 10 ms** — `BybitTradeFiPublicConnector.TICK_POLL_INTERVAL` changed from `0.1` to `0.01`. Each `symbol_info_tick()` call completes in ~15–60 µs over the local MT5 named-pipe IPC, so 100 ms was far more conservative than necessary. Average bid/ask detection latency drops from ~50 ms to ~5 ms with negligible CPU overhead.

### Added

- **`PublicConnectorConfig.tick_poll_interval`** — New optional `float | None` field (default `None`) that overrides the MT5 tick polling rate when set. The factory passes the value through to `BybitTradeFiPublicConnector`. Other exchange connectors ignore this field.
- **`price_type` kwarg for Bybit TradFi limit orders** — `BybitTradeFiOrderManagementSystem.create_order()` now reads an optional `price_type` kwarg (`"bid"`, `"ask"`, or `"opponent"`) from the strategy call. When present, the OMS calls `symbol_info_tick()` at the moment the order is dispatched to MT5 and substitutes the fresh quote for the strategy-supplied price. `"opponent"` resolves to best ask for buy orders and best bid for sell orders. Has no effect on other exchanges.

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

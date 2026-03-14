# Changelog

All notable changes to NexusTrader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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

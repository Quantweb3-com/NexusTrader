# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NexusTrader is a professional-grade quantitative trading platform built with Python 3.11+ that focuses on high-performance, low-latency trading across multiple exchanges. It features a modular, event-driven architecture with Rust-powered core components for maximum performance.

## Development Commands

### Dependencies and Setup
```bash
# Install with uv (package manager used in this project)
uv sync

# Install development dependencies
uv sync --group dev

# Install pre-commit hooks (required for contributions)
uv add --dev pre-commit
pre-commit install
```

### Testing
```bash
# Run all tests with async support
uv run pytest

# Run specific test modules
uv run pytest test/core/
uv run pytest test/core/test_entity.py

# Test configuration: pytest.ini enables asyncio_mode = auto
```

### Code Quality
```bash
# Linting and formatting (via ruff)
uv run ruff check
uv run ruff format
```

### Development Infrastructure
```bash
# Start Redis, PostgreSQL, Loki logging stack
docker-compose up -d

# Clear log files
./clear.sh

# Process management (production)
pm2 start ecosystem.config.js
```

## Architecture Overview

### Core Components
- **Engine**: Central orchestrator managing all trading systems (`nexustrader/engine.py`)
- **Strategy**: Base class for trading logic with multiple execution modes (`nexustrader/strategy.py`)
- **Connectors**: Exchange-specific public (market data) and private (trading) connectors
- **EMS** (Execution Management System): Order submission and execution
- **OMS** (Order Management System): Order state tracking and management
- **Cache**: High-performance data caching layer (`nexustrader/core/cache.py`)
- **Registry**: Order and component tracking (`nexustrader/core/registry.py`)

### Exchange Integration
Each exchange follows a consistent pattern in `nexustrader/exchange/{exchange}/`:
- **PublicConnector**: Market data WebSocket streams
- **PrivateConnector**: Account data and order execution
- **EMS/OMS**: Exchange-specific order management
- **ExchangeManager**: Coordinate connectors and systems

Supported exchanges:
- **Primary**: Binance, Bybit, OKX (full implementation)
- **Additional**: Bitget, Hyperliquid

### Strategy Execution Modes
1. **Event-Driven**: React to market events (`on_bookl1`, `on_trade`, `on_kline`)
2. **Timer-Based**: Scheduled execution using `schedule()` method
3. **Signal-Based**: Custom signal processing (`on_custom_signal`)

### Performance Optimizations
- **uvloop**: High-performance event loop (2-4x faster than asyncio)
- **picows**: Cython-based WebSocket library (C++ performance)
- **msgspec**: Ultra-fast serialization/deserialization
- **nautilus-trader**: Rust-powered MessageBus and Clock components

## Key File Locations

### Core Framework
- `nexustrader/engine.py` - Main trading engine
- `nexustrader/strategy.py` - Strategy base class
- `nexustrader/config.py` - Configuration management
- `nexustrader/schema.py` - Data structures and schemas
- `nexustrader/indicator.py` - Technical indicators framework

### Base Classes
- `nexustrader/base/connector.py` - Base connector implementations
- `nexustrader/base/ems.py` - Base execution management
- `nexustrader/base/oms.py` - Base order management

### Exchange Implementations
Each exchange directory contains:
- `connector.py` - Public/Private connectors
- `ems.py` - Exchange-specific execution management
- `oms.py` - Exchange-specific order management
- `schema.py` - Exchange data structures
- `websockets.py` - WebSocket implementations
- `rest_api.py` - REST API client

### Configuration and Data
- `nexustrader/constants.py` - Enums and constants
- `nexustrader/backends/` - Database backends (Redis, PostgreSQL, SQLite)
- `strategy/` - Example strategies organized by exchange

## Environment Configuration

Copy `env.example` to `.env` and configure:
```bash
# Redis Configuration
NEXUS_REDIS_HOST=127.0.0.1
NEXUS_REDIS_PORT=6379
NEXUS_REDIS_DB=0
NEXUS_REDIS_PASSWORD=your_redis_password

# PostgreSQL Configuration  
NEXUS_PG_HOST=localhost
NEXUS_PG_PORT=5432
NEXUS_PG_USER=postgres
NEXUS_PG_PASSWORD=your_postgres_password
NEXUS_PG_DATABASE=postgres
```

## Custom Indicator Development

Indicators support automatic warmup with historical data:

```python
class CustomIndicator(Indicator):
    def __init__(self, period: int = 20):
        super().__init__(
            params={"period": period},
            name=f"Custom_{period}",
            warmup_period=period * 2,  # Required historical periods
            warmup_interval=KlineInterval.MINUTE_1,  # Data interval
        )
    
    def handle_kline(self, kline: Kline):
        # Process kline data
        pass
```

Register indicators in strategy:
```python
self.register_indicator(
    symbols="BTCUSDT-PERP.BINANCE",
    indicator=self.custom_indicator,
    data_type=DataType.KLINE,
    account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
)
```

## Symbol Format

All symbols follow the pattern: `{base}{quote}-{instrument_type}.{exchange}`

Examples:
- `BTCUSDT-PERP.BINANCE` (Binance perpetual futures)
- `BTCUSDT-PERP.OKX` (OKX perpetual futures)
- `BTCUSDT-PERP.BYBIT` (Bybit perpetual futures)

## Configuration Management

Configuration uses `dynaconf` for environment-based settings:
- API credentials stored in `settings` system
- Environment variables via `.env` files
- Exchange account types specify testnet/mainnet and account categories

## Contributing Guidelines

From CONTRIBUTING.md:
1. Open GitHub issues before implementing changes
2. Fork from main branch and keep synced
3. Install pre-commit hooks (mandatory)
4. Small, focused pull requests with clear descriptions
5. Reference GitHub issues in PR descriptions
6. Target main branch for all PRs

## Infrastructure Services

Development stack includes:
- **Redis**: Data caching and pub/sub messaging
- **PostgreSQL**: Persistent data storage
- **Grafana Loki**: Centralized logging
- **Promtail**: Log shipping agent

Start with: `docker-compose up -d`

## Development Conventions

### Import Guidelines
- Always use absolute path imports

## Claude Code Memories

### CLI Usage Warnings
- Do not run nexustrader-cli moniter in claude code

### Ruff Usage
- Lint all files in the current directory with `uvx ruff check`
- Format all files in the current directory with `uvx ruff format`
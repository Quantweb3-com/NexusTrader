<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/source/_static/logo-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/source/_static/logo-light.png">
  <img alt="nexustrader Logo" src="docs/source/_static/logo-light.png">
</picture>

# NexusTrader

> **Make every trade deterministic.**

---

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue)
![Version](https://img.shields.io/pypi/v/nexustrader?color=blue)
![Stars](https://img.shields.io/github/stars/Quantweb3-com/NexusTrader?style=social)

---

NexusTrader is built for one thing: making live trading execution reliable.

And now, with [NexusTrader MCP](https://github.com/Quantweb3-com/NexusTrader-mcp), AI agents can trade through the same execution-safe stack.

If you care about reliable trading, a star helps others discover the project.

## Links

- Website: [https://nexustrader.quantweb3.ai/](https://nexustrader.quantweb3.ai/)
- Docs: [https://nexustrader.readthedocs.io/en/latest/](https://nexustrader.readthedocs.io/en/latest/)
- NexusTrader MCP: [https://github.com/Quantweb3-com/NexusTrader-mcp](https://github.com/Quantweb3-com/NexusTrader-mcp)
- Releases: [https://github.com/Quantweb3-com/NexusTrader/releases](https://github.com/Quantweb3-com/NexusTrader/releases)
- Support: [quantweb3.ai@gmail.com](mailto:quantweb3.ai@gmail.com)

## The Problem

If you trade live, you have probably seen at least one of these failures:

- An order was sent, but you were not sure whether it was actually confirmed.
- Network jitter, retries, or replayed signals created duplicate trades.
- A WebSocket disconnect left balances, positions, or open orders out of sync.
- A fast market exposed race conditions that looked fine in backtests.
- Debugging execution failures turned into guesswork.

## What Is NexusTrader?

NexusTrader is an **execution reliability layer** for live trading systems.

It is designed to help a strategy remain correct under delayed ACKs, reconnects, retries, and exchange-side uncertainty.

It is not just an exchange connector. It is the layer that keeps execution correct when markets, networks, and APIs behave badly.

## AI-Native Trading With MCP

[NexusTrader MCP](https://github.com/Quantweb3-com/NexusTrader-mcp) exposes NexusTrader through the Model Context Protocol so AI systems can trade through the same deterministic execution layer.

What this means in practice:

- Trade from AI agents
- Trigger trades from natural language workflows
- Connect the same trading backend to multiple MCP-compatible tools

Works with:

- OpenClaw
- Cursor
- Codex
- Claude Code

Example intent:

> "Buy BTC if funding rate < 0 and log it."

With MCP in the loop, AI can analyze the condition, generate the signal, submit the order through NexusTrader, and log the result through one connected workflow.

## Core Capabilities

- **Deterministic Order Execution**: WebSocket orders are tracked until ACK, and ACK timeout triggers REST confirmation before the system decides the request failed.
- **Idempotent Orders**: `client_oid` and `idempotency_key` help suppress duplicate creates and make retries safe.
- **Auto-Recovery After Disconnect**: Private WS reconnect can automatically resync balances, positions, and open orders, then emit a diff to the strategy layer.
- **Safer Failure Handling**: WS send failure, ACK timeout, and explicit rejection are surfaced as different failure paths instead of being mixed together.
- **Observable Execution State**: Failed orders carry a `reason`, WS lifecycle events are published, and pending ACK state is tracked explicitly.
- **MCP-Friendly AI Integration**: The NexusTrader MCP layer lets you connect the trading stack to MCP-compatible assistants such as Codex, Claude Code, Cursor, and OpenClaw without building a separate adapter for each tool.

## Why Not Other Tools?

| Capability | CCXT | Hummingbot | NexusTrader |
| --- | --- | --- | --- |
| Order confirmation path | ❌ | ❌ | ✅ |
| Duplicate order protection | ❌ | ❌ | ✅ |
| Reconnect reconciliation | ❌ | ⚠️ | ✅ |
| WS ACK timeout recovery | ❌ | ❌ | ✅ |
| AI trading support via MCP | ❌ | ❌ | ✅ |
| Natural language trading workflows | ❌ | ❌ | ✅ |
| Multi-exchange live trading | ⚠️ | ✅ | ✅ |

## One-Liner

> Others let you trade. NexusTrader helps ensure the trade is correct, even when AI is part of the loop.

## Architecture

```text
Strategy
   ↓
NexusTrader
   ↓
Exchange APIs
```

## Use Cases

- Cross-exchange arbitrage
- Market making
- High-frequency trading
- Multi-symbol strategies
- Fully automated live trading systems
- TradFi workflows via Bybit TradFi (MT5)

## Performance Highlights

- `uvloop` for a faster event loop on non-Windows systems
- `picows` for low-latency WebSocket handling
- `msgspec` for fast serialization and structured models
- Batched subscriptions and inflight tracking for high-symbol-count strategies
- Lightweight pure-Python runtime plus `loguru` (zero build requirements, built-in time-based log rotation)

## Installation

```bash
pip install nexustrader
```

TradFi support on Windows:

```bash
pip install nexustrader MetaTrader5
```

## Quick Start

Inside a strategy, submit orders with deterministic identifiers:

```python
from decimal import Decimal
from nexustrader.constants import OrderSide, OrderType

self.create_order_ws(
    symbol="BTCUSDT-PERP.OKX",
    side=OrderSide.BUY,
    type=OrderType.LIMIT,
    amount=Decimal("0.001"),
    price=Decimal("90000"),
    client_oid="entry_001",
    idempotency_key="signal:btc:entry",
)
```

Why this matters:

- The strategy makes the decision.
- NexusTrader makes execution safer.
- MCP lets AI systems access the same trading workflow.

## Start Here

- Read the [installation guide](https://nexustrader.readthedocs.io/en/latest/installation.html)
- Read the [quickstart docs](https://nexustrader.readthedocs.io/en/latest/quickstart/index.html)
- Read the [release notes](https://nexustrader.readthedocs.io/en/latest/release_notes.html)
- Check runnable examples in [`strategy/`](strategy)

## Supported Exchanges

- Binance
- Bybit
- OKX
- Bitget
- HyperLiquid
- Bybit TradFi (MT5)

## Bybit TradFi

NexusTrader also supports traditional financial markets through [Bybit TradFi](https://www.bybit.com/en/trade/tradfi/) with MetaTrader 5 as the execution backend.

- Windows only
- Supports Forex, Gold, Indices, and Stocks
- Symbol mapping is normalized into NexusTrader format such as `XAUUSD_s.BYBIT_TRADFI`

See the docs for installation, credentials, and runnable examples.

## Contributing

Contributions are welcome.

- Open an issue first if you are planning a feature or non-trivial change.
- Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before opening a pull request.
- Target the `main` branch for pull requests.

## Social

[![X (Twitter)](https://img.shields.io/badge/X_(Twitter)-000000?logo=x&logoColor=white)](https://x.com/quantweb3_ai)
[![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/BR8VGRrXFr)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/+6e2MtXxoibM2Yzlk)

## License

NexusTrader is released under the MIT License. See [`LICENSE`](./LICENSE) for details.

## Star History

<a href="https://www.star-history.com/#Quantweb3-com/NexusTrader&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Quantweb3-com/NexusTrader&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Quantweb3-com/NexusTrader&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Quantweb3-com/NexusTrader&type=Date" />
 </picture>
</a>

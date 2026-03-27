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

**If this project helps you, please star it.**

## Links

- Website: [https://nexustrader.quantweb3.ai/](https://nexustrader.quantweb3.ai/)
- Docs: [https://nexustrader.readthedocs.io/en/latest/](https://nexustrader.readthedocs.io/en/latest/)
- Releases: [https://github.com/Quantweb3-com/NexusTrader/releases](https://github.com/Quantweb3-com/NexusTrader/releases)
- Support: [quantweb3.ai@gmail.com](mailto:quantweb3.ai@gmail.com)

## The Problem

If you trade live, you have probably seen at least one of these failures:

- An order was sent, but you were not sure whether it actually reached the exchange.
- Network jitter or retries created duplicate orders.
- A WebSocket disconnect left balances, positions, or open orders out of sync.
- A fast market exposed race conditions that were invisible in backtests.
- Debugging execution issues turned into guesswork.

## What Is NexusTrader?

NexusTrader is not just an exchange connector or a strategy shell.

It is an **execution reliability layer** for live trading systems, built to help your strategy stay correct under delayed ACKs, reconnects, retries, and exchange-side uncertainty.

## What Actually Matters

- **Deterministic Order Execution**: WebSocket orders are tracked until ACK, and ACK timeout triggers REST confirmation before the system decides the request failed.
- **Idempotent Orders**: `client_oid` and `idempotency_key` help suppress duplicate creates and make retries safe.
- **Auto-Recovery After Disconnect**: Private WS reconnect can automatically resync balances, positions, and open orders, then emit a diff to the strategy layer.
- **Safer Failure Handling**: WS send failure, ACK timeout, and explicit rejection are surfaced as different failure paths instead of being mixed together.
- **Observable Execution State**: Failed orders carry a `reason`, WS lifecycle events are published, and pending ACK state is tracked explicitly.

## Why Not Other Tools?

| Capability | CCXT | Hummingbot | NexusTrader |
| --- | --- | --- | --- |
| Order confirmation path | ❌ | ❌ | ✅ |
| Duplicate order protection | ❌ | ❌ | ✅ |
| Reconnect reconciliation | ❌ | ⚠️ | ✅ |
| WS ACK timeout recovery | ❌ | ❌ | ✅ |
| Multi-exchange live trading | ⚠️ | ✅ | ✅ |

## One-Liner

> Other tools help you trade. NexusTrader helps you trust your execution path.

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
- Lightweight pure-Python runtime plus `nexuslog`

## Installation

```bash
pip install nexustrader
```

TradFi support on Windows:

```bash
pip install nexustrader MetaTrader5
```

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

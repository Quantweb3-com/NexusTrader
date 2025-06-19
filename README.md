<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/source/_static/logo-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/source/_static/logo-light.png">
  <img alt="nexustrader Logo" src="docs/source/_static/logo-light.png">
</picture>


---

![License](https://img.shields.io/badge/license-MIT-blue.svg)![Python](https://img.shields.io/badge/python-3.11%20|%203.12-blue)![Version](https://img.shields.io/pypi/v/nexustrader?&color=blue)

- **Docs**: https://nexustrader.readthedocs.io/en/latest/
- **Support**: [quantweb3.ai@gmail.com](mailto:quantweb3.ai@gmail.com)

```python
                ###############################################################
                ##                                                           ##
                ##                                                           ##
                ##         ███    ██ ███████ ██   ██ ██    ██ ███████        ##
                ##         ████   ██ ██       ██ ██  ██    ██ ██             ##
                ##         ██ ██  ██ █████     ███   ██    ██ ███████        ##
                ##         ██  ██ ██ ██       ██ ██  ██    ██      ██        ##
                ##         ██   ████ ███████ ██   ██  ██████  ███████        ##
                ##                                                           ##
                ##                                                           ##
                ##     ████████ ██████   █████  ██████   ███████ ██████      ##
                ##        ██    ██   ██ ██   ██ ██   ██  ██      ██   ██     ##
                ##        ██    ██████  ███████ ██   ██  █████   ██████      ##
                ##        ██    ██   ██ ██   ██ ██   ██  ██      ██   ██     ##
                ##        ██    ██   ██ ██   ██ ██████   ███████ ██   ██     ##
                ##                                                           ##
                ##                                                           ##
                ###############################################################
```
## Introduction

NexusTrader is a professional-grade open-source quantitative trading platform, specifically designed for **large capital
management** and **complex strategy development**, dedicated to providing high-performance, scalable, and user-friendly
quantitative trading solutions.

## Overview

### Core Advantages

- 🚀 **Professionally Optimized Order Algorithms：** Deep optimization for algorithmic orders including TWAP, effectively
   reducing market impact costs. Users can easily integrate their own execution signals to achieve more efficient and
   precise order execution.
- 💰 **Professional Arbitrage Strategy Support：** Provides professional optimization for various arbitrage strategies,
   including funding rate arbitrage and cross-exchange arbitrage, supporting real-time tracking and trading of thousands
   of trading pairs to help users easily capture arbitrage opportunities.
- 🚧 **Full-Featured Quantitative Trading Framework：** Users don't need to build frameworks or handle complex exchange
   interface details themselves. NexusTrader has integrated professional position management, order management, fund
   management, and statistical analysis modules, allowing users to focus on writing strategy logic and quickly implement
   quantitative trading.
- 🚀 **Multi-Market Support and High Scalability：** Supports large-scale multi-market tracking and high-frequency strategy
   execution, covering a wide range of trading instruments, making it an ideal choice for professional trading needs.

### Why NexusTrader Is More Efficient?

  - **Enhanced Event Loop Performance**: NexusTrader leverages [uvloop](https://github.com/MagicStack/uvloop), a high-performance event loop, delivering speeds up to 2-4 times faster than Python's default asyncio loop.

  - **High-Performance WebSocket Framework**: Built with [picows](https://github.com/tarasko/picows), a Cython-based WebSocket library that matches the speed of C++'s Boost.Beast, significantly outperforming Python alternatives like websockets and aiohttp.

  - **Optimized Data Serialization**: Utilizing `msgspec` for serialization and deserialization, NexusTrader achieves unmatched efficiency, surpassing tools like `orjson`, `ujson`, and `json`. All data classes are implemented with `msgspec.Struct` for maximum performance.

  - **Scalable Order Management**: Orders are handled efficiently using `asyncio.Queue`, ensuring seamless processing even at high volumes.

  - **Rust-Powered Core Components**: Core modules such as the MessageBus and Clock are implemented in Rust, combining Rust's speed and reliability with Python's flexibility through the [nautilius](https://github.com/nautilius/nautilius) framework.

### Comparison with Other Frameworks

| Framework                                                    | Websocket Package                                            | Data Serialization                                 | Strategy Support | Advantages                                         | Disadvantages                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------ | -------------------------------------------------- | ---------------- | -------------------------------------------------- | ------------------------------------------------- |
| **NexusTrader**                                              | [picows](https://picows.readthedocs.io/en/stable/introduction.html#installation) | [msgspec](https://jcristharif.com/msgspec/)        | ✅                | Professionally optimized for speed and low latency | Requires some familiarity with async workflows    |
| [HummingBot](https://github.com/hummingbot/hummingbot?tab=readme-ov-file) | aiohttp                                                      | [ujson](https://pypi.org/project/ujson/)           | ✅                | Widely adopted with robust community support       | Slower WebSocket handling and limited flexibility |
| [Freqtrade](https://github.com/freqtrade/freqtrade)          | websockets                                                   | [orjson](https://github.com/ijl/orjson)            | ✅                | Flexible strategy support                          | Higher resource consumption                       |
| [crypto-feed](https://github.com/bmoscon/cryptofeed)         | [websockets](https://websockets.readthedocs.io/en/stable/)   | [yapic.json](https://pypi.org/project/yapic.json/) | ❌                | Simple design for feed-only use                    | Lacks trading support and advanced features       |
| [ccxt](https://github.com/bmoscon/cryptofeed)                | [aiohttp](https://docs.aiohttp.org/en/stable/client_reference.html) | json                                               | ❌                | Great REST API support                             | Limited WebSocket performance                     |
| [binance-futures-connector](https://github.com/binance/binance-futures-connector-python) | [websocket-client](https://websocket-client.readthedocs.io/en/latest/examples.html) | json                                               | ❌                | Optimized for Binance-specific integration         | Limited to Binance Futures                        |
| [python-okx](https://github.com/okxapi/python-okx)           | websockets                                                   | json                                               | ❌                | Dedicated to OKX trading                           | Limited to OKX platform                           |
| [unicorn-binance-websocket-api](https://github.com/LUCIT-Systems-and-Development/unicorn-binance-websocket-api) | websockets                                                   | [ujson](https://pypi.org/project/ujson/)           | ❌                | Easy-to-use for Binance users                      | Restricted to Binance and resource-heavy          |

### Architecture (data flow)
The core of Tradebot is the `Connector`, which is responsible for connecting to the exchange and data flow. Through the `PublicConnector`, users can access market data from the exchange, and through the `PrivateConnector`, users can execute trades and receive callbacks for trade data. Orders are submitted through the ``OrderExecutionSystem``, which is responsible for submitting orders to the exchange and obtaining the order ID from the exchange. Order status management is handled by the `OrderManagementSystem`, which is responsible for managing the status of orders and sending them to the `Strategy`.

![Architecture](docs/source/_static/arch.png "architecture")

### Features

- 🌍 Multi-Exchange Integration: Effortlessly connect to top exchanges like Binance, Bybit, and OKX, with an extensible design to support additional platforms.
- ⚡ Asynchronous Operations: Built on asyncio for highly efficient, scalable performance, even during high-frequency trading.
- 📡 Real-Time Data Streaming: Reliable WebSocket support for live market data, order book updates, and trade execution notifications.
- 📊 Advanced Order Management: Execute diverse order types (limit, market, stop) with optimized, professional-grade order handling.
- 📋 Account Monitoring: Real-time tracking of balances, positions, and PnL across multiple exchanges with integrated monitoring tools.
- 🛠️ Modular Architecture: Flexible framework to add exchanges, instruments, or custom strategies with ease.
- 🔄 Strategy Execution & Backtesting: Seamlessly transition from strategy testing to live trading with built-in tools.
- 📈 Scalability: Designed to handle large-scale, multi-market operations for retail and institutional traders alike.
- 💰 Risk & Fund Management: Optimize capital allocation and control risk exposure with integrated management tools.
- 🔔 Instant Notifications: Stay updated with alerts for trades, market changes, and custom conditions.

### Supported Exchanges

| OKX                                                          | **Binance**                                                  | BYBIT                                                        |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| <img src="https://www.okx.com/cdn/assets/imgs/226/EB771F0EE8994DD5.png" width="100"> | <img src="https://cryptologos.cc/logos/binance-coin-bnb-logo.png" width="100"> | <img src="https://raw.githubusercontent.com/bybit-web3/bybit-web3.github.io/main/docs/images/bybit-logo.png" width="100"> |

## Installation

### Prerequisites

- Python 3.11+
- Redis
- Poetry (recommended)
- build-essential

### Install Build Essentials

```bash
sudo apt-get update
sudo apt-get install build-essential
```

### From PyPI

```bash
pip install nexustrader
```

### From Source

```bash
git clone https://github.com/RiverTrading/NexusTrader
cd NexusTrader
poetry install
```

> **Note**
> more details can be found in the [installation guide](https://nexustrader.readthedocs.io/en/latest/installation.html)

### Quick Start

Here's a basic example of how to use nexustrader, demonstrating a simple buy and sell strategy on OKX.

```python
from decimal import Decimal

from nexustrader.constants import settings
from nexustrader.config import Config, PublicConnectorConfig, PrivateConnectorConfig, BasicConfig
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide, OrderType
from nexustrader.exchange.okx import OkxAccountType
from nexustrader.schema import BookL1, Order
from nexustrader.engine import Engine

# Retrieve API credentials from settings
OKX_API_KEY = settings.OKX.DEMO_1.api_key
OKX_SECRET = settings.OKX.DEMO_1.secret
OKX_PASSPHRASE = settings.OKX.DEMO_1.passphrase


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.OKX"])  # Subscribe to the order book for the specified symbol
        self.signal = True  # Initialize signal to control order execution

    def on_failed_order(self, order: Order):
        print(order)  # Log failed orders

    def on_pending_order(self, order: Order):
        print(order)  # Log pending orders

    def on_accepted_order(self, order: Order):
        print(order)  # Log accepted orders

    def on_partially_filled_order(self, order: Order):
        print(order)  # Log partially filled orders

    def on_filled_order(self, order: Order):
        print(order)  # Log filled orders

    def on_bookl1(self, bookl1: BookL1):
        if self.signal:  # Check if the signal is active
            # Create a market buy order
            self.create_order(
                symbol="BTCUSDT-PERP.OKX",
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )
            # Create a market sell order
            self.create_order(
                symbol="BTCUSDT-PERP.OKX",
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                amount=Decimal("0.1"),
            )
            self.signal = False  # Deactivate the signal after placing orders


# Configuration for the trading strategy
config = Config(
    strategy_id="okx_buy_and_sell",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.OKX: BasicConfig(
            api_key=OKX_API_KEY,
            secret=OKX_SECRET,
            passphrase=OKX_PASSPHRASE,
            testnet=True,  # Use testnet for safe trading
        )
    },
    public_conn_config={
        ExchangeType.OKX: [
            PublicConnectorConfig(
                account_type=OkxAccountType.DEMO,  # Specify demo account type
            )
        ]
    },
    private_conn_config={
        ExchangeType.OKX: [
            PrivateConnectorConfig(
                account_type=OkxAccountType.DEMO,  # Specify demo account type
            )
        ]
    }
)

# Initialize the trading engine with the configuration
engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()  # Start the trading engine
    finally:
        engine.dispose()  # Ensure resources are cleaned up

```

This example illustrates how easy it is to switch between different exchanges and strategies by modifying the `config`
class. For instance, to switch to Binance, you can adjust the configuration as follows, and change the symbol to
`BTCUSDT-PERP.BINANCE`.

```python
from nexustrader.exchange.binance import BinanceAccountType

config = Config(
    strategy_id="buy_and_sell_binance",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=True,  # Use testnet for safe trading
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,  # Specify account type for Binance
            )
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,  # Specify account type for Binance
            )
        ]
    }
)
```

## Multi-Mode Support

nexustrader supports multiple modes of operation to cater to different trading strategies and requirements. Each mode
allows for flexibility in how trading logic is executed based on market conditions or specific triggers.

### Event-Driven Mode

In this mode, trading logic is executed in response to real-time market events. The methods `on_bookl1`, `on_trade`, and
`on_kline` are triggered whenever relevant data is updated, allowing for immediate reaction to market changes.

```python
class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.subscribe_bookl1(symbols=["BTCUSDT-PERP.BINANCE"])

    def on_bookl1(self, bookl1: BookL1):
        # implement the trading logic Here
        pass
```

### Timer Mode

This mode allows you to schedule trading logic to run at specific intervals. You can use the `schedule` method to define
when your trading algorithm should execute, making it suitable for strategies that require periodic checks or actions.

```python
class Demo2(Strategy):
    def __init__(self):
        super().__init__()
        self.schedule(self.algo, trigger="interval", seconds=1)

    def algo(self):
        # run every 1 second
        # implement the trading logic Here
        pass
```

### Custom Signal Mode

In this mode, trading logic is executed based on custom signals. You can define your own signals and use the
`on_custom_signal` method to trigger trading actions when these signals are received. This is particularly useful for
integrating with external systems or custom event sources.

```python
class Demo3(Strategy):
    def __init__(self):
        super().__init__()
        self.signal = True

    def on_custom_signal(self, signal: object):
        # implement the trading logic Here,
        # signal can be any object, it is up to you to define the signal
        pass
```

## Define Your Own Indicator

NexusTrader provides a powerful framework for creating custom indicators with built-in warmup functionality. This allows your indicators to automatically fetch historical data and prepare themselves before live trading begins.

Here's an example of creating a custom Moving Average indicator with automatic warmup:

```python
from collections import deque
from nexustrader.indicator import Indicator
from nexustrader.constants import KlineInterval, DataType
from nexustrader.schema import Kline, BookL1, BookL2, Trade
from nexustrader.strategy import Strategy
from nexustrader.exchange.bybit import BybitAccountType

class MovingAverageIndicator(Indicator):
    def __init__(self, period: int = 20):
        super().__init__(
            params={"period": period},
            name=f"MA_{period}",
            warmup_period=period * 2,  # Define warmup period
            warmup_interval=KlineInterval.MINUTE_1,  # Define warmup interval
        )
        self.period = period
        self.prices = deque(maxlen=period)
        self.current_ma = None

    def handle_kline(self, kline: Kline):
        if not kline.confirm:  # Only process confirmed klines
            return

        self.prices.append(kline.close)

        # Calculate moving average if we have enough data
        if len(self.prices) >= self.period:
            self.current_ma = sum(self.prices) / len(self.prices)

    def handle_bookl1(self, bookl1: BookL1):
        pass  # Implement if needed

    def handle_bookl2(self, bookl2: BookL2):
        pass  # Implement if needed

    def handle_trade(self, trade: Trade):
        pass  # Implement if needed

    @property
    def value(self):
        return self.current_ma

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.symbol = "UNIUSDT-PERP.BYBIT"
        self.ma_20 = MovingAverageIndicator(period=20)
        self.ma_50 = MovingAverageIndicator(period=50)

    def on_start(self):
        # Subscribe to kline data
        self.subscribe_kline(
            symbols=self.symbol,
            interval=KlineInterval.MINUTE_1,
        )

        # Register indicators with automatic warmup
        self.register_indicator(
            symbols=self.symbol,
            indicator=self.ma_20,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

        self.register_indicator(
            symbols=self.symbol,
            indicator=self.ma_50,
            data_type=DataType.KLINE,
            account_type=BybitAccountType.LINEAR,
        )

    def on_kline(self, kline: Kline):
        # Wait for indicators to warm up
        if not self.ma_20.is_warmed_up or not self.ma_50.is_warmed_up:
            self.log.info("Indicators still warming up...")
            return

        if not kline.confirm:
            return

        if self.ma_20.value and self.ma_50.value:
            self.log.info(
                f"MA20: {self.ma_20.value:.4f}, MA50: {self.ma_50.value:.4f}, "
                f"Current Price: {kline.close:.4f}"
            )

            # Simple golden cross strategy
            if self.ma_20.value > self.ma_50.value:
                self.log.info("Golden Cross - Bullish signal!")
            elif self.ma_20.value < self.ma_50.value:
                self.log.info("Death Cross - Bearish signal!")
```

#### Key Features of Custom Indicators:

1. **Automatic Warmup**: Set `warmup_period` and `warmup_interval` to automatically fetch historical data
2. **Data Handlers**: Implement `handle_kline`, `handle_bookl1`, `handle_bookl2`, and `handle_trade` as needed
3. **Value Property**: Expose your indicator's current value through the `value` property
4. **Warmup Status**: Check `is_warmed_up` property to ensure indicator is ready before using
5. **Flexible Parameters**: Pass custom parameters through the `params` dictionary

This approach ensures your indicators have sufficient historical data before making trading decisions, improving the reliability and accuracy of your trading strategies.

## Contributing

Thank you for considering contributing to nexustrader! We greatly appreciate any effort to help improve the project. If
you have an idea for an enhancement or a bug fix, the first step is to open
an [issue](https://github.com/Quantweb3-ai/tradebot-pro/issues) on GitHub. This allows us to discuss your proposal and
ensure it aligns with the project's goals, while also helping to avoid duplicate efforts.

When you're ready to start working on your contribution, please review the guidelines in
the [CONTRIBUTING.md](./CONTRIBUTING.md) file. Depending on the nature of your contribution, you may also need to sign a
Contributor License Agreement (CLA) to ensure it can be included in the project.

> **Note**
> Pull requests should be directed to the `main` branch (the default branch), where new features and improvements are
> integrated before release.

Thank you again for your interest in nexustrader! We look forward to reviewing your contributions and collaborating with
you to make the project even better.

## VIP Privileges

Trading on our platform is free. Become a VIP customer to enjoy exclusive technical support privileges for $499 per month ([Subscription Here](https://quantweb3.ai/subscribe/ ))—or get VIP status at no cost by opening an account through our partnership links.

Our partners include global leading trading platforms like Bybit, OKX, ZFX, Bison and others. By opening an account through our referral links, you'll enjoy these benefits:

Instant Account Benefits

1. Trading Fee Discounts: Exclusive discounts to lower your trading costs.
2. VIP Service Support: Contact us after opening your account to become our VIP customer. Enjoy exclusive events and benefits for the ultimate VIP experience.

Act now and join our VIP program!

> Click the links below to register

- [Bybit](https://partner.bybit.com/b/90899)
- [OKX](http://www.okx.com/join/80353297)
- [ZFX](https://zfx.link/46dFByp)
- [Bison](https://m.bison.com/#/register?invitationCode=1002)

## Social

Connect with us on your favorite platforms:

[![X (Twitter)](https://img.shields.io/badge/X_(Twitter)-000000?logo=x&logoColor=white)](https://x.com/quantweb3_ai) Stay updated with our latest news, features, and announcements.

[![Discord](https://img.shields.io/badge/Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/BR8VGRrXFr) Join our community to discuss ideas, get support, and connect with other users.

[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/+6e2MtXxoibM2Yzlk) Receive instant updates and engage in real-time discussions.

## See Also

We recommend exploring related tools and projects that can enhance your trading workflows:

- **[Nexus](https://github.com/Quantweb3-ai/nexus):** A robust exchange interface optimization solution that integrates
  seamlessly with trading bots like nexustrader, enabling faster and more reliable trading execution.

## License

Nexustrader is available on GitHub under the MIT License. Contributions to the project are welcome and require the
completion of a Contributor License Agreement (CLA). Please review the contribution guidelines and submit a pull
request. See the [LICENSE](./LICENSE) file for details.

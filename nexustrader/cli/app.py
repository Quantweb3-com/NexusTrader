from typing import Dict, Any
import msgspec
import redis
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Select
from textual.containers import Container

from nexustrader.cli.widgets.dashboard import DashboardWidget
from nexustrader.cli.widgets.positions import PositionsWidget
from nexustrader.cli.widgets.balances import BalancesWidget
from nexustrader.core.entity import get_redis_client_if_available


class NexusTraderMonitor(App):
    """NexusTrader CLI monitoring application"""

    def __init__(self):
        super().__init__()
        self.current_strategy = None
        self.strategies = {}
        self._redis_client = None
        self._init_redis()

    CSS = """
    Screen {
        background: $surface;
        layout: vertical;
    }
    
    .widget {
        border: solid $primary;
        height: auto;
        margin: 1;
    }
    
    .strategy-selector {
        height: 4;
        margin: 1 2;
        dock: top;
    }
    
    Select {
        width: 100%;
        height: 100%;
    }
    
    TabbedContent {
        height: 1fr;
        margin-top: 1;
    }
    
    TabPane {
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="strategy-selector"):
            yield Select(
                [], prompt="Select a strategy to monitor", id="strategy-select"
            )
        with TabbedContent():
            with TabPane("📊 Dashboard"):
                yield DashboardWidget()
            with TabPane("📍 Positions"):
                yield PositionsWidget()
            with TabPane("💰 Balances"):
                yield BalancesWidget()
        yield Footer()

    @on(Select.Changed)
    def select_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self.current_strategy = str(event.value)
            self.title = f"NexusTrader Monitor - {self.current_strategy}"

    def on_mount(self):
        self.title = "NexusTrader Monitor"
        self.set_interval(1.0, self.refresh_strategies)
        self.set_interval(1.0, self.refresh_data)

    def refresh_strategies(self) -> None:
        """Refresh the list of running strategies from Redis"""
        if not self._redis_client:
            return

        try:
            # Get all running strategies from Redis hash
            running_strategies = self._redis_client.hgetall(
                "nexustrader:running_strategies"
            )

            strategies = {}
            for strategy_key, strategy_data in running_strategies.items():
                if isinstance(strategy_key, bytes):
                    strategy_key = strategy_key.decode("utf-8")
                if isinstance(strategy_data, bytes):
                    strategy_data = strategy_data.decode("utf-8")

                try:
                    strategy_info = msgspec.json.decode(strategy_data)
                    full_id = strategy_info.get("full_id", strategy_key)
                    pid = strategy_info.get("pid", "unknown")
                    strategies[f"{full_id}:{pid}"] = strategy_info
                except msgspec.DecodeError:
                    continue

            self.strategies = strategies
            self._update_strategy_select()

            # Auto-select first strategy if none selected
            if not self.current_strategy and self.strategies:
                first_strategy_id = next(iter(self.strategies.keys()))
                self.current_strategy = first_strategy_id
                self.title = f"NexusTrader Monitor - {self.current_strategy}"
        except Exception:
            # Redis might not be available yet
            pass

    def refresh_data(self) -> None:
        """Refresh data for the selected strategy"""
        if not self.current_strategy:
            return

        try:
            strategy_data = self._load_strategy_data(self.current_strategy)
            self._update_widgets(strategy_data)
        except Exception:
            # Data might not be available yet
            pass

    def _update_strategy_select(self) -> None:
        """Update the strategy selector options"""
        select = self.query_one("#strategy-select", Select)
        options = [(strategy_id, strategy_id) for strategy_id in self.strategies.keys()]
        current_value = select.value
        select.set_options(options)
        # Restore selection if it still exists
        if current_value and current_value in self.strategies:
            select.value = current_value

    def _init_redis(self):
        """Initialize Redis connection"""
        self._redis_client = get_redis_client_if_available()

    def _load_strategy_data(self, strategy_id: str) -> Dict[str, Any]:
        """Load strategy data from Redis"""
        if not self._redis_client:
            return {}

        data = {}

        # Load each data type from Redis
        for data_type in ["positions", "balances", "metrics"]:
            try:
                key = f"strategy:{strategy_id}:{data_type}"
                redis_data = self._redis_client.get(key)
                if redis_data:
                    content = msgspec.json.decode(redis_data)
                    data[data_type] = content
            except (redis.RedisError, redis.ConnectionError, msgspec.DecodeError):
                # Skip failed data loads
                pass

        return data

    def _update_widgets(self, data: Dict[str, Any]) -> None:
        """Update all widgets with new data"""

        # Update dashboard
        dashboard = self.query_one(DashboardWidget)
        dashboard.update_data(data)

        # Update positions
        positions = self.query_one(PositionsWidget)
        positions.update_data(data.get("positions", {}))
        # Update balances
        balances = self.query_one(BalancesWidget)
        balances.update_data(data.get("balances", {}))


def run_monitor():
    """Entry point for the CLI monitor"""
    app = NexusTraderMonitor()
    app.run()


if __name__ == "__main__":
    run_monitor()

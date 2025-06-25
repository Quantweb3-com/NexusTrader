from typing import Dict, Any
from textual.widgets import Static, DataTable
from textual.app import App, ComposeResult


class DashboardWidget(Static):
    """Main dashboard widget displaying various metrics in a table"""

    def __init__(self):
        super().__init__()
        self.add_class("widget")

    def compose(self):
        """Compose the dashboard layout"""
        table = DataTable(classes="dashboard-table")
        table.add_columns("Metric", "Value", "Status")
        yield table

    def update_data(self, data: Dict[str, Any]):
        """Update dashboard with new data"""
        table = self.query_one(DataTable)
        table.clear()

        # Extract metrics from data
        metrics = data.get("metrics", {}).get("metrics", {})

        # Order metrics
        table.add_row("Total Orders", str(metrics.get("total_orders", 0)), "--")
        table.add_row("Open Orders", str(metrics.get("open_orders", 0)), "--")

        # Position metrics
        table.add_row("Total Positions", str(metrics.get("total_positions", 0)), "--")
        table.add_row("Active Positions", str(metrics.get("active_positions", 0)), "--")

        # PnL metrics with status
        unrealized_pnl = metrics.get("total_unrealized_pnl", 0.0)
        unrealized_status = (
            "📈" if unrealized_pnl > 0 else "📉" if unrealized_pnl < 0 else "➖"
        )
        table.add_row("Unrealized PnL", f"${unrealized_pnl:.2f}", unrealized_status)

        realized_pnl = metrics.get("total_realized_pnl", 0.0)
        realized_status = (
            "📈" if realized_pnl > 0 else "📉" if realized_pnl < 0 else "➖"
        )
        table.add_row("Realized PnL", f"${realized_pnl:.2f}", realized_status)


class DashboardTestApp(App):
    """Test application for the dashboard widget"""

    CSS = """
    Screen {
        background: $surface;
    }
    
    .widget {
        border: solid $primary;
        height: auto;
        margin: 1 2;
    }
    
    .dashboard-table {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Header, Footer

        yield Header()
        yield DashboardWidget()
        yield Footer()

    def on_mount(self):
        self.set_interval(1, self.load_sample_data)

    def load_sample_data(self):
        """Load sample dashboard data into the widget"""
        from random import random

        # Simulate dynamic test data
        sample_data = {
            "metrics": {
                "metrics": {
                    "total_orders": int(156 * (0.8 + 0.4 * random())),
                    "open_orders": int(3 * (0.5 + random())),
                    "total_positions": int(45 * (0.8 + 0.4 * random())),
                    "active_positions": int(2 * (0.5 + random())),
                    "total_unrealized_pnl": 1234.56
                    * (0.5 + random())
                    * (1 if random() > 0.3 else -1),
                    "total_realized_pnl": -234.78
                    * (0.5 + random())
                    * (1 if random() > 0.4 else -1),
                }
            }
        }

        dashboard = self.query_one(DashboardWidget)
        dashboard.update_data(sample_data)


if __name__ == "__main__":
    app = DashboardTestApp()
    app.run()

from typing import Dict, Any
from textual.widgets import Static, DataTable
from textual.app import App, ComposeResult


class BalancesWidget(Static):
    """Widget for displaying account balances"""

    def __init__(self):
        super().__init__()
        self.add_class("widget")

    def compose(self):
        table = DataTable(classes="balances-table")
        table.add_columns("Account", "Asset", "Free", "Total")
        yield table

    def update_data(self, data: Dict[str, Any]):
        """Update balances table with new data"""
        table = self.query_one(DataTable)
        table.clear()
        balances = data.get("balances", [])

        for balance in balances:
            # Format values
            account_type = balance.get("account_type", "N/A")
            asset = balance.get("asset", "N/A")
            free = balance.get("free", 0.0)
            total = balance.get("total", 0.0)

            table.add_row(account_type, asset, f"{free:.8f}", f"{total:.8f}")


class BalancesTestApp(App):
    """Test application for BalancesWidget"""

    CSS = """
    Screen {
        background: $surface;
    }
    
    .widget {
        border: solid $primary;
        height: auto;
        margin: 1 2;
    }
    
    .balances-table {
        height: auto;
    }
    
    Button {
        margin: 1 2;
        width: 20;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Header, Footer

        yield Header()
        yield BalancesWidget()
        yield Footer()

    def on_mount(self):
        self.set_interval(1, self.load_sample_data)

    def load_sample_data(self):
        from random import random

        """Load sample balance data into the widget"""
        sample_data = {
            "balances": [
                {
                    "account_type": "demo",
                    "asset": "USDT",
                    "free": 104351.44449810461,
                    "locked": None,
                    "total": 104351.44449810461,
                },
                {
                    "account_type": "demo",
                    "asset": "BTC",
                    "free": 5.29e-09,
                    "locked": None,
                    "total": 5.29e-09,
                },
                {
                    "account_type": "demo",
                    "asset": "SOL",
                    "free": 5.266e-07,
                    "locked": None,
                    "total": 5.266e-07,
                },
            ]
        }

        balance_widget = self.query_one(BalancesWidget)
        balance_widget.update_data(sample_data)


if __name__ == "__main__":
    app = BalancesTestApp()
    app.run()

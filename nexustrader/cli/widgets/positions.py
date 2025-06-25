from typing import Dict, Any
from textual.widgets import Static, DataTable
from textual.app import App, ComposeResult


class PositionsWidget(Static):
    """Widget for displaying positions"""

    def __init__(self):
        super().__init__()
        self.add_class("widget")

    def compose(self):
        table = DataTable(classes="positions-table")
        table.add_columns("Symbol", "Side", "Amount", "Entry Price")
        yield table

    def update_data(self, data: Dict[str, Any]):
        """Update positions table with new data"""
        table = self.query_one(DataTable)
        table.clear()

        positions = data.get("positions", [])

        for position in positions:
            symbol = position.get("symbol", "N/A")
            side = position.get("side", "N/A")
            amount = (
                f"{position.get('amount', 0):.6f}" if position.get("amount") else "N/A"
            )
            entry_price = (
                f"{position.get('entry_price', 0):.6f}"
                if position.get("entry_price")
                else "N/A"
            )

            table.add_row(symbol, side, amount, entry_price)


class PositionsTestApp(App):
    """Test application for PositionsWidget"""

    CSS = """
    Screen {
        background: $surface;
    }
    
    .widget {
        border: solid $primary;
        height: auto;
        margin: 1 2;
    }
    
    .positions-table {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Header, Footer

        yield Header()
        yield PositionsWidget()
        yield Footer()

    def on_mount(self):
        self.set_interval(2, self.load_sample_data)

    def load_sample_data(self):
        """Load sample positions data into the widget"""
        from random import random, choice

        sample_data = {
            "positions": [
                {
                    "symbol": "BTCUSDT-PERP",
                    "side": choice(["LONG", "SHORT"]),
                    "amount": 1.5 + random() * 3,
                    "entry_price": 95000.0 + random() * 1000,
                    "mark_price": 95500.0 + random() * 1000,
                    "unrealized_pnl": (random() - 0.5) * 2000,
                    "roe_percent": (random() - 0.5) * 20,
                },
                {
                    "symbol": "ETHUSDT-PERP",
                    "side": choice(["LONG", "SHORT"]),
                    "amount": 10.0 + random() * 15,
                    "entry_price": 3500.0 + random() * 200,
                    "mark_price": 3520.0 + random() * 200,
                    "unrealized_pnl": (random() - 0.5) * 1500,
                    "roe_percent": (random() - 0.5) * 15,
                },
                {
                    "symbol": "ADAUSDT-PERP",
                    "side": choice(["LONG", "SHORT"]),
                    "amount": 5000.0 + random() * 3000,
                    "entry_price": 1.2 + random() * 0.3,
                    "mark_price": 1.25 + random() * 0.3,
                    "unrealized_pnl": (random() - 0.5) * 500,
                    "roe_percent": (random() - 0.5) * 25,
                },
            ]
        }

        positions_widget = self.query_one(PositionsWidget)
        positions_widget.update_data(sample_data)


if __name__ == "__main__":
    app = PositionsTestApp()
    app.run()

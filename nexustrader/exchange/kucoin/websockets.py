# https://www.kucoin.com/docs-new/websocket-api/base-info/introduction-uta

# PING
# {
#   "id": "1545910590801",
#   "type": "ping"
# }

# You can use timestamp_ms as the id for PING messages
# define the user_api_pong_callback function to handle PONG responses

# PONG
# {
#   "id": "1545910590801",
#   "type": "pong",
#   "timestamp": 1764215232226553
# }

# class KuCoinWebsocketPongMsg(Struct):
#     type: str | None = None

#     @property
#     def is_pong(self) -> bool:
#         return self.type == "pong"

# You need to define two classes
# KucoinWSClient(WSClient)

# Public Channels
# ------------------------------------------
# Ticker SPOT | Futures https://www.kucoin.com/docs-new/3470222w0
# def subscribe_ticker(self, symbols: List[str], trade_type: Literal["SPOT", "FUTURES"] = "SPOT") -> None:

# Trade
# OrderBook
# Kline

# Private Channels
# ------------------------------------------
# Order 
# Position
# Balance

# KucoinWSApiClient(WSClient)
# Add Order
# Cancel Order
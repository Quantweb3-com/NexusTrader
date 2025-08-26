import msgspec
from decimal import Decimal
from nexustrader.schema import BaseMarket, Balance
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidKlineInterval,
    HyperLiquidOrderStatusType,
    HyperLiquidOrderSide,
    HyperLiquidFillDirection,
)


class HyperLiquidMarketInfo(msgspec.Struct, kw_only=True):
    """Market information from HyperLiquid exchange
    {



            "circulatingSupply": "8888888887.9898376465",
            "coin": "@153",
            "totalSupply": "8888888887.9898376465",
            "tokens": [
                241,
                0
            ],

            "index": 153,
            "isCanonical": false
        },

     "info": {
            "szDecimals": 5,

            "maxLeverage": 40,
            "funding": "0.0000069988",
            "openInterest": "9584.3844",


            "premium": "-0.0004322507",
            "oraclePx": "83285.0",

            "impactPxs": [
                "83238.0",
                "83249.0"
            ],
            "baseId": 0
        },


    """

    # Common fields
    name: str
    prevDayPx: str
    dayNtlVlm: str
    markPx: str
    midPx: str | None = None
    dayBaseVlm: str

    # Spot specific fields
    circulatingSupply: str | None = None
    coin: str | None = None
    totalSupply: str | None = None
    tokens: list[str] | None = None
    index: str | None = None
    isCanonical: bool | None = None

    # Perpetual specific fields
    szDecimals: str | None = None
    maxLeverage: str | None = None
    funding: str | None = None
    openInterest: str | None = None
    premium: str | None = None
    oraclePx: str | None = None
    impactPxs: list[str] | None = None
    baseId: int | None = None


class HyperLiquidMarket(BaseMarket):
    info: HyperLiquidMarketInfo
    baseName: str


class HyperLiquidOrderRestingStatus(msgspec.Struct):
    oid: int  # Order ID


class HyperLiquidOrderFilledStatus(msgspec.Struct):
    oid: int  # Order ID
    avgPx: str
    totalSz: str


class HyperLiquidOrderStatus(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Order status information"""

    error: str | None = None  # Error message if any
    resting: HyperLiquidOrderRestingStatus | None = (
        None  # Contains oid when order is resting
    )
    filled: HyperLiquidOrderFilledStatus | None = (
        None  # Contains oid when order is filled
    )


class HyperLiquidOrderData(msgspec.Struct):
    """Order response data"""

    statuses: list[HyperLiquidOrderStatus]


class HyperLiquidOrderResponseData(msgspec.Struct):
    """Order response wrapper"""

    type: str
    data: HyperLiquidOrderData


class HyperLiquidOrderResponse(msgspec.Struct):
    """Response from order placement"""

    status: str
    response: HyperLiquidOrderResponseData


class HyperLiquidOrderStatusCancelStatus(msgspec.Struct):
    error: str


class HyperLiquidOrderDataStatuses(msgspec.Struct):
    statuses: list[str | HyperLiquidOrderStatusCancelStatus]


class HyperLiquidCancelResponseData(msgspec.Struct):
    type: str
    data: HyperLiquidOrderDataStatuses


class HyperLiquidCancelResponse(msgspec.Struct):
    """Response from order cancellation"""

    status: str
    response: HyperLiquidCancelResponseData


class HyperLiquidCumFunding(msgspec.Struct):
    """Cumulative funding information"""

    allTime: str
    sinceChange: str
    sinceOpen: str


class HyperLiquidLeverage(msgspec.Struct):
    """Leverage information"""

    type: str
    value: int
    rawUsd: str | None = None


class HyperLiquidActiveAssetData(msgspec.Struct):
    """Active asset data for a specific coin"""

    user: str  # User address
    coin: str  # Coin/token symbol
    leverage: HyperLiquidLeverage  # Leverage information
    maxTradeSzs: list[str]  # Maximum trade sizes
    availableToTrade: list[str]  # Available amounts to trade
    markPx: str  # Mark price


class HyperLiquidPosition(msgspec.Struct, kw_only=True):
    """Individual position data"""

    coin: str
    cumFunding: HyperLiquidCumFunding
    entryPx: str
    leverage: HyperLiquidLeverage
    liquidationPx: str | None = None
    marginUsed: str
    maxLeverage: int
    positionValue: str
    returnOnEquity: str
    szi: str
    unrealizedPnl: str


class HyperLiquidAssetPosition(msgspec.Struct):
    """Asset position wrapper"""

    position: HyperLiquidPosition
    type: str


class HyperLiquidMarginSummary(msgspec.Struct):
    """Margin summary information"""

    accountValue: str
    totalMarginUsed: str
    totalNtlPos: str
    totalRawUsd: str


class HyperLiquidUserPerpsSummary(msgspec.Struct):
    """User perpetuals summary information"""

    assetPositions: list[HyperLiquidAssetPosition]
    crossMaintenanceMarginUsed: str
    crossMarginSummary: HyperLiquidMarginSummary
    marginSummary: HyperLiquidMarginSummary
    time: int
    withdrawable: str


class HyperLiquidMeta(msgspec.Struct):
    """Market metadata"""

    universe: list[dict]
    amms: list[dict]


class HyperLiquidKline(msgspec.Struct):
    """
    Kline/candlestick data from HyperLiquid API
    [
        {
            "T": 1681924499999,
            "c": "29258.0",
            "h": "29309.0",
            "i": "15m",
            "l": "29250.0",
            "n": 189,
            "o": "29295.0",
            "s": "BTC",
            "t": 1681923600000,
            "v": "0.98639"
        }
    ]
    """

    T: int  # Close time
    c: str  # Close price
    h: str  # High price
    i: str  # Interval
    l: str  # Low price # noqa: E741
    n: int  # Number of trades
    o: str  # Open price
    s: str  # Symbol
    t: int  # Open time
    v: str  # Volume


class HyperLiquidTrade(msgspec.Struct):
    """Trade data"""

    timestamp: int
    price: str
    size: str
    side: str
    hash: str


class HyperLiquidOrderBook(msgspec.Struct):
    """Order book data"""

    levels: list[list[str]]  # [price, size] pairs
    timestamp: int


class HyperLiquidTicker(msgspec.Struct):
    """Ticker data"""

    symbol: str
    lastPrice: str
    volume24h: str
    priceChange24h: str
    high24h: str
    low24h: str


class HyperLiquidUserOrder(msgspec.Struct):
    """
    User order data from HyperLiquid API
    [
        {
            "coin": "BTC",
            "limitPx": "29792.0",
            "oid": 91490942,
            "side": "A",
            "sz": "0.0",
            "timestamp": 1681247412573
        }
    ]
    """

    coin: str  # Trading pair/symbol
    limitPx: str  # Limit price
    oid: int  # Order ID
    side: str  # Side: "A" for ask/sell, "B" for bid/buy
    sz: str  # Size/quantity
    timestamp: int  # Order timestamp in milliseconds


class HyperLiquidSpotToken(msgspec.Struct):
    """
    Spot token information from HyperLiquid API
    {
        "name": "USDC",
        "szDecimals": 8,
        "weiDecimals": 8,
        "index": 0,
        "tokenId": "0x6d1e7cde53ba9467b783cb7c530ce054",
        "isCanonical": true,
        "evmContract": null,
        "fullName": null
    }
    """

    name: str  # Token name/symbol
    szDecimals: int  # Size decimals
    weiDecimals: int  # Wei decimals
    index: int  # Token index
    tokenId: str  # Token ID
    isCanonical: bool  # Whether this is a canonical token
    evmContract: dict | None = None  # EVM contract address
    fullName: str | None = None  # Full token name


class HyperLiquidSpotUniverse(msgspec.Struct):
    """
    Spot universe information from HyperLiquid API
    {
        "name": "PURR/USDC",
        "tokens": [1, 0],
        "index": 0,
        "isCanonical": true
    }
    """

    name: str  # Trading pair name
    tokens: list[int]  # List of token indices
    index: int  # Universe index
    isCanonical: bool  # Whether this is a canonical pair


class HyperLiquidSpotMeta(msgspec.Struct):
    """
    Spot market metadata from HyperLiquid API
    {
        "tokens": [...],
        "universe": [...]
    }
    """

    tokens: list[HyperLiquidSpotToken]  # List of available tokens
    universe: list[HyperLiquidSpotUniverse]  # List of trading pairs


class HyperLiquidSpotBalance(msgspec.Struct):
    """
    Spot balance information from HyperLiquid API
    {
        "coin": "USDC",
        "token": 0,
        "hold": "0.0",
        "total": "14.625485",
        "entryNtl": "0.0"
    }
    """

    coin: str  # Coin/token symbol
    token: int  # Token index
    hold: str  # Amount on hold
    total: str  # Total balance
    entryNtl: str  # Entry notional value

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.coin,
            locked=Decimal(self.hold),
            free=Decimal(self.total) - Decimal(self.hold),
        )


class HyperLiquidUserSpotSummary(msgspec.Struct):
    """
    User spot summary from HyperLiquid API
    {
        "balances": [
            {
                "coin": "USDC",
                "token": 0,
                "hold": "0.0",
                "total": "14.625485",
                "entryNtl": "0.0"
            }
        ]
    }
    """

    balances: list[HyperLiquidSpotBalance]  # List of spot balances

    def parse_to_balances(self) -> list[Balance]:
        return [balance.parse_to_balance() for balance in self.balances]


class HyperLiquidWsMessageGeneral(msgspec.Struct):
    channel: str  # Channel name


class HyperLiquidWsBboLevelMsgData(msgspec.Struct):
    px: str  # Price
    sz: str  # Size
    n: int  # Number of orders


class HyperLiquidWsBboMsgData(msgspec.Struct):
    coin: str
    time: int
    bbo: list[HyperLiquidWsBboLevelMsgData]  # Best bid/ask levels


class HyperLiquidWsBboMsg(msgspec.Struct):
    """
    {
        "channel": "bbo",
        "data": {
            "coin": "PURR/USDC",
            "time": 1753455504649,
            "bbo": [
                {"px": "0.18134", "sz": "250.0", "n": 1},
                {"px": "0.18168", "sz": "750.0", "n": 1},
            ],
        },
    }
    """

    data: HyperLiquidWsBboMsgData


class HyperLiquidWsTradeDataMsg(msgspec.Struct):
    coin: str
    px: str  # Price
    sz: str  # Size
    time: int


class HyperLiquidWsTradeMsg(msgspec.Struct):
    data: list[HyperLiquidWsTradeDataMsg]


class HyperLiquidWsCandleDataMsg(msgspec.Struct):
    t: int  # Open time
    T: int  # Close time
    s: str  # Symbol
    i: HyperLiquidKlineInterval  # Interval
    o: str  # Open price
    c: str  # Close price
    h: str  # High price
    l: str  # Low price # noqa: E741
    v: str  # Volume
    n: int  # Number of trades


class HyperLiquidWsCandleMsg(msgspec.Struct):
    data: HyperLiquidWsCandleDataMsg


class HyperLiquidWsBasicOrder(msgspec.Struct, kw_only=True, omit_defaults=True):
    coin: str
    side: HyperLiquidOrderSide  # "A" for ask/sell, "B" for bid/buy
    limitPx: str
    sz: str
    oid: int
    timestamp: int
    origSz: str
    cloid: str | None = None  # Client order ID


class HyperLiquidWsOrderUpdatesMsgData(msgspec.Struct):
    order: HyperLiquidWsBasicOrder
    status: HyperLiquidOrderStatusType  # Order status
    statusTimestamp: int  # Timestamp of the status update


class HyperLiquidWsOrderUpdatesMsg(msgspec.Struct):
    data: list[HyperLiquidWsOrderUpdatesMsgData]


class HyperLiquidWsFills(msgspec.Struct):
    coin: str
    px: str
    sz: str
    side: HyperLiquidOrderSide  # "A" for ask/sell, "B" for bid/buy
    time: int
    startPosition: str
    dir: HyperLiquidFillDirection  # Direction of the fill
    closedPnl: str
    oid: int
    crossed: bool  # whether order crossed the spread (was taker)
    fee: str
    tid: int  # Trade ID
    feeToken: str


class HyperLiquidWsUserFillsMsgData(msgspec.Struct):
    fills: list[HyperLiquidWsFills] | None = None  # List of fills, if any


class HyperLiquidWsUserFillsMsg(msgspec.Struct):
    data: HyperLiquidWsUserFillsMsgData


class HyperLiquidWsApiOrderFilledStatus(msgspec.Struct):
    """WebSocket API order filled status"""
    totalSz: str
    avgPx: str
    oid: int


class HyperLiquidWsApiOrderStatus(msgspec.Struct, kw_only=True, omit_defaults=True):
    """WebSocket API order status"""
    error: str | None = None
    filled: HyperLiquidWsApiOrderFilledStatus | None = None
    resting: HyperLiquidOrderRestingStatus | None = None


class HyperLiquidWsApiOrderData(msgspec.Struct):
    """WebSocket API order response data"""
    statuses: list[HyperLiquidWsApiOrderStatus | str]


class HyperLiquidWsApiResponseData(msgspec.Struct):
    """WebSocket API response data wrapper"""
    type: str  # "order" or "cancel"
    data: HyperLiquidWsApiOrderData


class HyperLiquidWsApiPayload(msgspec.Struct):
    """WebSocket API payload"""
    status: str
    response: HyperLiquidWsApiResponseData


class HyperLiquidWsApiResponse(msgspec.Struct):
    """WebSocket API response"""
    type: str
    payload: HyperLiquidWsApiPayload


class HyperLiquidWsApiMessageData(msgspec.Struct):
    """WebSocket API message data"""
    id: int
    response: HyperLiquidWsApiResponse


class HyperLiquidWsApiGeneralMsg(msgspec.Struct):
    """General WebSocket API message structure"""
    channel: str
    data: HyperLiquidWsApiMessageData | None = None

    @property
    def is_pong(self) -> bool:
        return self.channel == "pong"

    @property
    def is_order_response(self) -> bool:
        return self.channel == "post" and self.data is not None

    @property 
    def is_ping(self) -> bool:
        return self.channel == "ping"

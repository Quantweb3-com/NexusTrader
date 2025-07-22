import msgspec
from nexustrader.schema import BaseMarket


class HyperLiquidMarketInfo(msgspec.Struct):
    """Market information from HyperLiquid exchange"""
    # Core market fields
    name: str
    baseId: int | str | None = None
    coin: str | None = None
    index: int | str | None = None
    isCanonical: bool | None = None

    # Price and volume data
    prevDayPx: str | None = None
    dayNtlVlm: str | None = None
    markPx: str | None = None
    midPx: str | None = None
    dayBaseVlm: str | None = None

    # Perpetual/contract specific fields
    szDecimals: int | str | None = None
    maxLeverage: int | str | None = None
    funding: str | None = None
    openInterest: str | None = None
    premium: str | None = None
    oraclePx: str | None = None
    impactPxs: list[str] | None = None
    marginTableId: str | None = None

    # Spot/Token info (optional, not always present)
    circulatingSupply: str | None = None
    totalSupply: str | None = None
    tokens: list[str] | None = None


class HyperLiquidMarket(BaseMarket):
    info: HyperLiquidMarketInfo


class HyperLiquidOrderStatus(msgspec.Struct):
    """Order status information"""
    resting: dict | None = None  # Contains oid when order is resting


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


class HyperLiquidCancelResponse(msgspec.Struct):
    """Response from order cancellation"""
    status: str
    response: dict


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
    szi: str
    leverage: HyperLiquidLeverage
    entryPx: str
    positionValue: str
    unrealizedPnl: str
    returnOnEquity: str
    liquidationPx: str | None = None
    marginUsed: str
    maxLeverage: int
    cumFunding: HyperLiquidCumFunding


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
    l: str  # Low price
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

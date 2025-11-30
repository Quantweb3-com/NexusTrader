import msgspec
from typing import List
from nexustrader.schema import BaseMarket
from decimal import Decimal
from msgspec import Struct


class KucoinSpotMarketInfo(msgspec.Struct, kw_only=True):
    """
    KuCoin Spot market info structure.

    Example:
    {
        "symbol": "BTC-USDT",
        "name": "BTC-USDT",
        "baseCurrency": "BTC",
        "quoteCurrency": "USDT",
        "feeCurrency": "USDT",
        "market": "USDS",
        "baseMinSize": "0.00001",
        "quoteMinSize": "0.1",
        "baseMaxSize": "10000000000",
        "quoteMaxSize": "99999999",
        "baseIncrement": "0.00000001",
        "quoteIncrement": "0.000001",
        "priceIncrement": "0.1",
        "priceLimitRate": "0.1",
        "minFunds": "0.1",
        "isMarginEnabled": true,
        "enableTrading": true,
        "feeCategory": 1,
        "makerFeeCoefficient": "1.00",
        "takerFeeCoefficient": "1.00"
    }
    """

    symbol: str  # Symbol name
    name: str  # Symbol display name
    baseCurrency: str  # Base currency
    quoteCurrency: str  # Quote currency
    feeCurrency: str  # Fee currency
    market: str  # Market group (USDS, BTC, etc.)
    baseMinSize: str  # Minimum base currency order size
    quoteMinSize: str  # Minimum quote currency order size
    baseMaxSize: str  # Maximum base currency order size
    quoteMaxSize: str  # Maximum quote currency order size
    baseIncrement: str  # Base currency increment
    quoteIncrement: str  # Quote currency increment
    priceIncrement: str  # Price increment (tick size)
    priceLimitRate: str  # Price limit rate
    minFunds: str  # Minimum order funds
    isMarginEnabled: bool  # Whether margin trading is enabled
    enableTrading: bool  # Whether trading is enabled
    feeCategory: int  # Fee category
    makerFeeCoefficient: str  # Maker fee coefficient
    takerFeeCoefficient: str  # Taker fee coefficient
    st: bool | None = None  # Whether it's a special token
    callauctionIsEnabled: bool | None = None  # Call auction enabled
    callauctionPriceFloor: str | None = None  # Call auction price floor
    callauctionPriceCeiling: str | None = None  # Call auction price ceiling
    callauctionFirstStageStartTime: int | None = None  # First stage start time
    callauctionSecondStageStartTime: int | None = None  # Second stage start time
    callauctionThirdStageStartTime: int | None = None  # Third stage start time
    tradingStartTime: int | None = None  # Trading start time


class KucoinFuturesMarketInfo(msgspec.Struct, kw_only=True):
    """
    KuCoin Futures market info structure.

    Example:
    {
        "symbol": "XBTUSDTM",
        "rootSymbol": "USDT",
        "type": "FFWCSX",
        "baseCurrency": "XBT",
        "quoteCurrency": "USDT",
        "settleCurrency": "USDT",
        "maxOrderQty": 1000000,
        "maxPrice": 1000000.0,
        "lotSize": 1,
        "tickSize": 0.1,
        "indexPriceTickSize": 0.01,
        "multiplier": 0.001,
        "initialMargin": 0.008,
        "maintainMargin": 0.004,
        "maxRiskLimit": 100000,
        "minRiskLimit": 100000,
        "riskStep": 50000,
        "makerFeeRate": 2.0E-4,
        "takerFeeRate": 6.0E-4,
        "status": "Open",
        "fundingFeeRate": 3.9E-5,
        "maxLeverage": 125
    }
    """

    symbol: str  # Contract symbol
    rootSymbol: str  # Contract group (root symbol)
    type: str  # Contract type
    baseCurrency: str  # Base currency
    quoteCurrency: str  # Quote currency
    settleCurrency: str  # Settlement currency
    maxOrderQty: int  # Maximum order quantity
    marketMaxOrderQty: int | None = None  # Maximum market order quantity
    maxPrice: float  # Maximum order price
    lotSize: int  # Minimum order size increment
    tickSize: float  # Price tick size
    indexPriceTickSize: float  # Index price tick size
    multiplier: float  # Contract multiplier (contract value)
    initialMargin: float  # Initial margin rate
    maintainMargin: float  # Maintenance margin rate
    maxRiskLimit: int  # Maximum risk limit
    minRiskLimit: int  # Minimum risk limit
    riskStep: int  # Risk limit step
    makerFeeRate: float  # Maker fee rate
    takerFeeRate: float  # Taker fee rate
    takerFixFee: float | None = None  # Taker fixed fee
    makerFixFee: float | None = None  # Maker fixed fee
    settlementFee: float | None = None  # Settlement fee
    isDeleverage: bool | None = None  # Whether auto-deleveraging is enabled
    isQuanto: bool | None = None  # Whether it's a quanto contract
    isInverse: bool | None = None  # Whether it's an inverse contract
    markMethod: str | None = None  # Mark price method
    fairMethod: str | None = None  # Fair price method
    fundingBaseSymbol: str | None = None  # Funding base symbol
    fundingQuoteSymbol: str | None = None  # Funding quote symbol
    fundingRateSymbol: str | None = None  # Funding rate symbol
    indexSymbol: str | None = None  # Index symbol
    settlementSymbol: str | None = None  # Settlement symbol
    status: str  # Contract status (Open, Closed, etc.)
    fundingFeeRate: float | None = None  # Current funding rate
    predictedFundingFeeRate: float | None = None  # Predicted funding rate
    fundingRateGranularity: int | None = None  # Funding interval in milliseconds
    fundingRateCap: float | None = None  # Funding rate cap
    fundingRateFloor: float | None = None  # Funding rate floor
    period: int | None = None  # Settlement period
    openInterest: str | None = None  # Open interest
    turnoverOf24h: float | None = None  # 24h turnover
    volumeOf24h: float | None = None  # 24h volume
    markPrice: float | None = None  # Mark price
    indexPrice: float | None = None  # Index price
    lastTradePrice: float | None = None  # Last trade price
    nextFundingRateTime: int | None = None  # Next funding time (milliseconds left)
    nextFundingRateDateTime: int | None = None  # Next funding datetime (timestamp)
    maxLeverage: int  # Maximum leverage
    sourceExchanges: List[str] | None = None  # Source exchanges for index
    premiumsSymbol1M: str | None = None  # 1-minute premium symbol
    premiumsSymbol8H: str | None = None  # 8-hour premium symbol
    fundingBaseSymbol1M: str | None = None  # 1-minute funding base symbol
    fundingQuoteSymbol1M: str | None = None  # 1-minute funding quote symbol
    lowPrice: float | None = None  # 24h low price
    highPrice: float | None = None  # 24h high price
    priceChgPct: float | None = None  # 24h price change percentage
    priceChg: float | None = None  # 24h price change
    firstOpenDate: int | None = None  # First open date timestamp
    expireDate: int | None = None  # Expiry date timestamp
    settleDate: int | None = None  # Settlement date timestamp
    k: float | None = None  # Risk limit coefficient k
    m: float | None = None  # Risk limit coefficient m
    f: float | None = None  # Risk limit coefficient f
    mmrLimit: float | None = None  # Maintenance margin ratio limit
    mmrLevConstant: float | None = None  # MMR leverage constant
    supportCross: bool | None = None  # Whether cross margin is supported
    buyLimit: float | None = None  # Buy price limit
    sellLimit: float | None = None  # Sell price limit
    adjustK: float | None = None  # Adjusted k
    adjustM: float | None = None  # Adjusted m
    adjustMmrLevConstant: float | None = None  # Adjusted MMR leverage constant
    adjustActiveTime: int | None = None  # Adjustment active time
    crossRiskLimit: float | None = None  # Cross margin risk limit
    marketStage: str | None = None  # Market stage (NORMAL, etc.)
    preMarketToPerpDate: int | None = None  # Pre-market to perpetual date


class KucoinSpotMarket(BaseMarket):
    """
    KuCoin unified market structure that works for both spot and futures.
    Contains the raw exchange info in the 'info' field.
    """

    info: KucoinSpotMarketInfo 

class KucoinFuturesMarket(BaseMarket):
    """
    KuCoin unified market structure that works for both spot and futures.
    Contains the raw exchange info in the 'info' field.
    """

    info: KucoinFuturesMarketInfo


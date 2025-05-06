import msgspec
from nexustrader.schema import BaseMarket


class BitgetMarketInfo(msgspec.Struct, kw_only=True, omit_defaults=True):
    baseCoin: str
    buyLimitPriceRatio: str
    makerFeeRate: str
    minTradeUSDT: str
    offTime: str
    openTime: str
    quoteCoin: str
    sellLimitPriceRatio: str
    symbol: str
    takerFeeRate: str

    areaSymbol: str | None = None
    deliveryPeriod: str | None = None
    deliveryStartTime: str | None = None
    deliveryTime: str | None = None
    feeRateUpRatio: str | None = None
    fundInterval: str | None = None
    launchTime: str | None = None
    limitOpenTime: str | None = None
    maintainTime: str | None = None
    maxLever: str | None = None
    maxPositionNum: str | None = None
    maxProductOrderNum: str | None = None
    maxSymbolOrderNum: str | None = None
    maxTradeAmount: str | None = None
    minLever: str | None = None
    minTradeAmount: str | None = None
    minTradeNum: str | None = None
    openCostUpRatio: str | None = None
    orderQuantity: str | None = None
    posLimit: str | None = None
    priceEndStep: str | None = None
    pricePlace: str | None = None
    pricePrecision: str | None = None
    quantityPrecision: str | None = None
    quotePrecision: str | None = None
    sizeMultiplier: str | None = None
    status: str | None = None
    supportMarginCoins: list[str] | None = None
    symbolStatus: str | None = None
    symbolType: str | None = None
    volumePlace: str | None = None


class BitgetMarket(BaseMarket):
    info: BitgetMarketInfo

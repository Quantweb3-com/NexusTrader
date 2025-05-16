import msgspec
from nexustrader.schema import BaseMarket


class HyperLiquidMarketInfo(msgspec.Struct):
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
    midPx: str
    dayBaseVlm: str

    # Spot specific fields
    circulatingSupply: str | None = None
    coin: str | None = None
    totalSupply: str | None = None
    tokens: list[int] | None = None
    index: int | None = None
    isCanonical: bool | None = None

    # Perpetual specific fields
    szDecimals: int | None = None
    maxLeverage: int | None = None
    funding: str | None = None
    openInterest: str | None = None
    premium: str | None = None
    oraclePx: str | None = None
    impactPxs: list[str] | None = None
    baseId: int | None = None


class HpyerLiquidMarket(BaseMarket):
    info: HyperLiquidMarketInfo

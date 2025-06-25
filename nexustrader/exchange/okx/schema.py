import msgspec
from typing import List
from nexustrader.schema import BaseMarket
from decimal import Decimal
from msgspec import Struct

from nexustrader.schema import Balance, BookOrderData
from nexustrader.exchange.okx.constants import (
    OkxInstrumentType,
    OkxInstrumentFamily,
    OkxOrderType,
    OkxOrderSide,
    OkxPositionSide,
    OkxTdMode,
    OkxOrderStatus,
    OkxSavingsPurchaseRedemptSide,
    OkxAcctLv,
    OkxPositionMode,
)


class OkxWsArgMsg(msgspec.Struct):
    channel: str | None = None
    instType: OkxInstrumentType | None = None
    instFamily: OkxInstrumentFamily | None = None
    instId: str | None = None
    uid: str | None = None


class OkxWsGeneralMsg(msgspec.Struct):
    event: str | None = None
    msg: str | None = None
    code: str | None = None
    connId: str | None = None
    channel: str | None = None
    arg: OkxWsArgMsg | None = None

    @property
    def is_event_msg(self) -> bool:
        return self.event is not None


class OkxWsBboTbtData(msgspec.Struct):
    ts: str
    seqId: int
    asks: list[list[str]]
    bids: list[list[str]]


class OkxWsBboTbtMsg(msgspec.Struct):
    """
    {
        "arg": {
            "channel": "bbo-tbt",
            "instId": "BCH-USDT-SWAP"
        },
        "data": [
            {
            "asks": [
                [
                "111.06","55154","0","2"
                ]
            ],
            "bids": [
                [
                "111.05","57745","0","2"
                ]
            ],
            "ts": "1670324386802",
            "seqId": 363996337
            }
        ]
    }
    """

    arg: OkxWsArgMsg
    data: list[OkxWsBboTbtData]


class OkxWsBook5BookDelta(msgspec.Struct, array_like=True):
    price: str
    size: str
    feature: str
    order_number: str

    def parse_to_book_order_data(self) -> BookOrderData:
        return BookOrderData(
            price=float(self.price),
            size=float(self.size),
        )


class OkxWsBook5Data(msgspec.Struct):
    asks: list[OkxWsBook5BookDelta]
    bids: list[OkxWsBook5BookDelta]
    ts: str
    seqId: int
    instId: str


class OkxWsBook5Msg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[OkxWsBook5Data]


class OkxWsCandleMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[list[str]]


class OkxWsIndexTickerData(msgspec.Struct):
    """
    "instId": "BTC-USDT",
    "idxPx": "0.1",
    "high24h": "0.5",
    "low24h": "0.1",
    "open24h": "0.1",
    "sodUtc0": "0.1",
    "sodUtc8": "0.1",
    "ts": "1597026383085"
    """

    instId: str
    idxPx: str
    high24h: str
    low24h: str
    open24h: str
    sodUtc0: str
    sodUtc8: str
    ts: str


class OkxWsIndexTickerMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[OkxWsIndexTickerData]


class OkxWsMarkPriceData(msgspec.Struct):
    instType: OkxInstrumentType
    instId: str
    markPx: str
    ts: str


class OkxWsMarkPriceMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[OkxWsMarkPriceData]


class OkxWsTradeData(msgspec.Struct):
    instId: str
    tradeId: str
    px: str
    sz: str
    side: str
    ts: str
    count: str


class OkxWsTradeMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[OkxWsTradeData]


class OkxWsFundingRateData(msgspec.Struct, kw_only=True):
    formulaType: str
    fundingRate: str
    fundingTime: str
    impactValue: str
    instId: str
    instType: OkxInstrumentType
    interestRate: str
    method: str
    maxFundingRate: str
    minFundingRate: str
    nextFundingRate: str
    nextFundingTime: str
    premium: str
    settFundingRate: str | None = None
    settState: str
    ts: str


class OkxWsFundingRateMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: list[OkxWsFundingRateData]


class OkxWsOrderData(msgspec.Struct):
    instType: OkxInstrumentType
    instId: str
    tgtCcy: str
    ccy: str
    ordId: str
    clOrdId: str
    tag: str
    px: str
    pxUsd: str
    pxVol: str
    pxType: str
    sz: str
    notionalUsd: str
    ordType: OkxOrderType
    side: OkxOrderSide
    posSide: OkxPositionSide
    tdMode: OkxTdMode
    fillPx: str  # last fill price
    tradeId: str  # last trade id
    fillSz: str  # last filled quantity
    fillPnl: str  # last filled profit and loss
    fillTime: str  # last filled time
    fillFee: str  # last filled fee
    fillFeeCcy: str  # last filled fee currency
    fillPxVol: str  # last filled price volume
    fillPxUsd: str  # last filled price in USD
    fillMarkVol: str  # last filled mark volume
    fillFwdPx: str  # last filled forward price
    fillMarkPx: str  # last filled mark price
    execType: str  # last execution type
    accFillSz: str  # accumulated filled quantity
    fillNotionalUsd: str  # accumulated filled notional in USD
    avgPx: str  # average price
    state: OkxOrderStatus
    lever: str  # leverage
    attachAlgoClOrdId: str  # attached algo order id
    tpTriggerPx: str  # take profit trigger price
    tpTriggerPxType: str  # take profit trigger price type
    tpOrdPx: str  # take profit order price
    slTriggerPx: str  # stop loss trigger price
    slTriggerPxType: str  # stop loss trigger price type
    slOrdPx: str  # stop loss order price
    stpMode: str  # stop loss mode
    feeCcy: str  # fee currency
    fee: str  # fee
    rebateCcy: str  # rebate currency
    rebate: str  # rebate
    pnl: str
    source: str
    cancelSource: str
    amendSource: str
    category: str
    isTpLimit: bool
    uTime: int
    cTime: int
    reqId: str
    amendResult: str
    reduceOnly: bool
    quickMgnType: str
    algoClOrdId: str
    algoId: str
    lastPx: str  # last price
    code: str
    msg: str


class OkxWsOrderMsg(msgspec.Struct):
    arg: OkxWsArgMsg
    data: List[OkxWsOrderData]


################################################################################
# Place Order: POST /api/v5/trade/order
################################################################################


class OkxPlaceOrderData(msgspec.Struct):
    ordId: str
    clOrdId: str
    tag: str
    ts: str  # milliseconds when OKX finished order request processing
    sCode: str  # event code, "0" means success
    sMsg: str  # rejection or success message of event execution


class OkxPlaceOrderResponse(msgspec.Struct):
    code: str
    msg: str
    data: list[OkxPlaceOrderData]
    inTime: str  # milliseconds when request hit REST gateway
    outTime: str  # milliseconds when response leaves REST gateway


################################################################################
# Amend order: POST /api/v5/trade/amend-order
################################################################################


class OkxAmendOrderData(msgspec.Struct):
    ordId: str
    clOrdId: str
    ts: str
    reqId: str
    sCode: str
    sMsg: str


class OkxAmendOrderResponse(msgspec.Struct):
    code: str
    msg: str
    data: list[OkxAmendOrderData]
    inTime: str
    outTime: str


################################################################################
# Cancel order: POST /api/v5/trade/cancel-order
################################################################################


class OkxGeneralResponse(msgspec.Struct):
    code: str
    msg: str


class OkxErrorData(msgspec.Struct):
    sCode: str
    sMsg: str


class OkxErrorResponse(msgspec.Struct):
    code: str
    data: list[OkxErrorData]
    msg: str


class OkxCancelOrderData(msgspec.Struct):
    ordId: str
    clOrdId: str
    ts: str  # milliseconds when OKX finished order request processing
    sCode: str  # event code, "0" means success
    sMsg: str  # rejection or success message of event execution


class OkxCancelOrderResponse(msgspec.Struct):
    code: str
    msg: str
    data: list[OkxCancelOrderData]
    inTime: str  # milliseconds when request hit REST gateway
    outTime: str  # milliseconds when response leaves REST gateway


class OkxMarketInfo(msgspec.Struct):
    """
    {
        "alias": "",
        "auctionEndTime": "",
        "baseCcy": "BTC",
        "category": "1",
        "ctMult": "",
        "ctType": "",
        "ctVal": "",
        "ctValCcy": "",
        "expTime": "",
        "instFamily": "",
        "instId": "BTC-USDT",
        "instType": "SPOT",
        "lever": "10",
        "listTime": "1611907686000",
        "lotSz": "0.00000001",
        "maxIcebergSz": "9999999999.0000000000000000",
        "maxLmtAmt": "20000000",
        "maxLmtSz": "9999999999",
        "maxMktAmt": "1000000",
        "maxMktSz": "1000000",
        "maxStopSz": "1000000",
        "maxTriggerSz": "9999999999.0000000000000000",
        "maxTwapSz": "9999999999.0000000000000000",
        "minSz": "0.00001",
        "optType": "",
        "quoteCcy": "USDT",
        "ruleType": "normal",
        "settleCcy": "",
        "state": "live",
        "stk": "",
        "tickSz": "0.1",
        "uly": ""
    },

    {
        "alias": "this_week",
        "auctionEndTime": "",
        "baseCcy": "",
        "category": "1",
        "ctMult": "1",
        "ctType": "linear",
        "ctVal": "0.01",
        "ctValCcy": "BTC",
        "expTime": "1731657600000",
        "instFamily": "BTC-USDT",
        "instId": "BTC-USDT-241115",
        "instType": "FUTURES",
        "lever": "20",
        "listTime": "1730448600359",
        "lotSz": "0.1",
        "maxIcebergSz": "1000000.0000000000000000",
        "maxLmtAmt": "20000000",
        "maxLmtSz": "1000000",
        "maxMktAmt": "",
        "maxMktSz": "3000",
        "maxStopSz": "3000",
        "maxTriggerSz": "1000000.0000000000000000",
        "maxTwapSz": "1000000.0000000000000000",
        "minSz": "0.1",
        "optType": "",
        "quoteCcy": "",
        "ruleType": "normal",
        "settleCcy": "USDT",
        "state": "live",
        "stk": "",
        "tickSz": "0.1",
        "uly": "BTC-USDT"
    },

    {
        "alias": "",
        "auctionEndTime": "",
        "baseCcy": "",
        "category": "1",
        "ctMult": "1",
        "ctType": "linear",
        "ctVal": "0.01",
        "ctValCcy": "BTC",
        "expTime": "",
        "instFamily": "BTC-USDT",
        "instId": "BTC-USDT-SWAP",
        "instType": "SWAP",
        "lever": "100",
        "listTime": "1573557408000",
        "lotSz": "0.1",
        "maxIcebergSz": "100000000.0000000000000000",
        "maxLmtAmt": "20000000",
        "maxLmtSz": "100000000",
        "maxMktAmt": "",
        "maxMktSz": "12000",
        "maxStopSz": "12000",
        "maxTriggerSz": "100000000.0000000000000000",
        "maxTwapSz": "100000000.0000000000000000",
        "minSz": "0.1",
        "optType": "",
        "quoteCcy": "",
        "ruleType": "normal",
        "settleCcy": "USDT",
        "state": "live",
        "stk": "",
        "tickSz": "0.1",
        "uly": "BTC-USDT"
    },
    """

    alias: str | None = None  # Alias (this_week, next_week, etc)
    auctionEndTime: str | None = None  # Auction end time
    baseCcy: str | None = None  # Base currency
    category: str | None = None  # Category
    ctMult: str | None = None  # Contract multiplier
    ctType: str | None = None  # Contract type (linear/inverse)
    ctVal: str | None = None  # Contract value
    ctValCcy: str | None = None  # Contract value currency
    expTime: str | None = None  # Expiry time
    instFamily: str | None = None  # Instrument family
    instId: str | None = None  # Instrument ID
    instType: str | None = None  # Instrument type (SPOT/FUTURES/SWAP)
    lever: str | None = None  # Leverage
    listTime: str | None = None  # Listing time
    lotSz: str | None = None  # Lot size
    maxIcebergSz: str | None = None  # Maximum iceberg order size
    maxLmtAmt: str | None = None  # Maximum limit order amount
    maxLmtSz: str | None = None  # Maximum limit order size
    maxMktAmt: str | None = None  # Maximum market order amount
    maxMktSz: str | None = None  # Maximum market order size
    maxStopSz: str | None = None  # Maximum stop order size
    maxTriggerSz: str | None = None  # Maximum trigger order size
    maxTwapSz: str | None = None  # Maximum TWAP order size
    minSz: str | None = None  # Minimum order size
    optType: str | None = None  # Option type
    quoteCcy: str | None = None  # Quote currency
    ruleType: str | None = None  # Rule type
    settleCcy: str | None = None  # Settlement currency
    state: str | None = None  # Instrument state
    stk: str | None = None  # Strike price
    tickSz: str | None = None  # Tick size
    uly: str | None = None  # Underlying


class OkxMarket(BaseMarket):
    """
     {
        "id": "BTC-USDT-SWAP",
        "lowercaseId": null,
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "quote": "USDT",
        "settle": "USDT",
        "baseId": "BTC",
        "quoteId": "USDT",
        "settleId": "USDT",
        "type": "swap",
        "spot": false,
        "margin": false,
        "swap": true,
        "future": false,
        "option": false,
        "index": null,
        "active": true,
        "contract": true,
        "linear": true,
        "inverse": false,
        "subType": "linear",
        "taker": 0.0005,
        "maker": 0.0002,
        "contractSize": 0.01,
        "expiry": null,
        "expiryDatetime": null,
        "strike": null,
        "optionType": null,
        "precision": {
            "amount": 0.1,
            "price": 0.1,
            "cost": null,
            "base": null,
            "quote": null
        },
        "limits": {
            "leverage": {
                "min": 1.0,
                "max": 100.0
            },
            "amount": {
                "min": 0.1,
                "max": null
            },
            "price": {
                "min": null,
                "max": null
            },
            "cost": {
                "min": null,
                "max": null
            }
        },
        "marginModes": {
            "cross": null,
            "isolated": null
        },
        "created": 1573557408000,
        "info": {
            "alias": "",
            "auctionEndTime": "",
            "baseCcy": "",
            "category": "1",
            "ctMult": "1",
            "ctType": "linear",
            "ctVal": "0.01",
            "ctValCcy": "BTC",
            "expTime": "",
            "instFamily": "BTC-USDT",
            "instId": "BTC-USDT-SWAP",
            "instType": "SWAP",
            "lever": "100",
            "listTime": "1573557408000",
            "lotSz": "0.1",
            "maxIcebergSz": "100000000.0000000000000000",
            "maxLmtAmt": "20000000",
            "maxLmtSz": "100000000",
            "maxMktAmt": "",
            "maxMktSz": "12000",
            "maxStopSz": "12000",
            "maxTriggerSz": "100000000.0000000000000000",
            "maxTwapSz": "100000000.0000000000000000",
            "minSz": "0.1",
            "optType": "",
            "quoteCcy": "",
            "ruleType": "normal",
            "settleCcy": "USDT",
            "state": "live",
            "stk": "",
            "tickSz": "0.1",
            "uly": "BTC-USDT"
        },
        "tierBased": null,
        "percentage": null
    },
    """

    info: OkxMarketInfo


class OkxPositionCloseOrderAlgo(Struct):
    algoId: str | None = None
    slTriggerPx: str | None = None
    slTriggerPxType: str | None = None
    tpTriggerPx: str | None = None
    tpTriggerPxType: str | None = None
    closeFraction: str | None = None


class OkxPosition(Struct, kw_only=True):
    adl: str
    availPos: str
    avgPx: str
    baseBal: str | None = None
    baseBorrowed: str | None = None
    baseInterest: str | None = None
    bePx: str
    bizRefId: str | None = None
    bizRefType: str | None = None
    cTime: str
    ccy: str
    clSpotInUseAmt: str | None = None
    closeOrderAlgo: List[OkxPositionCloseOrderAlgo] = []
    deltaBS: str | None = None
    deltaPA: str | None = None
    fee: str
    fundingFee: str
    gammaBS: str | None = None
    gammaPA: str | None = None
    idxPx: str
    imr: str | None = None
    instId: str
    instType: str
    interest: str | None = None
    last: str
    lever: str
    liab: str | None = None
    liabCcy: str | None = None
    liqPenalty: str
    liqPx: str
    margin: str
    markPx: str
    maxSpotInUseAmt: str | None = None
    mgnMode: str
    mgnRatio: str
    mmr: str
    notionalUsd: str
    optVal: str | None = None
    pTime: str
    pendingCloseOrdLiabVal: str | None = None
    pnl: str
    pos: str
    posCcy: str | None = None
    posId: str
    posSide: OkxPositionSide
    quoteBal: str | None = None
    quoteBorrowed: str | None = None
    quoteInterest: str | None = None
    realizedPnl: str
    spotInUseAmt: str | None = None
    spotInUseCcy: str | None = None
    thetaBS: str | None = None
    thetaPA: str | None = None
    tradeId: str
    uTime: str
    upl: str
    uplLastPx: str
    uplRatio: str
    uplRatioLastPx: str
    usdPx: str
    vegaBS: str | None = None
    vegaPA: str | None = None


class OkxAccountDetail(Struct, kw_only=True):
    accAvgPx: str | None = None
    availBal: str
    availEq: str
    borrowFroz: str | None = None
    cashBal: str
    ccy: str
    clSpotInUseAmt: str | None = None
    coinUsdPrice: str
    crossLiab: str | None = None
    disEq: str
    eq: str
    eqUsd: str
    fixedBal: str
    frozenBal: str
    imr: str
    interest: str | None = None
    isoEq: str
    isoLiab: str | None = None
    isoUpl: str
    liab: str | None = None
    maxLoan: str | None = None
    maxSpotInUseAmt: str | None = None
    mgnRatio: str | None = None
    mmr: str
    notionalLever: str
    openAvgPx: str | None = None
    ordFrozen: str
    rewardBal: str
    smtSyncEq: str
    spotBal: str | None = None
    spotCopyTradingEq: str
    spotInUseAmt: str | None = None
    spotIsoBal: str
    spotUpl: str | None = None
    spotUplRatio: str | None = None
    stgyEq: str
    totalPnl: str | None = None
    totalPnlRatio: str | None = None
    twap: str
    uTime: str
    upl: str
    uplLiab: str | None = None

    def parse_to_balance(self) -> Balance:
        """Convert OKX account detail to standard Balance object"""
        return Balance(
            asset=self.ccy,
            free=Decimal(self.availBal),
            locked=Decimal(self.frozenBal),
        )


class OkxAccount(Struct):
    adjEq: str | None = None
    borrowFroz: str | None = None
    details: List[OkxAccountDetail] | None = None
    imr: str | None = None
    isoEq: str | None = None
    mgnRatio: str | None = None
    mmr: str | None = None
    notionalUsd: str | None = None
    ordFroz: str | None = None
    totalEq: str | None = None
    uTime: str | None = None
    upl: str | None = None

    def parse_to_balance(self) -> list[Balance]:
        return [detail.parse_to_balance() for detail in self.details]


class OkxWsPositionMsg(Struct):
    arg: dict
    data: List[OkxPosition]


class OkxWsAccountMsg(Struct):
    arg: dict
    data: List[OkxAccount]


################################################################################
# GET /api/v5/account/balance
################################################################################


class OkxBalanceDetail(msgspec.Struct):
    availBal: str  # Available balance
    availEq: str  # Available equity
    borrowFroz: str  # Potential borrowing IMR in USD
    cashBal: str  # Cash balance
    ccy: str  # Currency
    crossLiab: str  # Cross liabilities
    disEq: str  # Discount equity in USD
    eq: str  # Equity
    eqUsd: str  # Equity in USD
    smtSyncEq: str  # Smart sync equity
    spotCopyTradingEq: str  # Spot smart sync equity
    fixedBal: str  # Frozen balance for Dip/Peak Sniper
    frozenBal: str  # Frozen balance
    imr: str  # Cross initial margin requirement
    interest: str  # Accrued interest
    isoEq: str  # Isolated margin equity
    isoLiab: str  # Isolated liabilities
    isoUpl: str  # Isolated unrealized PnL
    liab: str  # Liabilities
    maxLoan: str  # Max loan
    mgnRatio: str  # Cross margin ratio
    mmr: str  # Cross maintenance margin requirement
    notionalLever: str  # Leverage
    ordFrozen: str  # Margin frozen for open orders
    rewardBal: str  # Trial fund balance
    spotInUseAmt: str  # Spot in use amount
    clSpotInUseAmt: str  # User-defined spot risk offset amount
    maxSpotInUse: str  # Max possible spot risk offset amount
    spotIsoBal: str  # Spot isolated balance
    stgyEq: str  # Strategy equity
    twap: str  # Risk indicator of auto liability repayment
    uTime: str  # Update time
    upl: str  # Unrealized PnL
    uplLiab: str  # Liabilities due to unrealized loss
    spotBal: str  # Spot balance
    openAvgPx: str  # Spot average cost price
    accAvgPx: str  # Spot accumulated cost price
    spotUpl: str  # Spot unrealized PnL
    spotUplRatio: str  # Spot unrealized PnL ratio
    totalPnl: str  # Spot accumulated PnL
    totalPnlRatio: str  # Spot accumulated PnL ratio

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.ccy,
            free=Decimal(self.availBal),
            locked=Decimal(self.frozenBal),
        )


class OkxBalanceData(msgspec.Struct):
    adjEq: str  # Adjusted/Effective equity in USD
    borrowFroz: str  # Potential borrowing IMR of account in USD
    details: list[OkxBalanceDetail]  # Detailed asset information
    imr: str  # Initial margin requirement in USD
    isoEq: str  # Isolated margin equity in USD
    mgnRatio: str  # Margin ratio in USD
    mmr: str  # Maintenance margin requirement in USD
    notionalUsd: str  # Notional value of positions in USD
    ordFroz: str  # Cross margin frozen for pending orders
    totalEq: str  # Total equity in USD
    uTime: int  # Update time
    upl: str  # Unrealized PnL in USD

    def parse_to_balances(self) -> list[Balance]:
        return [detail.parse_to_balance() for detail in self.details]


class OkxBalanceResponse(msgspec.Struct):
    code: str  # Response code
    data: list[OkxBalanceData]  # Balance data
    msg: str  # Response message


################################################################################
# GET /api/v5/account/positions
################################################################################


class OkxPositionResponseData(msgspec.Struct):
    adl: str
    availPos: str
    avgPx: str
    bePx: str
    bizRefId: str
    bizRefType: str
    cTime: str
    ccy: str
    clSpotInUseAmt: str
    closeOrderAlgo: List[OkxPositionCloseOrderAlgo]
    deltaBS: str
    deltaPA: str
    fee: str
    fundingFee: str
    gammaBS: str
    gammaPA: str
    idxPx: str
    imr: str
    instId: str
    instType: str
    interest: str
    last: str
    lever: str
    liab: str
    liabCcy: str
    liqPenalty: str
    liqPx: str
    margin: str
    markPx: str
    maxSpotInUseAmt: str
    mgnMode: str
    mgnRatio: str
    mmr: str
    notionalUsd: str
    optVal: str
    pendingCloseOrdLiabVal: str
    pnl: str
    pos: str
    posCcy: str
    posId: str
    posSide: OkxPositionSide
    realizedPnl: str
    spotInUseAmt: str
    spotInUseCcy: str
    thetaBS: str
    thetaPA: str
    tradeId: str
    uTime: int
    upl: str
    uplLastPx: str
    uplRatio: str
    uplRatioLastPx: str
    usdPx: str
    vegaBS: str
    vegaPA: str


class OkxPositionResponse(msgspec.Struct):
    code: str
    data: List[OkxPositionResponseData]
    msg: str


class OkxIndexCandlesticksResponse(msgspec.Struct):
    code: str
    data: list["OkxIndexCandlesticksResponseData"]
    msg: str


class OkxIndexCandlesticksResponseData(msgspec.Struct, array_like=True):
    ts: int
    o: str
    h: str
    l: str  # noqa: E741
    c: str
    confirm: str


class OkxCandlesticksResponse(msgspec.Struct):
    code: str
    data: list["OkxCandlesticksResponseData"]
    msg: str


class OkxCandlesticksResponseData(msgspec.Struct, array_like=True):
    """
    [
        "1597026383085",
        "3.721",
        "3.743",
        "3.677",
        "3.708",
        "8422410",
        "22698348.04828491",
        "12698348.04828491",
        "1"
    ],
    """

    ts: int
    o: str
    h: str
    l: str  # noqa: E741
    c: str
    vol: str
    volCcy: str
    volCcyQuote: str
    confirm: int


class OkxSavingsBalanceResponse(msgspec.Struct):
    code: str
    data: list["OkxSavingsBalanceResponseData"]
    msg: str


class OkxSavingsBalanceResponseData(msgspec.Struct):
    """
    ccy	String	币种，如 BTC
    amt	String	币种数量
    earnings	String	币种持仓收益
    rate	String	最新出借利率
    loanAmt	String	已出借数量
    pendingAmt	String	未出借数量
    """

    ccy: str
    amt: str
    earnings: str
    rate: str
    loanAmt: str
    pendingAmt: str


class OkxSavingsPurchaseRedemptResponse(msgspec.Struct):
    code: str
    data: list["OkxSavingsPurchaseRedemptResponseData"]
    msg: str


class OkxSavingsPurchaseRedemptResponseData(msgspec.Struct):
    ccy: str
    amt: str
    side: OkxSavingsPurchaseRedemptSide
    rate: str


class OkxSavingsLendingRateSummaryResponse(msgspec.Struct):
    code: str
    data: list["OkxSavingsLendingRateSummaryResponseData"]
    msg: str


class OkxSavingsLendingRateSummaryResponseData(msgspec.Struct):
    """
    ccy: str
    avgAmt: str
    avgAmtUsd: str
    avgRate: str
    preRate: str
    estRate: str
    """

    ccy: str
    avgAmt: str
    avgAmtUsd: str
    avgRate: str
    preRate: str
    estRate: str


class OkxSavingsLendingRateHistoryResponse(msgspec.Struct):
    code: str
    data: list["OkxSavingsLendingRateHistoryResponseData"]
    msg: str


class OkxSavingsLendingRateHistoryResponseData(msgspec.Struct):
    """
    ccy	String	Currency, e.g. BTC
    amt	String	Lending amount
    rate	String	Lending annual interest rate
    ts	String	Timestamp
    """

    ccy: str
    amt: str
    rate: str
    ts: str


class OkxAssetTransferResponse(msgspec.Struct):
    code: str
    data: list["OkxAssetTransferResponseData"]
    msg: str


class OkxAssetTransferResponseData(msgspec.Struct):
    """
    transId: str
    ccy: str
    clientId: str
    from: str
    amt: str
    to: str

    """

    transId: str
    ccy: str
    clientId: str
    from_acct: str = msgspec.field(name="from")
    amt: str
    to: str


class OkxFinanceStakingDefiRedeemResponse(msgspec.Struct):
    code: str
    data: list["OkxFinanceStakingDefiRedeemResponseData"]
    msg: str


class OkxFinanceStakingDefiRedeemResponseData(msgspec.Struct):
    ordId: str
    tag: str


class OkxFinanceStakingDefiPurchaseResponse(msgspec.Struct):
    code: str
    data: list["OkxFinanceStakingDefiPurchaseResponseData"]
    msg: str


class OkxFinanceStakingDefiPurchaseResponseData(msgspec.Struct):
    ordId: str
    tag: str


class OkxFinanceStakingDefiOffersResponse(msgspec.Struct):
    code: str
    data: list["OkxFinanceStakingDefiOffersResponseData"]
    msg: str


class OkxFinanceStakingDefiOffersResponseData(msgspec.Struct):
    ccy: str
    productId: str
    protocol: str
    protocolType: str
    term: str
    apy: str
    earlyRedeem: bool
    state: str
    investData: list["OkxFinanceStakingDefiOffersInvestData"]
    earningData: list["OkxFinanceStakingDefiOffersEarningData"]
    fastRedemptionDailyLimit: str
    redeemPeriod: list[str]


class OkxFinanceStakingDefiOffersInvestData(msgspec.Struct):
    bal: str
    ccy: str
    maxAmt: str
    minAmt: str


class OkxFinanceStakingDefiOffersEarningData(msgspec.Struct):
    ccy: str
    earningType: str


class OkxAccountConfigResponse(msgspec.Struct):
    code: str
    data: list["OkxAccountConfigResponseData"]
    msg: str


class OkxAccountConfigResponseData(msgspec.Struct):
    """
    Account configuration response data from OKX API.
    """

    uid: str  # Account ID of current request
    mainUid: str  # Main Account ID of current request
    acctLv: OkxAcctLv  # Account mode (1: Spot, 2: Futures, 3: Multi-currency margin, 4: Portfolio margin)
    acctStpMode: str  # Account self-trade prevention mode (cancel_maker, cancel_taker, cancel_both)
    posMode: OkxPositionMode  # Position mode (long_short_mode, net_mode)
    autoLoan: bool  # Whether to borrow coins automatically
    greeksType: (
        str  # Current display type of Greeks (PA: coins, BS: Black-Scholes in dollars)
    )
    level: str  # User level of current real trading volume
    levelTmp: str  # Temporary experience user level
    ctIsoMode: str  # Contract isolated margin trading settings (automatic, autonomy)
    mgnIsoMode: str  # Margin isolated margin trading settings (auto_transfers_ccy, automatic, quick_margin)
    spotOffsetType: str  # Risk offset type (1: Spot-Derivatives(USDT), 2: Spot-Derivatives(Coin), 3: Only derivatives)
    roleType: str  # Role type (0: General user, 1: Leading trader, 2: Copy trader)
    traderInsts: list[str]  # Leading trade instruments
    spotRoleType: str  # SPOT copy trading role type (0: General user, 1: Leading trader, 2: Copy trader)
    spotTraderInsts: list[str]  # Spot lead trading instruments
    opAuth: (
        str  # Whether optional trading was activated (0: not activate, 1: activated)
    )
    kycLv: str  # Main account KYC level (0: No verification, 1: level 1, 2: level 2, 3: level 3)
    label: str  # API key note
    ip: str  # IP addresses linked with current API key
    perm: str  # Permission of current API key (read_only, trade, withdraw)
    liquidationGear: str  # Maintenance margin ratio level of liquidation alert
    enableSpotBorrow: bool  # Whether borrow is allowed in Spot mode
    spotBorrowAutoRepay: bool  # Whether auto-repay is allowed in Spot mode
    type: str  # Account type (0: Main account, 1: Standard sub-account, 2: Managed trading sub-account, etc.)


class OkxBatchOrderResponse(msgspec.Struct):
    """
    Response structure for batch order operations.
    """

    code: str  # Response code
    msg: str  # Response message
    data: list["OkxBatchOrderResponseData"]  # List of order data
    inTime: str  # Time when the request was received by the REST gateway
    outTime: str  # Time when the response was sent from the REST gateway


class OkxBatchOrderResponseData(msgspec.Struct):
    """
    Data structure for individual order in batch order response.
    """

    ordId: str  # Order ID
    clOrdId: str  # Client order ID
    tag: str  # Tag associated with the order
    ts: str  # Timestamp when the order was processed
    sCode: str  # Status code of the order processing (0 means success)
    sMsg: str  # Status message of the order processing (success or error message)

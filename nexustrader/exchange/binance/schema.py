import msgspec
from decimal import Decimal
from typing import Any, Dict, List
from nexustrader.schema import BaseMarket, Balance, BookOrderData
from nexustrader.exchange.binance.constants import (
    BinanceAccountEventReasonType,
    BinanceOrderStatus,
    BinanceOrderType,
    BinancePositionSide,
    BinanceWsEventType,
    BinanceKlineInterval,
    BinancePriceMatch,
    BinanceUserDataStreamWsEventType,
    BinanceOrderSide,
    BinanceTimeInForce,
    BinanceExecutionType,
    BinanceFuturesWorkingType,
    BinanceBusinessUnit,
)


class BinanceResultId(msgspec.Struct):
    id: int | None = None


class BinanceFuturesBalanceInfo(msgspec.Struct, frozen=True):
    asset: str  # asset name
    walletBalance: str  # wallet balance
    unrealizedProfit: str  # unrealized profit
    marginBalance: str  # margin balance
    maintMargin: str  # maintenance margin required
    initialMargin: str  # total initial margin required with current mark price
    positionInitialMargin: (
        str  # initial margin required for positions with current mark price
    )
    openOrderInitialMargin: (
        str  # initial margin required for open orders with current mark price
    )
    crossWalletBalance: str  # crossed wallet balance
    crossUnPnl: str  # unrealized profit of crossed positions
    availableBalance: str  # available balance
    maxWithdrawAmount: str  # maximum amount for transfer out
    # whether the asset can be used as margin in Multi - Assets mode
    marginAvailable: bool | None = None
    updateTime: int | None = None  # last update time

    def parse_to_balance(self) -> Balance:
        free = Decimal(self.availableBalance)
        locked = Decimal(self.marginBalance) - free
        return Balance(
            asset=self.asset,
            free=free,
            locked=locked,
        )


class BinanceFuturesPositionInfo(msgspec.Struct, kw_only=True):
    symbol: str  # symbol name
    initialMargin: str  # initial margin required with current mark price
    maintMargin: str  # maintenance margin required
    unrealizedProfit: str  # unrealized profit
    positionInitialMargin: (
        str  # initial margin required for positions with current mark price
    )
    openOrderInitialMargin: (
        str  # initial margin required for open orders with current mark price
    )
    leverage: str  # current initial leverage
    isolated: bool  # if the position is isolated
    entryPrice: str  # average entry price
    maxNotional: str | None = None  # maximum available notional with current leverage
    bidNotional: str | None = None  # bids notional, ignore
    askNotional: str | None = None  # ask notional, ignore
    positionSide: BinancePositionSide  # position side
    positionAmt: str  # position amount
    updateTime: int
    breakEvenPrice: str | None = None  # break-even price
    maxQty: str | None = None  # maximum quantity of base asset


class BinancePortfolioMarginPositionRisk(msgspec.Struct, kw_only=True):
    """
    "entryPrice": "0.00000",
    "leverage": "10",
    "markPrice": "6679.50671178",
    "maxNotionalValue": "20000000",
    "positionAmt": "0.000",
    "notional": "0",
    "symbol": "BTCUSDT",
    "unRealizedProfit": "0.00000000",
    "liquidationPrice": "6170.20509059",
    "positionSide": "BOTH",
    "updateTime": 1625474304765

    "symbol": "BTCUSD_201225",
    "positionAmt": "1",
    "entryPrice": "11707.70000003",
    "markPrice": "11788.66626667",
    "unRealizedProfit": "0.00005866",
    "liquidationPrice": "6170.20509059",
    "leverage": "125",
    "positionSide": "LONG",
    "updateTime": 1627026881327,
    "maxQty": "50",
    "notionalValue": "0.00084827"
    """

    symbol: str
    markPrice: str
    entryPrice: str
    unRealizedProfit: str
    positionAmt: str
    positionSide: BinancePositionSide
    liquidationPrice: str
    updateTime: int
    leverage: str

    notional: str | None = None
    maxNotionalValue: str | None = None

    maxQty: str | None = None
    notionalValue: str | None = None


class BinancePortfolioMarginBalance(msgspec.Struct, kw_only=True):
    """
    "asset": "USDT",    // asset name
    "totalWalletBalance": "122607.35137903", // wallet balance =  cross margin free + cross margin locked + UM wallet balance + CM wallet balance
    "crossMarginAsset": "92.27530794", // crossMarginAsset = crossMarginFree + crossMarginLocked
    "crossMarginBorrowed": "10.00000000", // principal of cross margin
    "crossMarginFree": "100.00000000", // free asset of cross margin
    "crossMarginInterest": "0.72469206", // interest of cross margin
    "crossMarginLocked": "3.00000000", //lock asset of cross margin
    "umWalletBalance": "0.00000000",  // wallet balance of um
    "umUnrealizedPNL": "23.72469206",     // unrealized profit of um
    "cmWalletBalance": "23.72469206",       // wallet balance of cm
    "cmUnrealizedPNL": "",    // unrealized profit of cm
    "updateTime": 1617939110373,
    "negativeBalance": "0"
    """

    asset: str
    totalWalletBalance: str
    crossMarginAsset: str
    crossMarginBorrowed: str
    crossMarginFree: str
    crossMarginInterest: str
    crossMarginLocked: str
    umWalletBalance: str
    umUnrealizedPNL: str
    cmWalletBalance: str
    cmUnrealizedPNL: str
    updateTime: int
    negativeBalance: str

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.asset,
            free=Decimal(self.crossMarginFree)
            + Decimal(self.umWalletBalance)
            + Decimal(self.cmWalletBalance),
            locked=Decimal(self.crossMarginLocked),
        )


class BinanceFuturesAccountInfo(msgspec.Struct, kw_only=True):
    feeTier: int  # account commission tier
    canTrade: bool  # if can trade
    canDeposit: bool  # if can transfer in asset
    canWithdraw: bool  # if can transfer out asset
    updateTime: int
    totalInitialMargin: str | None = (
        None  # total initial margin required with current mark price (useless with isolated positions), only for USDT
    )
    totalMaintMargin: str | None = (
        None  # total maintenance margin required, only for USDT asset
    )
    totalWalletBalance: str | None = None  # total wallet balance, only for USDT asset
    totalUnrealizedProfit: str | None = (
        None  # total unrealized profit, only for USDT asset
    )
    totalMarginBalance: str | None = None  # total margin balance, only for USDT asset
    # initial margin required for positions with current mark price, only for USDT asset
    totalPositionInitialMargin: str | None = None
    # initial margin required for open orders with current mark price, only for USDT asset
    totalOpenOrderInitialMargin: str | None = None
    totalCrossWalletBalance: str | None = (
        None  # crossed wallet balance, only for USDT asset
    )
    # unrealized profit of crossed positions, only for USDT asset
    totalCrossUnPnl: str | None = None
    availableBalance: str | None = None  # available balance, only for USDT asset
    maxWithdrawAmount: str | None = (
        None  # maximum amount for transfer out, only for USDT asset
    )
    assets: list[BinanceFuturesBalanceInfo]
    positions: list[BinanceFuturesPositionInfo]

    def parse_to_balances(self) -> List[Balance]:
        return [balance.parse_to_balance() for balance in self.assets]


class BinanceSpotBalanceInfo(msgspec.Struct):
    asset: str
    free: str
    locked: str

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.asset,
            free=Decimal(self.free),
            locked=Decimal(self.locked),
        )


class BinanceSpotAccountInfo(msgspec.Struct, frozen=True):
    makerCommission: int
    takerCommission: int
    buyerCommission: int
    sellerCommission: int
    canTrade: bool
    canWithdraw: bool
    canDeposit: bool
    updateTime: int
    accountType: str
    balances: list[BinanceSpotBalanceInfo]
    permissions: list[str]

    def parse_to_balances(self) -> List[Balance]:
        return [balance.parse_to_balance() for balance in self.balances]


class BinanceSpotOrderUpdateMsg(msgspec.Struct, kw_only=True):
    C: str | None = None
    E: int
    F: str | None = None
    I: int  # noqa: E741
    L: str
    M: bool | None = None
    N: str | None = None
    O: int  # noqa: E741
    P: str
    Q: str | None = None
    S: BinanceOrderSide
    T: int
    V: str
    W: int | None = None  # Working Time
    X: BinanceOrderStatus
    Y: str
    Z: str
    c: str
    e: BinanceUserDataStreamWsEventType
    f: BinanceTimeInForce
    g: int
    i: int
    l: str  # noqa: E741
    m: bool
    n: str | None = None
    o: BinanceOrderType
    p: str
    q: str
    r: str | None = None
    s: str
    t: int
    v: int | None = None
    w: bool
    x: BinanceExecutionType
    z: str

    A: str | None = None  # Prevented Quantity
    B: str | None = None  # Last Prevented Quantity
    D: int | None = None  # trailing time
    J: int | None = None  # strategy type
    U: int | None = None  # CounterOrderId
    d: int | None = None  # trailing Delta
    j: int | None = None  # strategy id
    u: int | None = None  # Trade Group id


class BinanceFuturesOrderData(msgspec.Struct, kw_only=True):
    L: str  # Last Filled Price
    N: str  # Commission Asset
    R: bool  # Is reduce only
    S: BinanceOrderSide
    T: int  # Order Trade Time
    V: str  # Order Filled Accumulated Quantity
    X: BinanceOrderStatus
    a: str  # Ask Notional
    ap: str  # Average Price
    b: str  # Bids Notional
    c: str  # Client Order ID
    f: BinanceTimeInForce
    i: int  # Order ID
    l: str  # Order Last Filled Quantity # noqa: E741
    m: bool  # Is trade the maker side
    n: str  # Commission, will not push if no commission
    o: BinanceOrderType
    p: str  # Original Price
    ps: BinancePositionSide
    q: str  # Original Quantity
    rp: str  # Realized Profit of the trade
    s: str  # Symbol
    sp: str  # Stop Price
    t: int  # Trade ID
    x: BinanceExecutionType
    z: str  # Order Filled Accumulated Quantity

    AP: str | None = None  # Activation Price
    cp: bool | None = None  # If Close-All, pushed with conditional order
    cr: str | None = None  # Callback Rate
    gtd: int | None = None  # TIF GTD order auto cancel time
    ot: BinanceOrderType | None = None
    pP: bool | None = None  # ignore
    pm: str | None = None  # Order Margin Type
    si: int | None = None  # ignore
    ss: int | None = None  # ignore
    wt: BinanceFuturesWorkingType | None = None
    ma: str | None = None  # Order Margin Type
    st: str | None = (
        None  #  Strategy type, only pushed with conditional order triggered
    )


class BinanceFuturesOrderUpdateMsg(msgspec.Struct, kw_only=True):
    """
    WebSocket message for Binance Futures Order Update events.
    """

    e: BinanceUserDataStreamWsEventType
    E: int  # Event Time
    T: int  # Transaction Time
    fs: BinanceBusinessUnit | None = (
        None  # Event business unit. 'UM' for USDS-M futures and 'CM' for COIN-M futures
    )
    o: BinanceFuturesOrderData


class BinanceMarkPriceDataStream(msgspec.Struct):
    e: BinanceWsEventType
    E: int
    s: str
    p: str
    i: str
    P: str
    r: str
    T: int


class BinanceMarkPrice(msgspec.Struct):
    data: BinanceMarkPriceDataStream
    stream: str


class BinanceKlineData(msgspec.Struct):
    t: int  # Kline start time
    T: int  # Kline close time
    s: str  # Symbol
    i: BinanceKlineInterval  # Interval
    f: int  # First trade ID
    L: int  # Last trade ID
    o: str  # Open price
    c: str  # Close price
    h: str  # High price
    l: str  # Low price # noqa
    v: str  # Base asset volume
    n: int  # Number of trades
    x: bool  # Is this kline closed?
    q: str  # Quote asset volume
    V: str  # Taker buy base asset volume
    Q: str  # Taker buy quote asset volume
    B: str  # Ignore


class BinanceKlineDataStream(msgspec.Struct):
    e: BinanceWsEventType
    E: int
    s: str
    k: BinanceKlineData


class BinanceKline(msgspec.Struct):
    data: BinanceKlineDataStream
    stream: str


class BinanceTradeDataStream(msgspec.Struct):
    e: BinanceWsEventType
    E: int
    s: str
    t: int
    p: str
    q: str
    T: int


class BinanceTradeData(msgspec.Struct):
    data: BinanceTradeDataStream
    stream: str


class BinanceSpotBookTickerData(msgspec.Struct):
    """
      {
        "u":400900217,     // order book updateId
        "s":"BNBUSDT",     // symbol
        "b":"25.35190000", // best bid price
        "B":"31.21000000", // best bid qty
        "a":"25.36520000", // best ask price
        "A":"40.66000000"  // best ask qty
    }
    """

    u: int
    s: str
    b: str
    B: str
    a: str
    A: str


class BinanceSpotBookTicker(msgspec.Struct):
    data: BinanceSpotBookTickerData
    stream: str


class BinanceFuturesBookTickerData(msgspec.Struct):
    e: BinanceWsEventType
    u: int
    E: int
    T: int
    s: str
    b: str
    B: str
    a: str
    A: str


class BinanceFuturesBookTicker(msgspec.Struct):
    data: BinanceFuturesBookTickerData
    stream: str


class BinanceWsMessageGeneralData(msgspec.Struct):
    e: BinanceWsEventType | None = None
    u: int | None = None


class BinanceWsMessageGeneral(msgspec.Struct):
    data: BinanceWsMessageGeneralData


class BinanceUserDataStreamMsg(msgspec.Struct):
    e: BinanceUserDataStreamWsEventType | None = None


class BinanceListenKey(msgspec.Struct):
    listenKey: str


class BinanceUserTrade(msgspec.Struct, frozen=True):
    commission: str
    commissionAsset: str
    price: str
    qty: str

    # Parameters not present in 'fills' list (see FULL response of BinanceOrder)
    symbol: str | None = None
    id: int | None = None
    orderId: int | None = None
    time: int | None = None
    quoteQty: str | None = None  # SPOT/MARGIN & USD-M FUTURES only

    # Parameters in SPOT/MARGIN only:
    orderListId: int | None = None  # unless OCO, the value will always be -1
    isBuyer: bool | None = None
    isMaker: bool | None = None
    isBestMatch: bool | None = None
    tradeId: int | None = None  # only in BinanceOrder FULL response

    # Parameters in FUTURES only:
    buyer: bool | None = None
    maker: bool | None = None
    realizedPnl: str | None = None
    side: BinanceOrderSide | None = None
    positionSide: str | None = None
    baseQty: str | None = None  # COIN-M FUTURES only
    pair: str | None = None  # COIN-M FUTURES only


class BinanceOrder(msgspec.Struct, frozen=True):
    symbol: str
    orderId: int
    clientOrderId: str

    # Parameters not in ACK response:
    price: str | None = None
    origQty: str | None = None
    executedQty: str | None = None
    status: BinanceOrderStatus | None = None
    timeInForce: BinanceTimeInForce | None = None
    goodTillDate: int | None = None
    type: BinanceOrderType | None = None
    side: BinanceOrderSide | None = None
    stopPrice: str | None = (
        None  # please ignore when order type is TRAILING_STOP_MARKET
    )
    time: int | None = None
    updateTime: int | None = None

    # Parameters in SPOT/MARGIN only:
    orderListId: int | None = None  # Unless OCO, the value will always be -1
    cumulativeQuoteQty: str | None = None  # cumulative quote qty
    icebergQty: str | None = None
    isWorking: bool | None = None
    workingTime: int | None = None
    origQuoteOrderQty: str | None = None
    selfTradePreventionMode: str | None = None
    transactTime: int | None = None  # POST & DELETE methods only
    fills: list[BinanceUserTrade] | None = None  # FULL response only

    # Parameters in FUTURES only:
    avgPrice: str | None = None
    origType: BinanceOrderType | None = None
    reduceOnly: bool | None = None
    positionSide: BinancePositionSide | None = None
    closePosition: bool | None = None
    activatePrice: str | None = (
        None  # activation price, only for TRAILING_STOP_MARKET order
    )
    priceRate: str | None = None  # callback rate, only for TRAILING_STOP_MARKET order
    workingType: str | None = None
    priceProtect: bool | None = None  # if conditional order trigger is protected
    cumQuote: str | None = None  # USD-M FUTURES only
    cumBase: str | None = None  # COIN-M FUTURES only
    pair: str | None = None  # COIN-M FUTURES only


class BinanceFuturesModifyOrderResponse(msgspec.Struct, frozen=True, kw_only=True):
    """
        {
            "orderId": 20072994037,
            "symbol": "BTCUSDT",
            "pair": "BTCUSDT",
            "status": "NEW",
            "clientOrderId": "LJ9R4QZDihCaS8UAOOLpgW",
            "price": "30005",
            "avgPrice": "0.0",
            "origQty": "1",
            "executedQty": "0",
            "cumQty": "0",
            "cumBase": "0",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "reduceOnly": false,
            "closePosition": false,
            "side": "BUY",
            "positionSide": "LONG",
            "stopPrice": "0",
            "workingType": "CONTRACT_PRICE",
            "priceProtect": false,
            "origType": "LIMIT",
        "priceMatch": "NONE",              //price match mode
        "selfTradePreventionMode": "NONE", //self trading preventation mode
        "goodTillDate": 0,                 //order pre-set auot cancel time for TIF GTD order
        "updateTime": 1629182711600
    }
    """

    orderId: int
    symbol: str
    pair: str | None = None
    status: BinanceOrderStatus
    clientOrderId: str
    price: str
    avgPrice: str
    origQty: str
    executedQty: str
    cumQty: str
    cumBase: str | None = None
    cumQuote: str | None = None
    timeInForce: BinanceTimeInForce
    type: BinanceOrderType
    reduceOnly: bool | None = None
    closePosition: bool | None = None
    side: BinanceOrderSide
    positionSide: BinancePositionSide
    stopPrice: str | None = None
    workingType: BinanceFuturesWorkingType | None = None
    priceProtect: bool | None = None
    origType: BinanceOrderType
    priceMatch: BinancePriceMatch | None = None
    selfTradePreventionMode: str | None = None
    goodTillDate: int | None = None
    updateTime: int


class BinanceMarketInfo(msgspec.Struct):
    symbol: str = None
    status: str = None
    baseAsset: str = None
    baseAssetPrecision: str | int = None
    quoteAsset: str = None
    quotePrecision: str | int = None
    quoteAssetPrecision: str | int = None
    baseCommissionPrecision: str | int = None
    quoteCommissionPrecision: str | int = None
    orderTypes: List[BinanceOrderType] = None
    icebergAllowed: bool = None
    ocoAllowed: bool = None
    otoAllowed: bool = None
    quoteOrderQtyMarketAllowed: bool = None
    allowTrailingStop: bool = None
    cancelReplaceAllowed: bool = None
    isSpotTradingAllowed: bool = None
    isMarginTradingAllowed: bool = None
    filters: List[Dict[str, Any]] = None
    permissions: List[str] = None
    permissionSets: List[List[str] | str] = None
    defaultSelfTradePreventionMode: str = None
    allowedSelfTradePreventionModes: List[str] = None


class BinanceMarket(BaseMarket):
    info: BinanceMarketInfo
    feeSide: str


class BinanceFuturesBalanceData(msgspec.Struct):
    a: str
    wb: str  # wallet balance
    cw: str  # cross wallet balance
    bc: str  # wallet change except PnL and Commission

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.a,
            free=Decimal(self.wb),
            locked=Decimal(0),
        )


class BinanceFuturesPositionData(msgspec.Struct, kw_only=True):
    s: str
    pa: str  # position amount
    ep: str  # entry price
    bep: str | float  # breakeven price
    cr: str  # (Pre-fee) Accumulated Realized
    up: str  # Unrealized PnL
    mt: str | None = None  # margin type (if isolated position)
    iw: str | None = None  # isolated wallet (if isolated position)
    ps: BinancePositionSide


class BinanceFuturesUpdateData(msgspec.Struct, kw_only=True):
    m: BinanceAccountEventReasonType
    B: list[BinanceFuturesBalanceData]
    P: list[BinanceFuturesPositionData]

    def parse_to_balances(self) -> List[Balance]:
        return [balance.parse_to_balance() for balance in self.B]


class BinanceFuturesUpdateMsg(msgspec.Struct, kw_only=True):
    e: BinanceUserDataStreamWsEventType
    E: int
    T: int
    fs: BinanceBusinessUnit | None = None
    a: BinanceFuturesUpdateData


class BinanceSpotBalanceData(msgspec.Struct):
    a: str  # asset
    f: str  # free
    l: str  # locked # noqa: E741

    def parse_to_balance(self) -> Balance:
        return Balance(
            asset=self.a,
            free=Decimal(self.f),
            locked=Decimal(self.l),
        )


class BinanceSpotUpdateMsg(msgspec.Struct, kw_only=True):
    e: BinanceUserDataStreamWsEventType  # event type
    E: int  # event time
    u: int  # Time of last account update
    B: list[BinanceSpotBalanceData]  # balance array of the account

    def parse_to_balances(self) -> List[Balance]:
        return [balance.parse_to_balance() for balance in self.B]


class BinanceResponseKline(msgspec.Struct, array_like=True):
    """
    [
        1499040000000,      // Kline open time
        "0.01634790",       // Open price
        "0.80000000",       // High price
        "0.01575800",       // Low price
        "0.01577100",       // Close price
        "148976.11427815",  // Volume
        1499644799999,      // Kline Close time
        "2434.19055334",    // Quote asset volume
        308,                // Number of trades
        "1756.87402397",    // Taker buy base asset volume
        "28.46694368",      // Taker buy quote asset volume
        "0"                 // Unused field, ignore.
    ]
    """

    open_time: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time: int
    asset_volume: str
    trades_count: int
    taker_base_volume: str
    taker_quote_volume: str
    ignore: str


class BinanceIndexResponseKline(msgspec.Struct, array_like=True):
    """
    1591256400000,      	// Open time
    "9653.69440000",    	// Open
    "9653.69640000",     	// High
    "9651.38600000",     	// Low
    "9651.55200000",     	// Close (or latest price)
    "0	", 					// Ignore
    1591256459999,      	// Close time
    "0",    				// Ignore
    60,                		// Ignore
    "0",    				// Ignore
    "0",      				// Ignore
    "0" 					// Ignore
    """

    open_time: int
    open: str
    high: str
    low: str
    close: str
    ignore_1: str
    close_time: int
    ignore_2: str
    ignore_3: int
    ignore_4: str
    ignore_5: str
    ignore_6: str


class BinanceSpotOrderBookMsg(msgspec.Struct):
    """
    WebSocket message for 'Binance Spot/Margin' Partial Book Depth Streams.
    """

    stream: str
    data: "BinanceSpotOrderBookData"


class BinanceSpotOrderBookData(msgspec.Struct):
    """
    Websocket message 'inner struct' for 'Binance Spot/Margin Partial Book Depth
    Streams.'.
    """

    lastUpdateId: int
    bids: list["BinanceOrderBookDelta"]
    asks: list["BinanceOrderBookDelta"]


class BinanceOrderBookDelta(msgspec.Struct, array_like=True):
    """
    Schema of single ask/bid delta.
    """

    price: str
    size: str

    def parse_to_book_order_data(self) -> BookOrderData:
        return BookOrderData(
            price=float(self.price),
            size=float(self.size),
        )


class BinanceFuturesOrderBookMsg(msgspec.Struct, frozen=True):
    """
    WebSocket message from Binance Partial & Diff.

    Book Depth Streams.

    """

    stream: str
    data: "BinanceFuturesOrderBookData"


class BinanceFuturesOrderBookData(msgspec.Struct, frozen=True):
    """
    WebSocket message 'inner struct' for Binance Partial & Diff.

    Book Depth Streams.

    """

    e: str  # Event type
    E: int  # Event time
    s: str  # Symbol
    U: int  # First update ID in event
    u: int  # Final update ID in event
    b: list[BinanceOrderBookDelta]  # Bids to be updated
    a: list[BinanceOrderBookDelta]  # Asks to be updated

    T: int | None = None  # FUTURES only, transaction time
    pu: int | None = None  # FUTURES only, previous final update ID
    ps: str | None = None  # COIN-M FUTURES only, pair


class BinanceCancelAllOrdersResponse(msgspec.Struct, frozen=True):
    code: int
    msg: str


class BinanceFundingRateResponse(msgspec.Struct, frozen=True):
    symbol: str
    fundingRate: str
    fundingTime: int
    markPrice: str | None = None


class BinanceBatchOrderResponse(msgspec.Struct, frozen=True, omit_defaults=True):
    clientOrderId: str | None = None
    cumQty: str | None = None
    executedQty: str | None = None
    orderId: int | None = None
    avgPrice: str | None = None
    origQty: str | None = None
    price: str | None = None
    reduceOnly: bool | None = None
    side: BinanceOrderSide | None = None
    positionSide: BinancePositionSide | None = None
    status: BinanceOrderStatus | None = None
    stopPrice: str | None = None
    closePosition: bool | None = None
    symbol: str | None = None
    timeInForce: BinanceTimeInForce | None = None
    type: BinanceOrderType | None = None
    origType: BinanceOrderType | None = None
    updateTime: int | None = None
    priceProtect: bool | None = None
    # USD-M specific fields
    cumQuote: str | None = None
    goodTillDate: int | None = None
    # Coin-M specific fields
    cumBase: str | None = None
    pair: str | None = None
    # Optional fields for both
    activatePrice: str | None = None
    priceRate: str | None = None
    workingType: BinanceFuturesWorkingType | None = None
    priceMatch: BinancePriceMatch | None = None
    selfTradePreventionMode: str | None = None
    code: int | None = None
    msg: str | None = None

import msgspec
from decimal import Decimal
from typing import Optional
from typing import Any, List
from nexustrader.schema import BaseMarket, Balance
from nexustrader.exchange.bitget.constants import (
    BitgetInstType,
    BitgetUtaInstType,
    BitgetOrderSide,
    BitgetOrderStatus,
    BitgetTimeInForce,
    BitgetPositionSide,
    BitgetOrderType,
)


class BitgetWsUtaArgMsg(msgspec.Struct):
    instType: BitgetUtaInstType
    topic: str
    symbol: str | None = None
    interval: str | None = None

    @property
    def message(self) -> str:
        if not self.symbol:
            return f"{self.instType.value}.{self.topic}"
        if self.interval:
            return f"{self.instType.value}.{self.topic}{self.interval}.{self.symbol}"
        return f"{self.instType.value}.{self.topic}.{self.symbol}"


class BitgetWsUtaGeneralMsg(msgspec.Struct, kw_only=True):
    event: str | None = None
    arg: BitgetWsUtaArgMsg | None = None
    code: int | None = None
    msg: str | None = None

    @property
    def is_event_data(self) -> bool:
        return self.event is not None


class BitgetGeneralResponse(msgspec.Struct, kw_only=True):
    code: str
    msg: str


class BitgetWsArgMsg(msgspec.Struct):
    instType: BitgetInstType
    channel: str
    instId: str | None = None
    coin: str | None = None

    @property
    def message(self) -> str:
        if self.instId:
            return f"{self.instType.value}.{self.channel}.{self.instId}"
        if self.coin:
            return f"{self.instType.value}.{self.channel}.{self.coin}"
        return f"{self.instType.value}.{self.channel}"


class BitgetWsGeneralMsg(msgspec.Struct, kw_only=True):
    event: str | None = None
    arg: BitgetWsArgMsg | None = None
    code: int | None = None
    msg: str | None = None

    @property
    def is_event_data(self) -> bool:
        return self.event is not None


class BookData(msgspec.Struct, array_like=True):
    px: str
    sz: str


class BitgetBooks1WsMsgData(msgspec.Struct):
    a: List[BookData]
    b: List[BookData]
    ts: str


class BitgetBooks1WsMsg(msgspec.Struct):
    data: list[BitgetBooks1WsMsgData]


class BitgetTradeWsMsgData(msgspec.Struct):
    p: str  # fill price
    S: str  # fill side
    T: str  # ts
    v: str  # fill size
    i: str  # trade id


class BitgetWsTradeWsMsg(msgspec.Struct):
    data: list[BitgetTradeWsMsgData]


class BitgetWsCandleWsMsgData(msgspec.Struct):
    start: str
    open: str
    close: str
    high: str
    low: str
    volume: str
    turnover: str


class BitgetWsCandleWsMsg(msgspec.Struct):
    data: list[BitgetWsCandleWsMsgData]


# # --- Kline ---
# class BitgetKline(msgspec.Struct):
#     openTime: int
#     open: str
#     high: str
#     low: str
#     close: str
#     volume: str
#     quoteVolume: str
#     closeTime: int

# class BitgetKlineMsg(msgspec.Struct):
#     event: str
#     arg: Dict[str, Any]
#     data: List[BitgetKline]


# # --- Trade ---
# class BitgetTrade(msgspec.Struct):
#     tradeId: str
#     price: str
#     size: str
#     side: str
#     timestamp: int

# class BitgetTradeMsg(msgspec.Struct):
#     event: str
#     arg: Dict[str, Any]
#     data: List[BitgetTrade]

# # --- Order Book ---
# class BitgetOrderBookSnapshot(msgspec.Struct):
#     asks: List[List[str]]
#     bids: List[List[str]]
#     ts: int
#     checksum: int

# class BitgetOrderBookUpdate(msgspec.Struct):
#     asks: List[List[str]]
#     bids: List[List[str]]
#     ts: int
#     checksum: int

# class BitgetOrderBookMsg(msgspec.Struct):
#     event: str
#     arg: Dict[str, Any]
#     action: str  # snapshot or update
#     data: List[BitgetOrderBookSnapshot | BitgetOrderBookUpdate]

# class BitgetOrderBook(msgspec.Struct):
#     bids: Dict[float, float] = {}
#     asks: Dict[float, float] = {}

#     def parse_orderbook(self, msg: BitgetOrderBookMsg, levels: int = 1):
#         for entry in msg.data:
#             if msg.action == "snapshot":
#                 self._handle_snapshot(entry)
#             elif msg.action == "update":
#                 self._handle_delta(entry)
#         return self._get_orderbook(levels)

#     def _handle_snapshot(self, data: BitgetOrderBookSnapshot):
#         self.bids.clear()
#         self.asks.clear()
#         for price, size in data.bids:
#             self.bids[float(price)] = float(size)
#         for price, size in data.asks:
#             self.asks[float(price)] = float(size)

#     def _handle_delta(self, data: BitgetOrderBookUpdate):
#         for price, size in data.bids:
#             price_f = float(price)
#             size_f = float(size)
#             if size_f == 0:
#                 self.bids.pop(price_f, None)
#             else:
#                 self.bids[price_f] = size_f
#         for price, size in data.asks:
#             price_f = float(price)
#             size_f = float(size)
#             if size_f == 0:
#                 self.asks.pop(price_f, None)
#             else:
#                 self.asks[price_f] = size_f

#     def _get_orderbook(self, levels: int):
#         bids = sorted(self.bids.items(), reverse=True)[:levels]
#         asks = sorted(self.asks.items())[:levels]
#         return {
#             "bids": [BookOrderData(price=price, size=size) for price, size in bids],
#             "asks": [BookOrderData(price=price, size=size) for price, size in asks],
#         }

# # --- Ticker ---
# class BitgetTicker(msgspec.Struct):
#     symbol: str
#     markPrice: str | None = None
#     indexPrice: str | None = None
#     nextFundingTime: str | None = None
#     fundingRate: str | None = None

# class BitgetTickerMsg(msgspec.Struct):
#     event: str
#     arg: Dict[str, Any]
#     data: List[Dict[str, Any]]

# # --- Balance ---
# class BitgetBalanceCoin(msgspec.Struct):
#     coin: str
#     available: str
#     frozen: str

#     def parse_to_balance(self) -> Balance:
#         locked = Decimal(self.frozen)
#         free = Decimal(self.available)
#         return Balance(asset=self.coin, locked=locked, free=free)

# class BitgetBalanceResponse(msgspec.Struct):
#     code: str
#     msg: str
#     data: List[BitgetBalanceCoin]

#     def parse_to_balances(self) -> List[Balance]:
#         return [coin.parse_to_balance() for coin in self.data]


# # --- Market Info ---
class BitgetMarketInfo(msgspec.Struct, kw_only=True, omit_defaults=True):
    # Common required fields
    symbol: str
    baseCoin: str
    quoteCoin: str
    makerFeeRate: str
    takerFeeRate: str
    minTradeUSDT: str

    # Spot-only optional fields
    minTradeAmount: Optional[str] = None
    maxTradeAmount: Optional[str] = None
    pricePrecision: Optional[str] = None
    quantityPrecision: Optional[str] = None
    quotePrecision: Optional[str] = None
    status: Optional[str] = None
    buyLimitPriceRatio: Optional[str] = None
    sellLimitPriceRatio: Optional[str] = None
    areaSymbol: Optional[str] = None
    orderQuantity: Optional[str] = None
    openTime: Optional[str] = None
    offTime: Optional[str] = None

    # Futures-only optional fields
    feeRateUpRatio: Optional[str] = None
    openCostUpRatio: Optional[str] = None
    supportMarginCoins: Optional[List[str]] = None
    minTradeNum: Optional[str] = None
    priceEndStep: Optional[str] = None
    volumePlace: Optional[str] = None
    pricePlace: Optional[str] = None
    sizeMultiplier: Optional[str] = None
    symbolType: Optional[str] = None
    maxSymbolOrderNum: Optional[str] = None
    maxProductOrderNum: Optional[str] = None
    maxPositionNum: Optional[str] = None
    symbolStatus: Optional[str] = None
    limitOpenTime: Optional[str] = None
    deliveryTime: Optional[str] = None
    deliveryStartTime: Optional[str] = None
    launchTime: Optional[str] = None
    fundInterval: Optional[str] = None
    minLever: Optional[str] = None
    maxLever: Optional[str] = None
    posLimit: Optional[str] = None
    maintainTime: Optional[str] = None
    maxMarketOrderQty: Optional[str] = None
    maxOrderQty: Optional[str] = None


class BitgetMarket(BaseMarket):
    info: BitgetMarketInfo


class BitgetOrderCancelData(msgspec.Struct):
    orderId: str
    clientOid: str


class BitgetOrderCancelResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: BitgetOrderCancelData


class BitgetOrderPlaceData(msgspec.Struct, kw_only=True):
    orderId: str
    clientOid: str | None = None


class BitgetOrderPlaceResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: BitgetOrderPlaceData


class BitgetPositionItem(msgspec.Struct):
    symbol: str
    marginCoin: str
    holdSide: BitgetPositionSide
    openDelegateSize: str
    marginSize: str
    available: str
    locked: str
    total: str
    leverage: str
    openPriceAvg: str
    marginMode: str
    posMode: str
    unrealizedPL: str
    liquidationPrice: str
    markPrice: str
    breakEvenPrice: str
    achievedProfits: str | None = None
    keepMarginRate: str | None = None
    totalFee: str | None = None
    deductedFee: str | None = None
    marginRatio: str | None = None
    assetMode: str | None = None
    uTime: str | None = None
    autoMargin: str | None = None
    cTime: str | None = None


class BitgetPositionListResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: list[BitgetPositionItem]


class BitgetOrder(msgspec.Struct, kw_only=True):
    orderId: str
    clientOid: Optional[str]
    symbol: str
    baseCoin: str
    quoteCoin: str
    size: Decimal
    price: Decimal
    state: str
    orderType: str
    side: str
    timeInForceValue: Optional[str] = None
    force: Optional[str] = None
    priceAvg: Optional[Decimal] = None
    fillPrice: Optional[Decimal] = None
    filledQty: Optional[Decimal] = None
    fee: Optional[Decimal] = None
    orderSource: Optional[str] = None
    cTime: Optional[int] = None
    uTime: Optional[int] = None
    status: Optional[str] = None


class BitgetOpenOrdersResponse(msgspec.Struct, kw_only=True):
    code: str
    msg: Optional[str]
    requestTime: int
    data: List[BitgetOrder]


class BitgetOrderHistoryItem(msgspec.Struct, kw_only=True, omit_defaults=True):
    orderId: str
    symbol: str
    price: str
    size: str
    orderType: str
    side: str
    status: str
    createTime: int
    baseCoin: Optional[str] = None
    quoteCoin: Optional[str] = None
    clientOid: Optional[str] = None
    priceAvg: Optional[str] = None
    filledAmount: Optional[str] = None
    enterPointSource: Optional[str] = None
    tradeSide: Optional[str] = None
    forceClose: Optional[bool] = None
    marginMode: Optional[str] = None
    reduceOnly: Optional[bool] = None
    presetStopSurplusPrice: Optional[str] = None
    presetStopLossPrice: Optional[str] = None
    feeDetail: Optional[str] = None
    tradeId: Optional[str] = None


class BitgetOrderHistoryResponse(msgspec.Struct, kw_only=True, omit_defaults=True):
    code: str
    msg: str
    requestTime: int
    data: List[BitgetOrderHistoryItem]


class BitgetAccountAssetItem(msgspec.Struct):
    coin: str
    available: str
    frozen: str
    locked: str
    limitAvailable: str
    uTime: str


class BitgetAccountAssetResponse(msgspec.Struct):
    code: str
    message: str
    requestTime: int
    data: List[BitgetAccountAssetItem]


class BitgetOrderModifyResponse(msgspec.Struct, kw_only=True):
    orderId: str
    clientOid: str


class BitgetResponse(msgspec.Struct, kw_only=True):
    code: str
    msg: str
    data: BitgetOrderModifyResponse
    requestTime: int


class BitgetBaseResponse(msgspec.Struct, kw_only=True):
    code: str
    msg: str
    requestTime: int
    data: Any


class BitgetKlineItem(msgspec.Struct):
    timestamp: str  # index[0]
    open: str  # index[1]
    high: str  # index[2]
    low: str  # index[3]
    close: str  # index[4]
    volume_base: str  # index[5]
    volume_quote: str  # index[6]


class BitgetKlineResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: List[List[str]]


class BitgetIndexPriceKlineItem(msgspec.Struct):
    timestamp: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    base_volume: str
    quote_volume: str


class BitgetIndexPriceKlineResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: List[BitgetIndexPriceKlineItem]


class BitgetOrderFeeDetail(msgspec.Struct):
    feeCoin: str
    fee: str


class BitgetOrderData(msgspec.Struct, kw_only=True):
    # Common required fields (present in both spot and futures)
    instId: str
    orderId: str
    clientOid: str
    size: str
    orderType: BitgetOrderType
    force: BitgetTimeInForce
    side: BitgetOrderSide

    tradeId: Optional[str] = None
    fillTime: Optional[str] = None
    fillFee: Optional[str] = None
    fillFeeCoin: Optional[str] = None
    tradeScope: Optional[str] = None
    priceAvg: Optional[str] = None
    status: BitgetOrderStatus
    cTime: str
    uTime: str
    stpMode: str
    feeDetail: List[BitgetOrderFeeDetail]
    enterPointSource: str

    # Optional fields (may be present in spot, futures, or both)
    fillPrice: Optional[str] = None
    newSize: Optional[str] = None
    notional: Optional[str] = None
    baseVolume: Optional[str] = None
    accBaseVolume: Optional[str] = None

    # Futures-specific optional fields
    fillNotionalUsd: Optional[str] = None
    leverage: Optional[str] = None
    marginCoin: Optional[str] = None
    marginMode: Optional[str] = None
    notionalUsd: Optional[str] = None
    pnl: Optional[str] = None
    posMode: Optional[str] = None
    posSide: Optional[BitgetPositionSide] = None
    price: Optional[str] = None
    reduceOnly: Optional[str] = None
    tradeSide: Optional[str] = None
    presetStopSurplusPrice: Optional[str] = None
    totalProfits: Optional[str] = None
    presetStopLossPrice: Optional[str] = None
    cancelReason: Optional[str] = None


class BitgetOrderWsMsg(msgspec.Struct):
    action: str
    arg: BitgetWsArgMsg
    data: List[BitgetOrderData]
    ts: int


class BitgetPositionData(msgspec.Struct):
    posId: str
    instId: str
    marginCoin: str
    marginSize: str
    marginMode: str
    holdSide: BitgetPositionSide
    posMode: str
    total: str
    available: str
    frozen: str
    openPriceAvg: str
    leverage: int
    achievedProfits: str
    unrealizedPL: str
    unrealizedPLR: str
    liquidationPrice: str
    keepMarginRate: str
    marginRate: str
    cTime: str
    breakEvenPrice: str
    totalFee: str
    deductedFee: str
    markPrice: str
    uTime: str
    autoMargin: str


class BitgetPositionWsMsg(msgspec.Struct):
    action: str
    arg: BitgetWsArgMsg
    data: List[BitgetPositionData]
    ts: int


class BitgetSpotAccountData(msgspec.Struct):
    coin: str
    available: str
    frozen: str
    locked: str
    limitAvailable: str
    uTime: str

    def parse_to_balance(self) -> Balance:
        locked = Decimal(self.frozen) + Decimal(self.locked)
        free = Decimal(self.available)
        return Balance(asset=self.coin, locked=locked, free=free)


class BitgetSpotAccountWsMsg(msgspec.Struct):
    data: List[BitgetSpotAccountData]
    ts: int

    def parse_to_balances(self) -> List[Balance]:
        return [account_data.parse_to_balance() for account_data in self.data]


class BitgetFuturesAccountData(msgspec.Struct):
    marginCoin: str
    frozen: str
    available: str
    maxOpenPosAvailable: str
    maxTransferOut: str
    equity: str
    usdtEquity: str
    crossedRiskRate: str
    unrealizedPL: str

    def parse_to_balance(self) -> Balance:
        locked = Decimal(self.frozen)
        free = Decimal(self.available)
        return Balance(asset=self.marginCoin, locked=locked, free=free)


class BitgetFuturesAccountWsMsg(msgspec.Struct):
    data: List[BitgetFuturesAccountData]
    ts: int

    def parse_to_balances(self) -> List[Balance]:
        return [account_data.parse_to_balance() for account_data in self.data]


class BitgetUtaCoinData(msgspec.Struct):
    debts: str
    balance: str
    available: str
    borrow: str
    locked: str
    equity: str
    coin: str
    usdValue: str

    def parse_to_balance(self) -> Balance:
        locked = Decimal(self.locked)
        free = Decimal(self.available)
        return Balance(asset=self.coin, locked=locked, free=free)


class BitgetUtaAccountData(msgspec.Struct):
    unrealisedPnL: str
    totalEquity: str
    positionMgnRatio: str
    mmr: str
    effEquity: str
    imr: str
    mgnRatio: str
    coin: List[BitgetUtaCoinData]

    def parse_to_balances(self) -> List[Balance]:
        return [coin_data.parse_to_balance() for coin_data in self.coin]


class BitgetUtaAccountWsMsg(msgspec.Struct):
    data: List[BitgetUtaAccountData]
    ts: int

    def parse_to_balances(self) -> List[Balance]:
        balances = []
        for account_data in self.data:
            balances.extend(account_data.parse_to_balances())
        return balances


class BitgetUtaOrderFeeDetail(msgspec.Struct):
    feeCoin: str
    fee: str


class BitgetUtaOrderData(msgspec.Struct, kw_only=True):
    category: BitgetUtaInstType
    symbol: str
    orderId: str
    clientOid: str
    price: str
    qty: str
    holdMode: str
    holdSide: str
    tradeSide: str
    orderType: BitgetOrderType
    timeInForce: BitgetTimeInForce
    side: BitgetOrderSide
    marginMode: str
    marginCoin: str
    reduceOnly: str
    cumExecQty: str
    cumExecValue: str
    avgPrice: str
    totalProfit: str
    orderStatus: BitgetOrderStatus
    cancelReason: str
    leverage: str
    feeDetail: List[BitgetUtaOrderFeeDetail]
    createdTime: str
    updatedTime: str
    stpMode: str


class BitgetUtaOrderWsMsg(msgspec.Struct):
    data: List[BitgetUtaOrderData]
    ts: int


class BitgetUtaPositionData(msgspec.Struct, kw_only=True):
    symbol: str
    leverage: str
    openFeeTotal: str
    mmr: str
    breakEvenPrice: str
    available: str
    liqPrice: str
    marginMode: str
    unrealisedPnl: str
    markPrice: str
    createdTime: str
    openPriceAvg: str | None = None
    totalFundingFee: str
    updatedTime: str
    marginCoin: str
    frozen: str
    profitRate: str
    closeFeeTotal: str
    marginSize: str
    curRealisedPnl: str
    size: str
    posSide: BitgetPositionSide
    holdMode: str


class BitgetUtaPositionWsMsg(msgspec.Struct):
    data: List[BitgetUtaPositionData]
    ts: int


class BitgetWsApiArgParamsMsg(msgspec.Struct):
    orderId: str | None = None
    clientOid: str | None = None


class BitgetWsApiArgMsg(msgspec.Struct):
    id: str
    instType: str
    channel: str
    instId: str
    params: BitgetWsApiArgParamsMsg

    @property
    def is_place_order(self):
        return self.channel == "place-order"

    @property
    def is_cancel_order(self):
        return self.channel == "cancel-order"


class BitgetWsApiGeneralMsg(msgspec.Struct):
    event: str
    code: int | str
    arg: list[BitgetWsApiArgMsg] | None = None
    msg: str | None = None

    @property
    def is_success(self):
        return int(self.code) == 0

    @property
    def is_login_msg(self):
        return self.event == "login"

    @property
    def is_arg_msg(self):
        return self.arg is not None

    @property
    def is_error_msg(self):
        return int(self.code) != 0

    @property
    def error_msg(self):
        return f"code={self.code} msg={self.msg}"


class BitgetWsApiUtaArgMsg(msgspec.Struct, kw_only=True):
    orderId: str
    clientOid: str


class BitgetWsApiUtaGeneralMsg(msgspec.Struct, kw_only=True):
    event: str
    id: str | None = None
    code: str | int
    args: list[BitgetWsApiUtaArgMsg] | None = None
    msg: str | None = None

    @property
    def oid(self):
        if not self.id:
            raise ValueError("id is None")
        return self.id[1:]

    @property
    def is_cancel_order(self):
        self.id.startswith("c")

    @property
    def is_place_order(self):
        self.id.startswith("n")

    @property
    def is_success(self):
        return int(self.code) == 0

    @property
    def is_id_msg(self):
        return self.id is not None

    @property
    def is_error_msg(self):
        return int(self.code) != 0

    @property
    def error_msg(self):
        return f"code={self.code} msg={self.msg}"


class BitgetTickerResponseData(msgspec.Struct):
    category: BitgetInstType
    symbol: str
    lastPrice: str
    volume24h: str
    turnover24h: str


class BitgetTickerResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: List[BitgetTickerResponseData]


class BitgetV3PositionData(msgspec.Struct, kw_only=True):
    category: str
    symbol: str
    marginCoin: str
    holdMode: str
    posSide: str
    marginMode: str
    positionBalance: str
    available: str
    frozen: str
    total: str
    leverage: str
    curRealisedPnl: str
    avgPrice: str
    positionStatus: str
    unrealisedPnl: str
    liquidationPrice: str
    mmr: str
    profitRate: str
    markPrice: str
    breakEvenPrice: str
    totalFunding: str
    openFeeTotal: str
    closeFeeTotal: str
    createdTime: str
    updatedTime: str


class BitgetV3PositionResponseData(msgspec.Struct):
    list: List[BitgetV3PositionData] | None = None


class BitgetV3PositionResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: int
    data: BitgetV3PositionResponseData

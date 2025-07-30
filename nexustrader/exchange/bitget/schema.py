import msgspec
from decimal import Decimal
from typing import Final, Dict, Any, List, Generic, TypeVar
from nexustrader.schema import BaseMarket, Balance, BookOrderData
from typing import Optional
from typing import Literal




# --- Constants ---
BITGET_PONG: Final[str] = "pong"

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
    orderId: Optional[str] = None
    clientOid: Optional[str] = None

class BitgetOrderCancelResponse(msgspec.Struct):
    code: str
    msg: str
    requestTime: Optional[int] = None
    data: Optional[BitgetOrderCancelData] = None

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
    holdSide: str
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
    open: str        # index[1]
    high: str        # index[2]
    low: str         # index[3]
    close: str       # index[4]
    volume_base: str # index[5]
    volume_quote: str# index[6]

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

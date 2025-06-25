import asyncio
import msgspec
import sys
from typing import Dict, Any, List
from decimal import Decimal
from nexustrader.error import PositionModeError
from nexustrader.base import PublicConnector, PrivateConnector
from nexustrader.constants import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
    KlineInterval,
    TriggerType,
    BookLevel,
)
from nexustrader.schema import (
    BookL1,
    Trade,
    Kline,
    MarkPrice,
    FundingRate,
    IndexPrice,
    BookL2,
    Order,
    Position,
    KlineList,
    BatchOrderSubmit,
)
from nexustrader.exchange.binance.schema import BinanceMarket
from nexustrader.exchange.binance.rest_api import BinanceApiClient
from nexustrader.exchange.binance.constants import BinanceAccountType
from nexustrader.exchange.binance.websockets import BinanceWSClient
from nexustrader.exchange.binance.exchange import BinanceExchangeManager
from nexustrader.exchange.binance.constants import (
    BinanceWsEventType,
    BinanceUserDataStreamWsEventType,
    BinanceBusinessUnit,
    BinanceEnumParser,
)
from nexustrader.exchange.binance.schema import (
    BinanceResponseKline,
    BinanceIndexResponseKline,
    BinanceWsMessageGeneral,
    BinanceTradeData,
    BinanceSpotBookTicker,
    BinanceFuturesBookTicker,
    BinanceKline,
    BinanceMarkPrice,
    BinanceUserDataStreamMsg,
    BinanceSpotOrderUpdateMsg,
    BinanceFuturesOrderUpdateMsg,
    BinanceSpotAccountInfo,
    BinanceFuturesAccountInfo,
    BinanceSpotUpdateMsg,
    BinanceFuturesUpdateMsg,
    BinanceResultId,
    BinanceSpotOrderBookMsg,
    BinanceFuturesOrderBookMsg,
    BinancePortfolioMarginBalance,
    BinancePortfolioMarginPositionRisk,
    BinanceFuturesPositionInfo,
)
from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import MessageBus
from nexustrader.core.entity import TaskManager


class BinancePublicConnector(PublicConnector):
    _ws_client: BinanceWSClient
    _account_type: BinanceAccountType
    _market: Dict[str, BinanceMarket]
    _market_id: Dict[str, str]
    _api_client: BinanceApiClient

    def __init__(
        self,
        account_type: BinanceAccountType,
        exchange: BinanceExchangeManager,
        msgbus: MessageBus,
        task_manager: TaskManager,
        custom_url: str | None = None,
        enable_rate_limit: bool = True,
    ):
        if not account_type.is_spot and not account_type.is_future:
            raise ValueError(
                f"BinanceAccountType.{account_type.value} is not supported for Binance Public Connector"
            )

        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BinanceWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
                custom_url=custom_url,
                ws_suffix="/stream",
            ),
            msgbus=msgbus,
            api_client=BinanceApiClient(
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            task_manager=task_manager,
        )
        self._ws_general_decoder = msgspec.json.Decoder(BinanceWsMessageGeneral)
        self._ws_trade_decoder = msgspec.json.Decoder(BinanceTradeData)
        self._ws_spot_book_ticker_decoder = msgspec.json.Decoder(BinanceSpotBookTicker)
        self._ws_futures_book_ticker_decoder = msgspec.json.Decoder(
            BinanceFuturesBookTicker
        )
        self._ws_kline_decoder = msgspec.json.Decoder(BinanceKline)
        self._ws_mark_price_decoder = msgspec.json.Decoder(BinanceMarkPrice)
        self._ws_result_id_decoder = msgspec.json.Decoder(BinanceResultId)

        self._ws_spot_depth_decoder = msgspec.json.Decoder(BinanceSpotOrderBookMsg)
        self._ws_futures_depth_decoder = msgspec.json.Decoder(
            BinanceFuturesOrderBookMsg
        )

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"
        else:
            raise ValueError(
                f"Unsupported BinanceAccountType.{self._account_type.value}"
            )

    def request_index_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        bnc_interval = BinanceEnumParser.to_binance_kline_interval(interval)

        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        if market.linear:
            query_klines = self._api_client.get_fapi_v1_index_price_klines
        elif market.inverse:
            query_klines = self._api_client.get_dapi_v1_index_price_klines
        else:
            raise ValueError(f"Unsupported {market.type} market")

        end_time_ms = int(end_time) if end_time is not None else sys.maxsize
        limit = int(limit) if limit is not None else 500
        all_klines: list[Kline] = []
        while True:
            klines_response: list[BinanceIndexResponseKline] = query_klines(
                pair=market.id,
                interval=bnc_interval.value,
                limit=limit,
                startTime=start_time,
                endTime=end_time,
            )
            klines: list[Kline] = [
                self._parse_index_kline_response(
                    symbol=symbol, interval=interval, kline=kline
                )
                for kline in klines_response
            ]
            all_klines.extend(klines)

            # Update the start_time to fetch the next set of bars
            if klines:
                next_start_time = klines[-1].start + 1
            else:
                # Handle the case when klines is empty
                break

            # No more bars to fetch
            if (limit and len(klines) < limit) or next_start_time >= end_time_ms:
                break

            start_time = next_start_time

        kline_list = KlineList(
            all_klines,
            fields=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "confirm",
            ],
        )
        return kline_list

    def request_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> KlineList:
        bnc_interval = BinanceEnumParser.to_binance_kline_interval(interval)

        market = self._market.get(symbol)
        if market is None:
            raise ValueError(f"Symbol {symbol} not found")

        if market.spot:
            query_klines = self._api_client.get_api_v3_klines
        elif market.linear:
            query_klines = self._api_client.get_fapi_v1_klines
        elif market.inverse:
            query_klines = self._api_client.get_dapi_v1_klines
        else:
            raise ValueError(f"Unsupported {market.type} market")

        end_time_ms = int(end_time) if end_time is not None else sys.maxsize
        limit = int(limit) if limit is not None else 500
        all_klines: list[Kline] = []
        while True:
            klines_response: list[BinanceResponseKline] = query_klines(
                symbol=market.id,
                interval=bnc_interval.value,
                limit=limit,
                startTime=start_time,
                endTime=end_time,
            )
            klines: list[Kline] = [
                self._parse_kline_response(
                    symbol=symbol, interval=interval, kline=kline
                )
                for kline in klines_response
            ]
            all_klines.extend(klines)

            # Update the start_time to fetch the next set of bars
            if klines:
                next_start_time = klines[-1].start + 1
            else:
                # Handle the case when klines is empty
                break

            # No more bars to fetch
            if (limit and len(klines) < limit) or next_start_time >= end_time_ms:
                break

            start_time = next_start_time

        kline_list = KlineList(
            all_klines,
            fields=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "taker_volume",
                "taker_quote_volume",
                "confirm",
            ],
        )
        return kline_list

    async def subscribe_funding_rate(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(
            symbols
        )  # NOTE: funding rate is in mark price

    async def subscribe_index_price(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(
            symbols
        )  # NOTE: index price is in mark price

    async def subscribe_mark_price(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_mark_price(symbols)

    async def subscribe_trade(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_trade(symbols)

    async def subscribe_bookl1(self, symbol: str | List[str]):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)
        await self._ws_client.subscribe_book_ticker(symbols)

    async def subscribe_bookl2(self, symbol: str | List[str], level: BookLevel):
        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)
        await self._ws_client.subscribe_partial_book_depth(symbols, int(level.value))

    async def subscribe_kline(self, symbol: str | List[str], interval: KlineInterval):
        interval = BinanceEnumParser.to_binance_kline_interval(interval)

        symbols = []
        if isinstance(symbol, str):
            symbol = [symbol]

        for s in symbol:
            market = self._market.get(s)
            if market is None:
                raise ValueError(f"Symbol {s} not found")
            symbols.append(market.id)

        await self._ws_client.subscribe_kline(symbols, interval)

    def _ws_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_general_decoder.decode(raw)
            if msg.data.e:
                match msg.data.e:
                    case BinanceWsEventType.TRADE:
                        self._parse_trade(raw)
                    case BinanceWsEventType.BOOK_TICKER:
                        self._parse_futures_book_ticker(raw)
                    case BinanceWsEventType.KLINE:
                        self._parse_kline(raw)
                    case BinanceWsEventType.MARK_PRICE_UPDATE:
                        self._parse_mark_price(raw)
                    case BinanceWsEventType.DEPTH_UPDATE:
                        self._parse_futures_depth(raw)

            elif msg.data.u:
                # NOTE: spot book ticker doesn't have "e" key. FUCK BINANCE
                self._parse_spot_book_ticker(raw)
            else:
                # NOTE: spot partial depth doesn't have "e" and "u" keys
                self._parse_spot_depth(raw)
        except msgspec.DecodeError as e:
            res = self._ws_result_id_decoder.decode(raw)
            if res.id:
                return
            self._log.error(f"Error decoding message: {str(raw)} {str(e)}")

    def _parse_spot_depth(self, raw: bytes):
        res = self._ws_spot_depth_decoder.decode(raw)
        stream = res.stream
        id = stream.split("@")[0].upper() + self.market_type
        symbol = self._market_id[id]
        depth = res.data
        bids = [b.parse_to_book_order_data() for b in depth.bids]
        asks = [a.parse_to_book_order_data() for a in depth.asks]
        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_futures_depth(self, raw: bytes):
        res = self._ws_futures_depth_decoder.decode(raw)
        id = res.data.s + self.market_type
        symbol = self._market_id[id]
        depth = res.data
        bids = [b.parse_to_book_order_data() for b in depth.b]
        asks = [a.parse_to_book_order_data() for a in depth.a]
        bookl2 = BookL2(
            exchange=self._exchange_id,
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl2", msg=bookl2)

    def _parse_index_kline_response(
        self, symbol: str, interval: KlineInterval, kline: BinanceIndexResponseKline
    ) -> Kline:
        timestamp = self._clock.timestamp_ms()

        if kline.close_time > timestamp:
            confirm = False
        else:
            confirm = True

        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.open),
            high=float(kline.high),
            low=float(kline.low),
            close=float(kline.close),
            start=kline.open_time,
            timestamp=timestamp,
            confirm=confirm,
        )

    def _parse_kline_response(
        self, symbol: str, interval: KlineInterval, kline: BinanceResponseKline
    ) -> Kline:
        timestamp = self._clock.timestamp_ms()

        if kline.close_time > timestamp:
            confirm = False
        else:
            confirm = True

        return Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(kline.open),
            high=float(kline.high),
            low=float(kline.low),
            close=float(kline.close),
            volume=float(kline.volume),
            quote_volume=float(kline.asset_volume),
            taker_volume=float(kline.taker_base_volume),
            taker_quote_volume=float(kline.taker_quote_volume),
            start=kline.open_time,
            timestamp=timestamp,
            confirm=confirm,
        )

    def _parse_kline(self, raw: bytes) -> Kline:
        res = self._ws_kline_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]
        interval = BinanceEnumParser.parse_kline_interval(res.k.i)
        ticker = Kline(
            exchange=self._exchange_id,
            symbol=symbol,
            interval=interval,
            open=float(res.k.o),
            high=float(res.k.h),
            low=float(res.k.l),
            close=float(res.k.c),
            volume=float(res.k.v),
            quote_volume=float(res.k.q),
            taker_volume=float(res.k.V),
            taker_quote_volume=float(res.k.Q),
            start=res.k.t,
            timestamp=res.E,
            confirm=res.k.x,
        )
        self._msgbus.publish(topic="kline", msg=ticker)

    def _parse_trade(self, raw: bytes) -> Trade:
        res = self._ws_trade_decoder.decode(raw).data

        id = res.s + self.market_type
        symbol = self._market_id[id]  # map exchange id to ccxt symbol

        trade = Trade(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.p),
            size=float(res.q),
            timestamp=res.T,
        )
        self._msgbus.publish(topic="trade", msg=trade)

    def _parse_spot_book_ticker(self, raw: bytes) -> BookL1:
        res = self._ws_spot_book_ticker_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]

        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=float(res.b),
            ask=float(res.a),
            bid_size=float(res.B),
            ask_size=float(res.A),
            timestamp=self._clock.timestamp_ms(),
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _parse_futures_book_ticker(self, raw: bytes) -> BookL1:
        res = self._ws_futures_book_ticker_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]
        bookl1 = BookL1(
            exchange=self._exchange_id,
            symbol=symbol,
            bid=float(res.b),
            ask=float(res.a),
            bid_size=float(res.B),
            ask_size=float(res.A),
            timestamp=res.E,
        )
        self._msgbus.publish(topic="bookl1", msg=bookl1)

    def _parse_mark_price(self, raw: bytes):
        res = self._ws_mark_price_decoder.decode(raw).data
        id = res.s + self.market_type
        symbol = self._market_id[id]

        mark_price = MarkPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.p),
            timestamp=res.E,
        )

        funding_rate = FundingRate(
            exchange=self._exchange_id,
            symbol=symbol,
            rate=float(res.r),
            timestamp=res.E,
            next_funding_time=res.T,
        )

        index_price = IndexPrice(
            exchange=self._exchange_id,
            symbol=symbol,
            price=float(res.i),
            timestamp=res.E,
        )
        self._msgbus.publish(topic="funding_rate", msg=funding_rate)
        self._msgbus.publish(topic="mark_price", msg=mark_price)
        self._msgbus.publish(topic="index_price", msg=index_price)


class BinancePrivateConnector(PrivateConnector):
    _ws_client: BinanceWSClient
    _account_type: BinanceAccountType
    _market: Dict[str, BinanceMarket]
    _market_id: Dict[str, str]
    _api_client: BinanceApiClient

    def __init__(
        self,
        account_type: BinanceAccountType,
        exchange: BinanceExchangeManager,
        cache: AsyncCache,
        msgbus: MessageBus,
        task_manager: TaskManager,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            account_type=account_type,
            market=exchange.market,
            market_id=exchange.market_id,
            exchange_id=exchange.exchange_id,
            ws_client=BinanceWSClient(
                account_type=account_type,
                handler=self._ws_msg_handler,
                task_manager=task_manager,
            ),
            api_client=BinanceApiClient(
                api_key=exchange.api_key,
                secret=exchange.secret,
                testnet=account_type.is_testnet,
                enable_rate_limit=enable_rate_limit,
            ),
            cache=cache,
            msgbus=msgbus,
            task_manager=task_manager,
        )

        self._ws_msg_general_decoder = msgspec.json.Decoder(BinanceUserDataStreamMsg)
        self._ws_msg_spot_order_update_decoder = msgspec.json.Decoder(
            BinanceSpotOrderUpdateMsg
        )
        self._ws_msg_futures_order_update_decoder = msgspec.json.Decoder(
            BinanceFuturesOrderUpdateMsg
        )
        self._ws_msg_spot_account_update_decoder = msgspec.json.Decoder(
            BinanceSpotUpdateMsg
        )
        self._ws_msg_futures_account_update_decoder = msgspec.json.Decoder(
            BinanceFuturesUpdateMsg
        )

    def _apply_position(
        self,
        pos: BinanceFuturesPositionInfo | BinancePortfolioMarginPositionRisk,
        market_type: str | None = None,
    ):
        market_type = market_type or self.market_type
        id = pos.symbol + market_type
        symbol = self._market_id[id]
        side = pos.positionSide.parse_to_position_side()
        signed_amount = Decimal(pos.positionAmt)

        if signed_amount == 0:
            side = None
        else:
            if side == PositionSide.FLAT:
                if signed_amount > 0:
                    side = PositionSide.LONG
                elif signed_amount < 0:
                    side = PositionSide.SHORT

        if isinstance(pos, BinancePortfolioMarginPositionRisk):
            unrealized_pnl = float(pos.unRealizedProfit)
        elif isinstance(pos, BinanceFuturesPositionInfo):
            unrealized_pnl = float(pos.unrealizedProfit)

        position = Position(
            symbol=symbol,
            exchange=self._exchange_id,
            signed_amount=signed_amount,
            side=side,
            entry_price=float(pos.entryPrice),
            unrealized_pnl=unrealized_pnl,
        )
        if position.is_opened:
            self._cache._apply_position(position)

    async def _init_account_balance(self):
        if (
            self._account_type.is_spot
            or self._account_type.is_isolated_margin_or_margin
        ):
            res: BinanceSpotAccountInfo = await self._api_client.get_api_v3_account()
        elif self._account_type.is_linear:
            res: BinanceFuturesAccountInfo = (
                await self._api_client.get_fapi_v2_account()
            )
        elif self._account_type.is_inverse:
            res: BinanceFuturesAccountInfo = (
                await self._api_client.get_dapi_v1_account()
            )

        if self._account_type.is_portfolio_margin:
            balances = []
            res_pm: list[
                BinancePortfolioMarginBalance
            ] = await self._api_client.get_papi_v1_balance()
            for balance in res_pm:
                balances.append(balance.parse_to_balance())
        else:
            balances = res.parse_to_balances()

        self._cache._apply_balance(self._account_type, balances)

        if self._account_type.is_linear or self._account_type.is_inverse:
            for pos in res.positions:
                self._apply_position(pos)

    async def _init_position(self):
        # NOTE: Implement in `_init_account_balance`, only portfolio margin need to implement this
        if self._account_type.is_portfolio_margin:
            res_linear: list[
                BinancePortfolioMarginPositionRisk
            ] = await self._api_client.get_papi_v1_um_position_risk()
            res_inverse: list[
                BinancePortfolioMarginPositionRisk
            ] = await self._api_client.get_papi_v1_cm_position_risk()

            for pos in res_linear:
                self._apply_position(pos, market_type="_linear")
            for pos in res_inverse:
                self._apply_position(pos, market_type="_inverse")

    async def _position_mode_check(self):
        error_msg = "Please Set Position Mode to `One-Way Mode` in Binance App"

        if self._account_type.is_linear:
            res = await self._api_client.get_fapi_v1_positionSide_dual()
            if res["dualSidePosition"]:
                raise PositionModeError(error_msg)

        elif self._account_type.is_inverse:
            res = await self._api_client.get_dapi_v1_positionSide_dual()
            if res["dualSidePosition"]:
                raise PositionModeError(error_msg)

        elif self._account_type.is_portfolio_margin:
            for res in await asyncio.gather(
                self._api_client.get_papi_v1_um_positionSide_dual(),
                self._api_client.get_papi_v1_cm_positionSide_dual(),
            ):
                if res["dualSidePosition"]:
                    raise PositionModeError(error_msg)

    @property
    def market_type(self):
        if self._account_type.is_spot:
            return "_spot"
        elif self._account_type.is_linear:
            return "_linear"
        elif self._account_type.is_inverse:
            return "_inverse"

    async def _start_user_data_stream(self):
        if self._account_type.is_spot:
            res = await self._api_client.post_api_v3_user_data_stream()
        elif self._account_type.is_margin:
            res = await self._api_client.post_sapi_v1_user_data_stream()
        elif self._account_type.is_linear:
            res = await self._api_client.post_fapi_v1_listen_key()
        elif self._account_type.is_inverse:
            res = await self._api_client.post_dapi_v1_listen_key()
        elif self._account_type.is_portfolio_margin:
            res = await self._api_client.post_papi_v1_listen_key()
        return res.listenKey

    async def _keep_alive_listen_key(self, listen_key: str):
        if self._account_type.is_spot:
            await self._api_client.put_api_v3_user_data_stream(listen_key=listen_key)
        elif self._account_type.is_margin:
            await self._api_client.put_sapi_v1_user_data_stream(listen_key=listen_key)
        elif self._account_type.is_linear:
            await self._api_client.put_fapi_v1_listen_key()
        elif self._account_type.is_inverse:
            await self._api_client.put_dapi_v1_listen_key()
        elif self._account_type.is_portfolio_margin:
            await self._api_client.put_papi_v1_listen_key()

    async def _keep_alive_user_data_stream(
        self, listen_key: str, interval: int = 20, max_retry: int = 5
    ):
        retry_count = 0
        while retry_count < max_retry:
            await asyncio.sleep(60 * interval)
            try:
                await self._keep_alive_listen_key(listen_key)
                retry_count = 0  # Reset retry count on successful keep-alive
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self._log.error(f"Failed to keep alive listen key: {error_msg}")
                retry_count += 1
                if retry_count < max_retry:
                    await asyncio.sleep(5)
                else:
                    self._log.error(
                        f"Max retries ({max_retry}) reached. Stopping keep-alive attempts."
                    )
                    break

    async def connect(self):
        await super().connect()
        listen_key = await self._start_user_data_stream()

        if listen_key:
            self._task_manager.create_task(
                self._keep_alive_user_data_stream(listen_key)
            )
            await self._ws_client.subscribe_user_data_stream(listen_key)
        else:
            raise RuntimeError("Failed to start user data stream")

    def _ws_msg_handler(self, raw: bytes):
        try:
            msg = self._ws_msg_general_decoder.decode(raw)
            if msg.e:
                match msg.e:
                    case (
                        BinanceUserDataStreamWsEventType.ORDER_TRADE_UPDATE
                    ):  # futures order update
                        self._parse_order_trade_update(raw)
                    case (
                        BinanceUserDataStreamWsEventType.EXECUTION_REPORT
                    ):  # spot order update
                        self._parse_execution_report(raw)
                    case (
                        BinanceUserDataStreamWsEventType.ACCOUNT_UPDATE
                    ):  # futures account update
                        self._parse_account_update(raw)
                    case (
                        BinanceUserDataStreamWsEventType.OUT_BOUND_ACCOUNT_POSITION
                    ):  # spot account update
                        self._parse_out_bound_account_position(raw)
        except msgspec.DecodeError as e:
            self._log.error(f"Error decoding message: {str(raw)} {e}")

    def _parse_out_bound_account_position(self, raw: bytes):
        res = self._ws_msg_spot_account_update_decoder.decode(raw)
        self._log.debug(f"Out bound account position: {res}")

        balances = res.parse_to_balances()
        self._cache._apply_balance(account_type=self._account_type, balances=balances)

    def _parse_account_update(self, raw: bytes):
        res = self._ws_msg_futures_account_update_decoder.decode(raw)
        self._log.debug(f"Account update: {res}")

        balances = res.a.parse_to_balances()
        self._cache._apply_balance(account_type=self._account_type, balances=balances)

        event_unit = res.fs
        for position in res.a.P:
            if event_unit == BinanceBusinessUnit.UM:
                id = position.s + "_linear"
                symbol = self._market_id[id]
            elif event_unit == BinanceBusinessUnit.CM:
                id = position.s + "_inverse"
                symbol = self._market_id[id]
            else:
                id = position.s + self.market_type
                symbol = self._market_id[id]

            signed_amount = Decimal(position.pa)
            side = position.ps.parse_to_position_side()
            if signed_amount == 0:
                side = None  # 0 means no position side
            else:
                if side == PositionSide.FLAT:
                    if signed_amount > 0:
                        side = PositionSide.LONG
                    elif signed_amount < 0:
                        side = PositionSide.SHORT
            position = Position(
                symbol=symbol,
                exchange=self._exchange_id,
                signed_amount=signed_amount,
                side=side,
                entry_price=float(position.ep),
                unrealized_pnl=float(position.up),
                realized_pnl=float(position.cr),
            )
            self._cache._apply_position(position)

    def _parse_order_trade_update(self, raw: bytes) -> Order:
        res = self._ws_msg_futures_order_update_decoder.decode(raw)
        self._log.debug(f"Order trade update: {res}")

        event_data = res.o
        event_unit = res.fs

        # Only portfolio margin has "UM" and "CM" event business unit
        if event_unit == BinanceBusinessUnit.UM:
            id = event_data.s + "_linear"
            symbol = self._market_id[id]
        elif event_unit == BinanceBusinessUnit.CM:
            id = event_data.s + "_inverse"
            symbol = self._market_id[id]
        else:
            id = event_data.s + self.market_type
            symbol = self._market_id[id]

        # we use the last filled quantity to calculate the cost, instead of the accumulated filled quantity
        type = event_data.o
        if type.is_market:
            cost = Decimal(event_data.l) * Decimal(event_data.ap)
            cum_cost = Decimal(event_data.z) * Decimal(event_data.ap)
        elif type.is_limit:
            price = Decimal(event_data.ap) or Decimal(
                event_data.p
            )  # if average price is 0 or empty, use price
            cost = Decimal(event_data.l) * price
            cum_cost = Decimal(event_data.z) * price

        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            status=BinanceEnumParser.parse_order_status(event_data.X),
            id=str(event_data.i),
            amount=Decimal(event_data.q),
            filled=Decimal(event_data.z),
            client_order_id=event_data.c,
            timestamp=res.E,
            type=BinanceEnumParser.parse_futures_order_type(event_data.o),
            side=BinanceEnumParser.parse_order_side(event_data.S),
            time_in_force=BinanceEnumParser.parse_time_in_force(event_data.f),
            price=float(event_data.p),
            average=float(event_data.ap),
            last_filled_price=float(event_data.L),
            last_filled=float(event_data.l),
            remaining=Decimal(event_data.q) - Decimal(event_data.z),
            fee=Decimal(event_data.n),
            fee_currency=event_data.N,
            cum_cost=cum_cost,
            cost=cost,
            reduce_only=event_data.R,
            position_side=BinanceEnumParser.parse_position_side(event_data.ps),
        )
        # order status can be "new", "partially_filled", "filled", "canceled", "expired", "failed"
        self._msgbus.send(endpoint="binance.order", msg=order)

    def _parse_execution_report(self, raw: bytes) -> Order:
        event_data = self._ws_msg_spot_order_update_decoder.decode(raw)
        self._log.debug(f"Execution report: {event_data}")

        market_type = self.market_type or "_spot"
        id = event_data.s + market_type
        symbol = self._market_id[id]

        # Calculate average price only if filled amount is non-zero
        average = (
            float(event_data.Z) / float(event_data.z)
            if float(event_data.z) != 0
            else None
        )

        order = Order(
            exchange=self._exchange_id,
            symbol=symbol,
            status=BinanceEnumParser.parse_order_status(event_data.X),
            id=str(event_data.i),
            amount=Decimal(event_data.q),
            filled=Decimal(event_data.z),
            client_order_id=event_data.c,
            timestamp=event_data.E,
            type=BinanceEnumParser.parse_spot_order_type(event_data.o),
            side=BinanceEnumParser.parse_order_side(event_data.S),
            time_in_force=BinanceEnumParser.parse_time_in_force(event_data.f),
            price=float(event_data.p),
            average=average,
            last_filled_price=float(event_data.L),
            last_filled=float(event_data.l),
            remaining=Decimal(event_data.q) - Decimal(event_data.z),
            fee=Decimal(event_data.n),
            fee_currency=event_data.N,
            cum_cost=Decimal(event_data.Z),
            cost=Decimal(event_data.Y),
        )

        self._msgbus.send(endpoint="binance.order", msg=order)

    async def _execute_modify_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._account_type.is_spot_or_margin:
            raise ValueError(
                "Modify order is not supported for `spot` or `margin` account"
            )

        elif self._account_type.is_linear:
            return await self._api_client.put_fapi_v1_order(**params)
        elif self._account_type.is_inverse:
            return await self._api_client.put_dapi_v1_order(**params)
        elif self._account_type.is_portfolio_margin:
            if market.inverse:
                return await self._api_client.put_papi_v1_cm_order(**params)
            elif market.linear:
                return await self._api_client.put_papi_v1_um_order(**params)
            else:
                raise ValueError(f"Modify order is not supported for {symbol}")

    async def _execute_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        """Execute order request based on account type and market.

        Args:
            market: BinanceMarket object
            symbol: Trading symbol
            params: Order parameters

        Returns:
            API response

        Raises:
            ValueError: If market type is not supported for the account type
        """
        if self._account_type.is_spot:
            if not market.spot:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_api_v3_order(**params)

        elif self._account_type.is_isolated_margin_or_margin:
            if not market.margin:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_sapi_v1_margin_order(**params)

        elif self._account_type.is_linear:
            if not market.linear:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_fapi_v1_order(**params)

        elif self._account_type.is_inverse:
            if not market.inverse:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.post_dapi_v1_order(**params)

        elif self._account_type.is_portfolio_margin:
            if market.margin:
                return await self._api_client.post_papi_v1_margin_order(**params)
            elif market.linear:
                return await self._api_client.post_papi_v1_um_order(**params)
            elif market.inverse:
                return await self._api_client.post_papi_v1_cm_order(**params)

    async def create_stop_loss_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        return await self.create_take_profit_order(
            symbol=symbol,
            side=side,
            type=type,
            amount=amount,
            trigger_price=trigger_price,
            trigger_type=trigger_type,
            price=price,
            time_in_force=time_in_force,
            position_side=position_side,
            **kwargs,
        )

    async def create_take_profit_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        trigger_price: Decimal,
        trigger_type: TriggerType = TriggerType.LAST_PRICE,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")

        id = market.id

        if market.inverse or market.linear:
            binance_type = BinanceEnumParser.to_binance_futures_order_type(type)
        elif market.spot:
            binance_type = BinanceEnumParser.to_binance_spot_order_type(type)
        elif market.margin:
            # TODO: margin order is not supported yet
            pass

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "type": binance_type.value,
            "quantity": amount,
            "stopPrice": trigger_price,
            "workingType": BinanceEnumParser.to_binance_trigger_type(
                trigger_type
            ).value,
        }

        if type.is_limit:
            params["price"] = price
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if position_side:
            params["positionSide"] = BinanceEnumParser.to_binance_position_side(
                position_side
            ).value

        reduce_only = kwargs.pop("reduceOnly", False) or kwargs.pop(
            "reduce_only", False
        )
        if reduce_only:
            params["reduceOnly"] = True

        params.update(kwargs)

        try:
            res = await self._execute_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                amount=amount,
                filled=Decimal(0),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                trigger_price=float(res.stopPrice),
                remaining=amount,
                reduce_only=res.reduceOnly if res.reduceOnly else None,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                trigger_price=trigger_price,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        position_side: PositionSide | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        params = {
            "symbol": id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "type": BinanceEnumParser.to_binance_order_type(type).value,
            "quantity": amount,
        }

        if type == OrderType.LIMIT:
            if not price:
                raise ValueError("Price is required for  order")
            params["price"] = price
            params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                time_in_force
            ).value

        if position_side:
            params["positionSide"] = BinanceEnumParser.to_binance_position_side(
                position_side
            ).value

        reduce_only = kwargs.pop("reduceOnly", False) or kwargs.pop(
            "reduce_only", False
        )
        if reduce_only:
            params["reduceOnly"] = True

        params.update(kwargs)

        try:
            res = await self._execute_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                amount=amount,
                filled=Decimal(0),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=type,
                side=side,
                time_in_force=time_in_force,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                remaining=amount,
                reduce_only=res.reduceOnly if res.reduceOnly else None,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            self._log.error(f"Error creating order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                time_in_force=time_in_force,
                position_side=position_side,
                status=OrderStatus.FAILED,
                filled=Decimal(0),
                remaining=amount,
            )
            return order

    async def _execute_cancel_order_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._account_type.is_spot:
            if not market.spot:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_api_v3_order(**params)
        elif self._account_type.is_isolated_margin_or_margin:
            if not market.margin:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_sapi_v1_margin_order(**params)
        elif self._account_type.is_linear:
            if not market.linear:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_fapi_v1_order(**params)
        elif self._account_type.is_inverse:
            if not market.inverse:
                raise ValueError(
                    f"BinanceAccountType.{self._account_type.value} is not supported for {symbol}"
                )
            return await self._api_client.delete_dapi_v1_order(**params)
        elif self._account_type.is_portfolio_margin:
            if market.margin:
                return await self._api_client.delete_papi_v1_margin_order(**params)
            elif market.linear:
                return await self._api_client.delete_papi_v1_um_order(**params)
            elif market.inverse:
                return await self._api_client.delete_papi_v1_cm_order(**params)

    async def cancel_order(self, symbol: str, order_id: int, **kwargs):
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            id = market.id

            params = {
                "symbol": id,
                "order_id": order_id,
                **kwargs,
            }

            res = await self._execute_cancel_order_request(market, symbol, params)

            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.CANCELING,
                id=str(res.orderId),
                amount=res.origQty,
                filled=Decimal(res.executedQty),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=BinanceEnumParser.parse_order_type(res.type) if res.type else None,
                side=BinanceEnumParser.parse_order_side(res.side) if res.side else None,
                time_in_force=BinanceEnumParser.parse_time_in_force(res.timeInForce)
                if res.timeInForce
                else None,
                price=res.price,
                average=res.avgPrice,
                remaining=Decimal(res.origQty) - Decimal(res.executedQty),
                reduce_only=res.reduceOnly,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(f"Error canceling order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                id=str(order_id),
                status=OrderStatus.FAILED,
            )
            return order

    async def _execute_cancel_all_orders_request(
        self, market: BinanceMarket, symbol: str, params: Dict[str, Any]
    ):
        if self._account_type.is_spot:
            await self._api_client.delete_api_v3_open_orders(**params)
        elif self._account_type.is_isolated_margin_or_margin:
            await self._api_client.delete_sapi_v1_margin_order(**params)
        elif self._account_type.is_linear:
            await self._api_client.delete_fapi_v1_all_open_orders(**params)
        elif self._account_type.is_inverse:
            await self._api_client.delete_dapi_v1_all_open_orders(**params)
        elif self._account_type.is_portfolio_margin:
            if market.margin:
                await self._api_client.delete_papi_v1_margin_all_open_orders(**params)
            elif market.linear:
                await self._api_client.delete_papi_v1_um_all_open_orders(**params)
            elif market.inverse:
                await self._api_client.delete_papi_v1_cm_all_open_orders(**params)

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            market = self._market.get(symbol)
            if not market:
                raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
            symbol = market.id

            params = {
                "symbol": symbol,
            }
            await self._execute_cancel_all_orders_request(market, symbol, params)
            return True
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(
                f"Error canceling all orders: {error_msg} params: {str(params)}"
            )
            return False

    async def modify_order(
        self,
        symbol: str,
        order_id: int,
        side: OrderSide,
        price: Decimal | None = None,
        amount: Decimal | None = None,
        **kwargs,
    ):
        market = self._market.get(symbol)
        if not market:
            raise ValueError(f"Symbol {symbol} formated wrongly, or not supported")
        id = market.id

        params = {
            "symbol": id,
            "orderId": order_id,
            "side": BinanceEnumParser.to_binance_order_side(side).value,
            "quantity": str(amount) if amount else None,
            "price": str(price) if price else None,
            **kwargs,
        }

        try:
            res = await self._execute_modify_order_request(market, symbol, params)
            order = Order(
                exchange=self._exchange_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                id=str(res.orderId),
                amount=amount,
                filled=Decimal(res.executedQty),
                client_order_id=res.clientOrderId,
                timestamp=res.updateTime,
                type=BinanceEnumParser.parse_order_type(res.type) if res.type else None,
                side=side,
                time_in_force=BinanceEnumParser.parse_time_in_force(res.timeInForce)
                if res.timeInForce
                else None,
                price=float(res.price) if res.price else None,
                average=float(res.avgPrice) if res.avgPrice else None,
                remaining=Decimal(res.origQty) - Decimal(res.executedQty),
                reduce_only=res.reduceOnly,
                position_side=BinanceEnumParser.parse_position_side(res.positionSide)
                if res.positionSide
                else None,
            )
            return order
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(f"Error modifying order: {error_msg} params: {str(params)}")
            order = Order(
                exchange=self._exchange_id,
                timestamp=self._clock.timestamp_ms(),
                symbol=symbol,
                side=side,
                amount=amount,
                price=float(price) if price else None,
                status=OrderStatus.FAILED,
                filled=Decimal("0"),
                remaining=amount,
            )
            return order

    async def _execute_batch_order_request(self, batch_orders: list[Dict[str, Any]]):
        if self._account_type.is_linear:
            return await self._api_client.post_fapi_v1_batch_orders(
                batch_orders=batch_orders
            )
        elif self._account_type.is_inverse:
            return await self._api_client.post_dapi_v1_batch_orders(
                batch_orders=batch_orders
            )
        else:
            raise ValueError(
                f"Batch order is not supported for {self._account_type.value} account type"
            )

    async def create_batch_orders(self, orders: list[BatchOrderSubmit]):
        batch_orders = []
        for order in orders:
            market = self._market.get(order.symbol)
            if not market:
                raise ValueError(
                    f"Symbol {order.symbol} formated wrongly, or not supported"
                )
            id = market.id

            params = {
                "symbol": id,
                "side": BinanceEnumParser.to_binance_order_side(order.side).value,
                "type": BinanceEnumParser.to_binance_order_type(order.type).value,
                "quantity": str(order.amount),
            }

            if order.type.is_limit:
                if not order.price:
                    raise ValueError("Price is required for limit order")

                params["price"] = str(order.price)
                params["timeInForce"] = BinanceEnumParser.to_binance_time_in_force(
                    order.time_in_force
                ).value

            reduce_only = order.kwargs.pop("reduceOnly", False) or order.kwargs.pop(
                "reduce_only", False
            )
            if reduce_only:
                params["reduceOnly"] = True

            params.update(order.kwargs)
            batch_orders.append(params)
        try:
            res = await self._execute_batch_order_request(batch_orders)
            res_batch_orders = []
            for order, res_order in zip(orders, res):
                if not res_order.code:
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        symbol=order.symbol,
                        status=OrderStatus.PENDING,
                        id=str(res_order.orderId),
                        uuid=order.uuid,
                        amount=order.amount,
                        filled=Decimal(0),
                        client_order_id=res_order.clientOrderId,
                        timestamp=res_order.updateTime,
                        type=order.type,
                        side=order.side,
                        time_in_force=order.time_in_force,
                        price=float(order.price) if order.price else None,
                        average=float(res_order.avgPrice)
                        if res_order.avgPrice
                        else None,
                        remaining=order.amount,
                        reduce_only=res_order.reduceOnly
                        if res_order.reduceOnly
                        else None,
                        position_side=BinanceEnumParser.parse_position_side(
                            res_order.positionSide
                        )
                        if res_order.positionSide
                        else None,
                    )
                else:
                    res_batch_order = Order(
                        exchange=self._exchange_id,
                        timestamp=self._clock.timestamp_ms(),
                        uuid=order.uuid,
                        symbol=order.symbol,
                        type=order.type,
                        side=order.side,
                        amount=order.amount,
                        price=float(order.price) if order.price else None,
                        time_in_force=order.time_in_force,
                        status=OrderStatus.FAILED,
                        filled=Decimal(0),
                        remaining=order.amount,
                    )
                    self._log.error(
                        f"Failed to place order for {order.symbol}: {res_order.msg}: id: {order.uuid}"
                    )
                res_batch_orders.append(res_batch_order)
            return res_batch_orders

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._log.error(f"Error placing batch orders: {error_msg}")
            res_batch_orders = []
            for order in orders:
                res_batch_order = Order(
                    exchange=self._exchange_id,
                    timestamp=self._clock.timestamp_ms(),
                    uuid=order.uuid,
                    symbol=order.symbol,
                    type=order.type,
                    side=order.side,
                    amount=order.amount,
                    price=float(order.price) if order.price else None,
                    time_in_force=order.time_in_force,
                    status=OrderStatus.FAILED,
                    filled=Decimal(0),
                    remaining=order.amount,
                )
                res_batch_orders.append(res_batch_order)
            return res_batch_orders

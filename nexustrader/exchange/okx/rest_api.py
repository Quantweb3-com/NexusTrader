import msgspec
from typing import Dict, Any
import base64
import aiohttp
import asyncio
import httpx
from urllib.parse import urlencode
from nexustrader.base import ApiClient
from nexustrader.exchange.okx.constants import (
    OkxRestUrl,
    OkxRateLimiter,
    OkxRateLimiterSync,
)
from nexustrader.exchange.okx.error import OkxHttpError, OkxRequestError
from nexustrader.exchange.okx.schema import (
    OkxPlaceOrderResponse,
    OkxCancelOrderResponse,
    OkxGeneralResponse,
    OkxErrorResponse,
    OkxBalanceResponse,
    OkxPositionResponse,
    OkxCandlesticksResponse,
    OkxSavingsBalanceResponse,
    OkxSavingsPurchaseRedemptResponse,
    OkxSavingsLendingRateSummaryResponse,
    OkxSavingsLendingRateHistoryResponse,
    OkxAssetTransferResponse,
    OkxAmendOrderResponse,
    OkxFinanceStakingDefiRedeemResponse,
    OkxFinanceStakingDefiPurchaseResponse,
    OkxFinanceStakingDefiOffersResponse,
    OkxAccountConfigResponse,
    OkxIndexCandlesticksResponse,
    OkxBatchOrderResponse,
)
from nexustrader.core.nautilius_core import hmac_signature


class OkxApiClient(ApiClient):
    _limiter: OkxRateLimiter
    _limiter_sync: OkxRateLimiterSync

    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        passphrase: str = None,
        testnet: bool = False,
        timeout: int = 10,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            enable_rate_limit=enable_rate_limit,
            rate_limiter=OkxRateLimiter(),
            rate_limiter_sync=OkxRateLimiterSync(),
        )

        self._base_url = OkxRestUrl.DEMO.value if testnet else OkxRestUrl.LIVE.value
        self._passphrase = passphrase
        self._testnet = testnet
        self._place_order_decoder = msgspec.json.Decoder(OkxPlaceOrderResponse)
        self._cancel_order_decoder = msgspec.json.Decoder(OkxCancelOrderResponse)
        self._general_response_decoder = msgspec.json.Decoder(OkxGeneralResponse)
        self._error_response_decoder = msgspec.json.Decoder(OkxErrorResponse)
        self._balance_response_decoder = msgspec.json.Decoder(
            OkxBalanceResponse, strict=False
        )
        self._position_response_decoder = msgspec.json.Decoder(
            OkxPositionResponse, strict=False
        )
        self._candles_response_decoder = msgspec.json.Decoder(
            OkxCandlesticksResponse, strict=False
        )
        self._index_candles_response_decoder = msgspec.json.Decoder(
            OkxIndexCandlesticksResponse, strict=False
        )
        self._savings_balance_response_decoder = msgspec.json.Decoder(
            OkxSavingsBalanceResponse, strict=False
        )

        self._savings_purchase_redempt_response_decoder = msgspec.json.Decoder(
            OkxSavingsPurchaseRedemptResponse, strict=False
        )

        self._savings_lending_rate_summary_response_decoder = msgspec.json.Decoder(
            OkxSavingsLendingRateSummaryResponse, strict=False
        )

        self._savings_lending_rate_history_response_decoder = msgspec.json.Decoder(
            OkxSavingsLendingRateHistoryResponse, strict=False
        )

        self._asset_transfer_response_decoder = msgspec.json.Decoder(
            OkxAssetTransferResponse, strict=False
        )

        self._amend_order_response_decoder = msgspec.json.Decoder(
            OkxAmendOrderResponse, strict=False
        )

        self._finance_staking_defi_redeem_response_decoder = msgspec.json.Decoder(
            OkxFinanceStakingDefiRedeemResponse, strict=False
        )

        self._finance_staking_defi_purchase_response_decoder = msgspec.json.Decoder(
            OkxFinanceStakingDefiPurchaseResponse, strict=False
        )

        self._finance_staking_defi_offers_response_decoder = msgspec.json.Decoder(
            OkxFinanceStakingDefiOffersResponse, strict=False
        )

        self._account_config_response_decoder = msgspec.json.Decoder(
            OkxAccountConfigResponse, strict=False
        )

        self._batch_order_response_decoder = msgspec.json.Decoder(OkxBatchOrderResponse)

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
        }

        if self._testnet:
            self._headers["x-simulated-trading"] = "1"

    async def get_api_v5_account_balance(
        self, ccy: str | None = None
    ) -> OkxBalanceResponse:
        """
        https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-balance
        """
        endpoint = "/api/v5/account/balance"
        payload = {"ccy": ccy} if ccy else {}
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("GET", endpoint, payload=payload, signed=True)
        return self._balance_response_decoder.decode(raw)

    async def get_api_v5_account_positions(
        self,
        inst_type: str | None = None,
        inst_id: str | None = None,
        pos_id: str | None = None,
    ) -> OkxPositionResponse:
        """
        https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-positions
        """
        endpoint = "/api/v5/account/positions"
        payload = {
            k: v
            for k, v in {
                "instType": inst_type,
                "instId": inst_id,
                "posId": pos_id,
            }.items()
            if v is not None
        }
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("GET", endpoint, payload=payload, signed=True)
        return self._position_response_decoder.decode(raw)

    async def post_api_v5_trade_order(
        self,
        inst_id: str,
        td_mode: str,
        side: str,
        ord_type: str,
        sz: str,
        **kwargs,
    ) -> OkxPlaceOrderResponse:
        """
        Place a new order
        https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order

        {'arg': {'channel': 'orders', 'instType': 'ANY', 'uid': '611800569950521616'}, 'data': [{'instType': 'SWAP', 'instId': 'BTC-USDT-SWAP', 'tgtCcy': '', 'ccy': '', 'ordId': '1993784914940116992', 'clOrdId': '', 'algoClOrdId': '', 'algoId': '', 'tag': '', 'px': '80000', 'sz': '0.1', 'notionalUsd': '80.0128', 'ordType': 'limit', 'side': 'buy', 'posSide': 'long', 'tdMode': 'cross', 'accFillSz': '0', 'fillNotionalUsd': '', 'avgPx': '0', 'state': 'canceled', 'lever': '3', 'pnl': '0', 'feeCcy': 'USDT', 'fee': '0', 'rebateCcy': 'USDT', 'rebate': '0', 'category': 'normal', 'uTime': '1731921825881', 'cTime': '1731921820806', 'source': '', 'reduceOnly': 'false', 'cancelSource': '1', 'quickMgnType': '', 'stpId': '', 'stpMode': 'cancel_maker', 'attachAlgoClOrdId': '', 'lastPx': '91880', 'isTpLimit': 'false', 'slTriggerPx': '', 'slTriggerPxType': '', 'tpOrdPx': '', 'tpTriggerPx': '', 'tpTriggerPxType': '', 'slOrdPx': '', 'fillPx': '', 'tradeId': '', 'fillSz': '0', 'fillTime': '', 'fillPnl': '0', 'fillFee': '0', 'fillFeeCcy': '', 'execType': '', 'fillPxVol': '', 'fillPxUsd': '', 'fillMarkVol': '', 'fillFwdPx': '', 'fillMarkPx': '', 'amendSource': '', 'reqId': '', 'amendResult': '', 'code': '0', 'msg': '', 'pxType': '', 'pxUsd': '', 'pxVol': '', 'linkedAlgoOrd': {'algoId': ''}, 'attachAlgoOrds': []}]}
        """
        endpoint = "/api/v5/trade/order"
        payload = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
            **kwargs,
        }
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._place_order_decoder.decode(raw)

    async def post_api_v5_trade_cancel_order(
        self, inst_id: str, ord_id: str | None = None, cl_ord_id: str | None = None
    ) -> OkxCancelOrderResponse:
        """
        Cancel an existing order
        https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-cancel-order
        """
        endpoint = "/api/v5/trade/cancel-order"
        payload = {"instId": inst_id}
        if ord_id:
            payload["ordId"] = ord_id
        if cl_ord_id:
            payload["clOrdId"] = cl_ord_id

        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._cancel_order_decoder.decode(raw)

    def get_api_v5_market_history_index_candles(
        self,
        instId: str,
        bar: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> OkxIndexCandlesticksResponse:
        """
        GET /api/v5/market/history-index-candles
        """
        endpoint = "/api/v5/market/history-index-candles"
        payload = {
            "instId": instId,
            "bar": bar.replace("candle", ""),
            "after": after,
            "before": before,
            "limit": str(limit),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("GET", endpoint, payload=payload, signed=False)
        return self._index_candles_response_decoder.decode(raw)

    def get_api_v5_market_candles(
        self,
        instId: str,
        bar: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: int | None = None,
    ) -> OkxCandlesticksResponse:
        # the default bar is 1m
        endpoint = "/api/v5/market/candles"
        payload = {
            k: v
            for k, v in {
                "instId": instId,
                "bar": bar.replace("candle", ""),
                "after": after,
                "before": before,
                "limit": str(limit),
            }.items()
            if v is not None
        }
        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("GET", endpoint, payload=payload, signed=False)
        return self._candles_response_decoder.decode(raw)

    def get_api_v5_market_history_candles(
        self,
        instId: str,
        bar: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: str | None = None,
    ) -> OkxCandlesticksResponse:
        # the default bar is 1m
        endpoint = "/api/v5/market/history-candles"
        payload = {
            k: v
            for k, v in {
                "instId": instId,
                "bar": bar.replace("candle", ""),
                "after": after,
                "before": before,
                "limit": str(limit),
            }.items()
            if v is not None
        }
        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("GET", endpoint, payload=payload, signed=False)
        return self._candles_response_decoder.decode(raw)

    async def get_api_v5_finance_savings_balance(
        self,
        ccy: str | None = None,
    ) -> OkxSavingsBalanceResponse:
        """
        GET /api/v5/finance/savings/balance
        """
        endpoint = "/api/v5/finance/savings/balance"
        payload = {"ccy": ccy} if ccy else None
        raw = await self._fetch("GET", endpoint, payload=payload, signed=True)
        return self._savings_balance_response_decoder.decode(raw)

    async def post_api_v5_finance_savings_purchase_redempt(
        self,
        ccy: str,
        amt: str,
        side: str,
        rate: str | None = None,
    ) -> OkxSavingsPurchaseRedemptResponse:
        """
        POST /api/v5/finance/savings/purchase-redempt
        """
        endpoint = "/api/v5/finance/savings/purchase-redempt"
        payload = {
            "ccy": ccy,
            "amt": amt,
            "side": side,
        }
        if rate:
            payload["rate"] = rate

        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._savings_purchase_redempt_response_decoder.decode(raw)

    async def get_api_v5_finance_savings_lending_rate_summary(
        self,
        ccy: str | None = None,
    ) -> OkxSavingsLendingRateSummaryResponse:
        """
        /api/v5/finance/savings/lending-rate-summary
        """
        endpoint = "/api/v5/finance/savings/lending-rate-summary"
        payload = {"ccy": ccy} if ccy else None
        raw = await self._fetch("GET", endpoint, payload=payload, signed=False)
        return self._savings_lending_rate_summary_response_decoder.decode(raw)

    async def get_api_v5_finance_savings_lending_rate_history(
        self,
        ccy: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: str | None = None,
    ) -> OkxSavingsLendingRateHistoryResponse:
        """
        GET /api/v5/finance/savings/lending-rate-history
        """
        endpoint = "/api/v5/finance/savings/lending-rate-history"
        payload = {
            "ccy": ccy,
            "after": after,
            "before": before,
            "limit": limit,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("GET", endpoint, payload=payload, signed=False)
        return self._savings_lending_rate_history_response_decoder.decode(raw)

    async def post_api_v5_asset_transfer(
        self,
        ccy: str,
        amt: str,
        from_acct: str,  # from
        to_acct: str,  # to
        type: str = "0",
        subAcct: str = None,
        loanTrans: bool = False,
        omitPosRisk: bool = False,
        clientId: str = None,
    ) -> OkxAssetTransferResponse:
        """
        POST /api/v5/asset/transfer
        """
        endpoint = "/api/v5/asset/transfer"
        payload = {
            "ccy": ccy,
            "amt": amt,
            "from": from_acct,
            "to": to_acct,
            "type": type,
            "subAcct": subAcct,
            "loanTrans": loanTrans,
            "omitPosRisk": omitPosRisk,
            "clientId": clientId,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._asset_transfer_response_decoder.decode(raw)

    async def post_api_v5_trade_amend_order(
        self,
        instId: str,
        cxlOnFail: bool = False,
        ordId: str = None,
        clOrdId: str = None,
        reqId: str = None,
        newSz: str = None,
        newPx: str = None,
        newPxUsd: str = None,
        newPxVol: str = None,
        attachAlgoOrds: list[dict] = None,
    ):
        """
        https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-amend-order
        POST /api/v5/trade/amend-order
        """
        endpoint = "/api/v5/trade/amend-order"
        payload = {
            "instId": instId,
            "cxlOnFail": cxlOnFail,
            "ordId": ordId,
            "clOrdId": clOrdId,
            "reqId": reqId,
            "newSz": newSz,
            "newPx": newPx,
            "newPxUsd": newPxUsd,
            "newPxVol": newPxVol,
            "attachAlgoOrds": attachAlgoOrds,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._amend_order_response_decoder.decode(raw)

    async def post_api_v5_finance_staking_defi_redeem(
        self, ordId: str, protocolType: str, allowEarlyRedeem: bool = False
    ):
        """
        POST /api/v5/finance/staking-defi/redeem
        """
        endpoint = "/api/v5/finance/staking-defi/redeem"
        payload = {
            "ordId": ordId,
            "protocolType": protocolType,
            "allowEarlyRedeem": allowEarlyRedeem,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._finance_staking_defi_redeem_response_decoder.decode(raw)

    async def post_api_v5_trade_batch_orders(
        self, payload: list[dict]
    ) -> OkxBatchOrderResponse:
        """
        POST /api/v5/trade/batch-orders
        """
        endpoint = "/api/v5/trade/batch-orders"
        cost = len(payload)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._batch_order_response_decoder.decode(raw)

    async def post_api_v5_finance_staking_defi_purchase(
        self, productId: str, investData: list[dict], term: str = None, tag: str = None
    ):
        """
        productId	String	Yes	Product ID
        investData	Array of objects	Yes	Investment data
        > ccy	String	Yes	Investment currency, e.g. BTC
        > amt	String	Yes	Investment amount
        term	String	Conditional	Investment term
        Investment term must be specified for fixed-term product
        tag	String	No	Order tag
        A combination of case-sensitive alphanumerics, all numbers, or all letters of up to 16 characters.
        """

        endpoint = "/api/v5/finance/staking-defi/purchase"
        payload = {
            "productId": productId,
            "investData": investData,
            "term": term,
            "tag": tag,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._finance_staking_defi_purchase_response_decoder.decode(raw)

    async def get_api_v5_finance_staking_defi_offers(
        self, productId: str = None, protocolType: str = None, ccy: str = None
    ):
        endpoint = "/api/v5/finance/staking-defi/offers"
        payload = {
            "productId": productId,
            "protocolType": protocolType,
            "ccy": ccy,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("GET", endpoint, payload=payload, signed=True)
        return self._finance_staking_defi_offers_response_decoder.decode(raw)

    async def get_api_v5_account_config(self):
        """
        GET /api/v5/account/config
        """
        endpoint = "/api/v5/account/config"
        raw = await self._fetch("GET", endpoint, signed=True)
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        return self._account_config_response_decoder.decode(raw)

    def _generate_signature(self, message: str) -> str:
        hex_digest = hmac_signature(self._secret, message)
        digest = bytes.fromhex(hex_digest)
        return base64.b64encode(digest).decode()

    def _get_signature(
        self, ts: str, method: str, request_path: str, payload: bytes
    ) -> str:
        body = payload.decode() if payload else ""
        sign_str = f"{ts}{method}{request_path}{body}"
        signature = self._generate_signature(sign_str)
        return signature

    def _get_timestamp(self) -> str:
        return (
            self._clock.utc_now()
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _get_headers(
        self, ts: str, method: str, request_path: str, payload: bytes
    ) -> Dict[str, Any]:
        headers = self._headers
        signature = self._get_signature(ts, method, request_path, payload)
        headers.update(
            {
                "OK-ACCESS-KEY": self._api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self._passphrase,
            }
        )
        return headers

    async def _fetch(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> bytes:
        self._init_session(self._base_url)

        request_path = endpoint
        headers = self._headers
        timestamp = self._get_timestamp()

        payload = payload or {}

        payload_json = (
            urlencode(payload) if method == "GET" else msgspec.json.encode(payload)
        )

        if method == "GET":
            if payload_json:
                request_path += f"?{payload_json}"
            payload_json = None

        if signed and self._api_key:
            headers = self._get_headers(timestamp, method, request_path, payload_json)

        try:
            self._log.debug(
                f"{method} {request_path} Headers: {headers} payload: {payload_json}"
            )

            response = await self._session.request(
                method=method,
                url=request_path,
                headers=headers,
                data=payload_json,
            )
            raw = await response.read()

            if response.status >= 400:
                raise OkxHttpError(
                    status_code=response.status,
                    message=msgspec.json.decode(raw),
                    headers=response.headers,
                )
            okx_response = self._general_response_decoder.decode(raw)
            if okx_response.code == "0":
                return raw
            else:
                okx_error_response = self._error_response_decoder.decode(raw)
                for data in okx_error_response.data:
                    raise OkxRequestError(
                        error_code=data.sCode,
                        status_code=response.status,
                        message=data.sMsg,
                    )
                raise OkxRequestError(
                    error_code=okx_error_response.code,
                    status_code=response.status,
                    message=okx_error_response.msg,
                )
        except aiohttp.ClientError as e:
            self._log.error(f"Client Error {method} {request_path} {e}")
            raise
        except asyncio.TimeoutError:
            self._log.error(f"Timeout {method} {request_path}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

    def _fetch_sync(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> bytes:
        self._init_sync_session(self._base_url)

        request_path = endpoint
        headers = self._headers
        timestamp = self._get_timestamp()

        payload = payload or {}

        payload_json = (
            urlencode(payload) if method == "GET" else msgspec.json.encode(payload)
        )

        if method == "GET":
            if payload_json:
                request_path += f"?{payload_json}"
            payload_json = None

        if signed and self._api_key:
            headers = self._get_headers(timestamp, method, request_path, payload_json)

        try:
            self._log.debug(
                f"{method} {request_path} Headers: {headers} payload: {payload_json}"
            )

            response = self._sync_session.request(
                method=method,
                url=request_path,
                headers=headers,
                data=payload_json,
            )
            raw = response.content

            if response.status_code >= 400:
                raise OkxHttpError(
                    status_code=response.status_code,
                    message=msgspec.json.decode(raw),
                    headers=response.headers,
                )
            okx_response = self._general_response_decoder.decode(raw)
            if okx_response.code == "0":
                return raw
            else:
                okx_error_response = self._error_response_decoder.decode(raw)
                for data in okx_error_response.data:
                    raise OkxRequestError(
                        error_code=data.sCode,
                        status_code=response.status_code,
                        message=data.sMsg,
                    )
                raise OkxRequestError(
                    error_code=okx_error_response.code,
                    status_code=response.status_code,
                    message=okx_error_response.msg,
                )
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} {request_path} {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} {request_path} {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} {request_path} {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} {request_path} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

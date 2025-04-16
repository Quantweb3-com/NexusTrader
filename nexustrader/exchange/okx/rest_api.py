import msgspec
from typing import Dict, Any
import orjson
import hmac
import base64
import asyncio
import aiohttp
from urllib.parse import urljoin, urlencode
from nexustrader.base import ApiClient
from nexustrader.exchange.okx.constants import OkxRestUrl
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
)
from nexustrader.core.nautilius_core import hmac_signature


class OkxApiClient(ApiClient):
    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        passphrase: str = None,
        testnet: bool = False,
        timeout: int = 10,
    ):
        super().__init__(
            api_key=api_key,
            secret=secret,
            timeout=timeout,
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

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
        }

    async def get_api_v5_account_balance(
        self, ccy: str | None = None
    ) -> OkxBalanceResponse:
        endpoint = "/api/v5/account/balance"
        payload = {"ccy": ccy} if ccy else {}
        raw = await self._fetch("GET", endpoint, payload=payload, signed=True)
        return self._balance_response_decoder.decode(raw)

    async def get_api_v5_account_positions(
        self,
        inst_type: str | None = None,
        inst_id: str | None = None,
        pos_id: str | None = None,
    ) -> OkxPositionResponse:
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

        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._cancel_order_decoder.decode(raw)

    def _generate_signature(self, message: str) -> str:
        mac = hmac.new(
            bytes(self._secret, encoding="utf8"),
            bytes(message, encoding="utf-8"),
            digestmod="sha256",
        )
        return base64.b64encode(mac.digest()).decode()

    def _generate_signature_v2(self, message: str) -> str:
        hex_digest = hmac_signature(self._secret, message)
        digest = bytes.fromhex(hex_digest)
        return base64.b64encode(digest).decode()

    async def _get_signature(
        self, ts: str, method: str, request_path: str, payload: Dict[str, Any] = None
    ) -> str:
        body = ""
        if payload:
            body = orjson.dumps(payload).decode()

        sign_str = f"{ts}{method}{request_path}{body}"
        signature = self._generate_signature_v2(sign_str)
        return signature

    def _get_timestamp(self) -> str:
        return (
            self._clock.utc_now()
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    async def _get_headers(
        self, ts: str, method: str, request_path: str, payload: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        headers = self._headers
        signature = await self._get_signature(ts, method, request_path, payload)
        headers.update(
            {
                "OK-ACCESS-KEY": self._api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self._passphrase,
            }
        )
        if self._testnet:
            headers["x-simulated-trading"] = "1"
        return headers

    async def get_api_v5_market_candles(
        self,
        instId: str,
        bar: str | None = None,
        after: str | None = None,
        before: str | None = None,
        limit: str | None = None,
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
        raw = await self._fetch("GET", endpoint, payload=payload, signed=False)
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
        raw = await self._fetch("POST", endpoint, payload=payload, signed=True)
        return self._amend_order_response_decoder.decode(raw)

    async def _fetch(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> bytes:
        self._init_session()
        url = urljoin(self._base_url, endpoint)
        request_path = endpoint
        headers = self._headers
        timestamp = self._get_timestamp()

        payload = payload or {}

        payload_json = urlencode(payload) if method == "GET" else orjson.dumps(payload)

        if method == "GET":
            url += f"?{payload_json}"
            payload_json = None

        if signed and self._api_key:
            headers = await self._get_headers(timestamp, method, request_path, payload)

        try:
            self._log.debug(
                f"Request {method} Url: {url} Headers: {headers} Payload: {payload_json}"
            )

            response = await self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=payload_json,
            )
            raw = await response.read()

            if response.status >= 400:
                raise OkxHttpError(
                    status_code=response.status,
                    message=orjson.loads(raw),
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
            self._log.error(f"Client Error {method} Url: {url} {e}")
            raise
        except asyncio.TimeoutError:
            self._log.error(f"Timeout {method} Url: {url}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} Url: {url} {e}")
            raise

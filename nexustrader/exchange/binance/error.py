from nexustrader.exchange.binance.constants import (
    BinanceErrorCode,
    BINANCE_RETRY_ERRORS,
)


class BinanceError(Exception):
    """
    The base class for all Binance specific errors.
    """

    def __init__(self, status, message, headers):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers


class BinanceServerError(BinanceError):
    """
    Represents an Binance specific 500 series HTTP error.
    """

    def __init__(self, status, message, headers):
        super().__init__(status, message, headers)


class BinanceClientError(BinanceError):
    """
    Represents an Binance specific 400 series HTTP error.
    """

    def __init__(self, status, message, headers):
        super().__init__(status, message, headers)


def should_retry(error: BaseException) -> bool:
    """
    Determine if a retry should be attempted based on the error code.

    Parameters
    ----------
    error : BaseException
        The error to check.

    Returns
    -------
    bool
        True if should retry, otherwise False.

    """
    if isinstance(error, BinanceError):
        error_code = BinanceErrorCode(error.message["code"])
        return error_code in BINANCE_RETRY_ERRORS
    return False

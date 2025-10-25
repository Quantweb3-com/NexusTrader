class BinanceClientError(Exception):
    """
    The base class for all Binance specific errors.
    """

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, message='{self.message}')"

    __str__ = __repr__


class BinanceServerError(Exception):
    """
    The base class for all Binance specific errors.
    """

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, message='{self.message}')"

    __str__ = __repr__

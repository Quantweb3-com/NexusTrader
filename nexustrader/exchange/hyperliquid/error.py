from typing import Any


class HyperLiquidHttpError(Exception):
    def __init__(self, status_code: int, message: str, headers: dict[str, Any]):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.headers = headers

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status_code={self.status_code}, message='{self.message}')"

    __str__ = __repr__


class HyperLiquidOrderError(Exception):
    """
    The base class for all HyperLiquid specific errors.
    """

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(error_type={self.error_type}, message='{self.message}')"

    __str__ = __repr__

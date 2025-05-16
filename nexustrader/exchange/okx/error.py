from typing import Any


class OkxHttpError(Exception):
    """
    Define the class for all OKX http specific errors.
    """

    def __init__(self, status_code: int, message: str, headers: dict[str, Any]) -> None:
        """
        Define the base class for all OKX http specific errors.
        """
        super().__init__(message)
        self.status = status_code
        self.message = message
        self.headers = headers


class OkxRequestError(Exception):
    """
    The base class for all OKX specific errors.

    References
    ----------
    https://www.okx.com/docs-v5/en/?python#error-code

    """

    def __init__(self, error_code: int, status_code: int | None, message: str | None):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.message = message

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.error_code}, message='{self.message}')"
        )

    __str__ = __repr__

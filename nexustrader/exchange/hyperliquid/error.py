from nexustrader.error import EngineBuildError


class HyperLiquidError(EngineBuildError):
    """Base exception for HyperLiquid exchange errors"""
    pass


class HyperLiquidHttpError(HyperLiquidError):
    """HTTP error from HyperLiquid API"""
    
    def __init__(self, status_code: int, message: str, headers: dict = None):
        self.status_code = status_code
        self.message = message
        self.headers = headers or {}
        super().__init__(f"HTTP {status_code}: {message}")


class HyperLiquidOrderError(HyperLiquidError):
    """Order-related error from HyperLiquid"""
    pass


class HyperLiquidAuthenticationError(HyperLiquidError):
    """Authentication error from HyperLiquid"""
    pass


class HyperLiquidRateLimitError(HyperLiquidError):
    """Rate limit error from HyperLiquid"""
    pass


class HyperLiquidInsufficientBalanceError(HyperLiquidError):
    """Insufficient balance error from HyperLiquid"""
    pass


class HyperLiquidInvalidOrderError(HyperLiquidError):
    """Invalid order error from HyperLiquid"""
    pass 
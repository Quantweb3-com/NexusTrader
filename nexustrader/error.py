class NexusTraderError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class EngineBuildError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class SubscriptionError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class KlineSupportedError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class StrategyBuildError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class OrderError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class PositionModeError(NexusTraderError):
    def __init__(self, message: str):
        super().__init__(message)


class WsRequestNotSentError(NexusTraderError):
    """Raised when a WebSocket request could not be sent because the socket is not connected."""

    def __init__(
        self, message: str = "WebSocket request not sent: connection unavailable"
    ):
        super().__init__(message)


class WsAckTimeoutError(NexusTraderError):
    """Raised when no ACK is received from the exchange within the timeout window."""

    def __init__(self, oid: str, timeout: float):
        super().__init__(f"No WS ACK received for oid={oid} within {timeout}s")
        self.oid = oid
        self.timeout = timeout


class WsAckRejectedError(NexusTraderError):
    """Raised when the exchange explicitly rejects a WebSocket order/cancel request."""

    def __init__(self, oid: str, reason: str):
        super().__init__(f"WS ACK rejected for oid={oid}: {reason}")
        self.oid = oid
        self.reason = reason

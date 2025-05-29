from nexustrader.base import ApiClient


class BitgetApiClient(ApiClient):
    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        testnet: bool = False,
        timeout: int = 10,
    ):
        super().__init__(
            api_key=api_key,
            secret=secret,
            timeout=timeout,
        )

        self._base_url = "https://api.bitget.com"
        self._passphrase = passphrase
        self._testnet = testnet

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "NexusTrader/1.0",
        }

        if self._testnet:
            self._headers["PAPTRADING"] = "1"

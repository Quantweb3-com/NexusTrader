import pytest

from nexustrader.exchange.okx.constants import OkxAccountType


# OKX retires websocket port 8443, the streams use the default https port 443
@pytest.mark.parametrize(
    "account_type, host",
    [
        (OkxAccountType.LIVE, "wss://ws.okx.com"),
        (OkxAccountType.DEMO, "wss://wspap.okx.com"),
    ],
)
def test_okx_stream_url_uses_default_port(account_type, host):
    assert account_type.stream_url == f"{host}/ws"

from fastapi.testclient import TestClient

from nexustrader.web import create_strategy_app


def test_strategy_app_binds_self_method():
    app = create_strategy_app()

    class DummyStrategy:
        calls: list[str] = []

        @app.get("/ping")
        async def on_web_cb(self):
            self.calls.append("ping")
            return {"status": "ok"}

    strategy = DummyStrategy()

    # Routes should be pending until we bind the strategy instance
    assert app.has_user_routes()

    app.bind_strategy(strategy)

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert strategy.calls == ["ping"]

    app.unbind_strategy()
    client = TestClient(app)
    assert client.get("/ping").status_code == 404

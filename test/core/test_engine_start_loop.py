import asyncio

from nexustrader.engine import Engine


class OnStartStrategy:
    def __init__(self):
        self.loop = None

    def on_start(self):
        self.loop = asyncio.get_event_loop()


class CacheStub:
    async def start(self):
        return None


def test_engine_sets_current_loop_before_on_start():
    strategy = OnStartStrategy()
    engine = Engine.__new__(Engine)
    engine._loop = asyncio.new_event_loop()
    engine._build = lambda: None
    engine._cache = CacheStub()
    engine._start_web_interface = lambda: None
    engine.dispose = lambda: None
    engine._strategy = strategy

    async def _start():
        strategy.on_start()

    engine._start = _start

    try:
        Engine.start(engine)

        assert strategy.loop is engine._loop
    finally:
        engine._loop.close()
        asyncio.set_event_loop(None)

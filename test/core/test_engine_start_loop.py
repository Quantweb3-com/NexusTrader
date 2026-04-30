import asyncio

from nexustrader.engine import Engine


class OnStartStrategy:
    def __init__(self):
        self.loop = None

    def on_start(self):
        self.loop = asyncio.get_event_loop()


async def _noop_start():
    return None


def test_engine_sets_current_loop_before_on_start():
    strategy = OnStartStrategy()
    engine = Engine.__new__(Engine)
    engine._loop = asyncio.new_event_loop()
    engine._build = lambda: None
    engine._start = _noop_start
    engine._strategy = strategy

    try:
        Engine.start(engine)

        assert strategy.loop is engine._loop
    finally:
        engine._loop.close()
        asyncio.set_event_loop(None)

# Stdlib
from typing import List, Tuple, Coroutine

# External Libraries
from anyio import sleep

# Asynctwitch
from asynctwitch.bots.base import BotBase


class TimerBot(BotBase):
    def __init__(self,
                 *,
                 timers: List[Tuple[int, Coroutine]] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self._timers = timers or []

    async def event_ready(self):
        await super().event_ready()

        async def _task(time: int, coro: Coroutine):
            while self.do_loop:
                await sleep(time)
                await coro

        for timer in self._timers:
            await self._task_group.spawn(_task, *timer)

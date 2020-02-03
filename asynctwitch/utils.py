# __future__ imports
from __future__ import annotations

# Stdlib
from functools import wraps
from threading import Thread
import time
from typing import TYPE_CHECKING

# External Libraries
import anyio

# Asynctwitch
from asynctwitch.entities.badge import Badge
from asynctwitch.entities.emote import Emote

if TYPE_CHECKING:
    from typing import Coroutine, Callable, Any, List
    from asynctwitch.bots.base import BotBase


def ratelimit_wrapper(
    coro: Callable[[Any, ...], Coroutine]  # pylint: disable=bad-continuation
) -> Callable[[Any, ...], Coroutine]:
    def decrease(self):
        self._count -= 1

    @wraps(coro)
    async def wrapper(self: BotBase, *args, **kwargs):
        _max = 100 if all(status.is_mod
                          for status in self.channel_status.values()) else 20

        while self._count == _max:
            await anyio.sleep(1)

        self._count += 1
        r = await coro(self, *args, **kwargs)

        def decrease_after_20():
            time.sleep(20)
            decrease(self)

        Thread(target=decrease_after_20).start()

        return r

    return wrapper


def _parse_badges(string: str) -> List[Badge]:
    if not string:
        return []
    return [
        Badge(*badge.split("/"))
        for badge in (string.split(",") if "," in string else [string])
    ]


def _parse_emotes(string: str) -> List[Emote]:
    if not string:
        return []

    return [
        Emote(emote_id, loc)
        for (emote_id, locations) in map(lambda s: s.split(":"), (
            string.split("/") if "/" in string else [string]))
        for loc in (locations if "," in locations else [locations])
    ]

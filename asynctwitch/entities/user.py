from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from asynctwitch.entities.object import Object
from asynctwitch.utils import _parse_badges
from asynctwitch.entities.badge import Badge

if TYPE_CHECKING:
    from typing import Dict, List, Union


class User(Object):
    def __init__(self, name: str, channel: str, tags: Dict[str, Union[str, int]] = None):
        super().__init__()
        self.name = name
        self.channel = channel
        if tags:
            self.badges: List[Badge] = _parse_badges(tags['badges'])
            self.color: str = tags['color']
            self.moderator: int = tags['mod']
            self.subscriber: int = tags['subscriber']
            self.type: str = tags['user-type']
            with suppress(IndexError):
                self.turbo: int = tags['turbo']
                self.id: str = tags['user-id']

# __future__ imports
from __future__ import annotations

# Stdlib
from contextlib import suppress
from typing import TYPE_CHECKING

# Asynctwitch
from asynctwitch.entities.badge import Badge
from asynctwitch.entities.object import Object
from asynctwitch.utils import _parse_badges

if TYPE_CHECKING:
    from typing import Dict, List, Union


class User(Object):
    def __init__(self,
                 name: str,
                 channel: str,
                 tags: Dict[str, Union[str, int]] = None):
        # TODO: Refactor
        super().__init__()
        self.name = name
        self.channel = channel
        if tags:
            self.badges: List[Badge] = _parse_badges(tags['badges'])
            self.color: str = tags['color']
            self.moderator: int = tags['mod']
            self.subscriber: int = tags['subscriber']
            self.type: str = tags['user-type']
            with suppress(KeyError):
                self.turbo: int = tags['turbo']
                self.id: str = tags['user-id']

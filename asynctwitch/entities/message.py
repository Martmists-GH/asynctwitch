# Stdlib
import datetime
import uuid

# Asynctwitch
from asynctwitch.entities.object import Object
from asynctwitch.entities.user import User
from asynctwitch.utils import _parse_emotes


class Message(Object):
    """ Custom message object to combine message, author and timestamp """
    def __init__(self, m, a, channel, tags, **kwargs):
        # TODO: Refactor
        super().__init__()
        if tags:
            self.raw_timestamp = tags['tmi-sent-ts']
            self.timestamp = datetime.datetime.fromtimestamp(
                int(tags['tmi-sent-ts']) / 1000)
            self.emotes = _parse_emotes(tags['emotes'])
            self.id = uuid.UUID(tags.get('id') or tags.get("target-msg-id"))
            self.room_id = tags['room-id']
        self.content = m
        self.author = User(a, channel, tags)
        self.channel = channel

    def __str__(self):
        return self.content

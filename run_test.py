from uuid import uuid4

import asynctwitch as at
from asynctwitch.entities.message import Message
from asynctwitch.ext.db.sqlite import SQLiteDB


class Compound(at.ChatLogBot, at.DatabaseBot[SQLiteDB], at.JoinRequestBot, at.TimerBot):
    def __init__(self, **kwargs):
        async def say_hi():
            print("hi")

        kwargs["timers"] = [(
            120, say_hi()
        )]

        super().__init__(**kwargs)

    async def event_ready(self):
        await super().event_ready()
        await self.query("CREATE TABLE IF NOT EXISTS messages "
                         "(id VARCHAR(32) PRIMARY KEY, channel VARCHAR(32), user VARCHAR(32), message TEXT)",
                         ())

    async def event_message(self, message: Message):
        await super().event_message(message)
        await self.query("INSERT INTO messages VALUES (?, ?, ?, ?)",
                         (uuid4().hex, message.channel, message.author.name, message.content))


bot = Compound(channels=["bobross"])

bot.start()

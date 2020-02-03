# Asynctwitch
from asynctwitch.bots.base import BotBase
from asynctwitch.entities.message import Message


class JoinRequestBot(BotBase):
    async def event_private_message(self, message: Message):
        await super().event_private_message(message)
        if message.content == "join":
            await self._join("#" + message.author.name)

        if message.content == "leave":
            await self._part("#" + message.author.name)

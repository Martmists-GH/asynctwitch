# Asynctwitch
from asynctwitch.bots.base import BotBase
from asynctwitch.entities.message import Message


class ChatLogBot(BotBase):
    async def event_message(self, message: Message):
        print(f"#{message.channel} > {message.author.name}: {message.content}")

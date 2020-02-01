from asynctwitch.bots.base import BotBase


class ChatLogBot(BotBase):
    def event_message(self, message: str):
        print(message)

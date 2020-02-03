AsyncTwitch
=======================

This library is used to asynchronously interact with twitch chat.

----

How to use:

```python
import asynctwitch

# Create a bot that connects and does nothing else
bot = asynctwitch.BotBase(channels=["my_channel"])
bot.start()

# Create a bot that logs messages
chat_bot = asynctwitch.ChatLogBot(channels=["my_channel"])
chat_bot.start()

# Create a bot that joins your channel when sent "join" and leaves when sent "leave"
join_bot = asynctwitch.JoinRequestBot()
join_bot.start()

# Create a bot that manages a database
# Here we use SQLite as example, but providers for MySQL and PostgreSQL exist too
# Ideally you'd implement one yourself.
db_bot = asynctwitch.DatabaseBot[SQLiteDB](channels=["my_channel"])
db_bot.start()


# Bots can be combined using multi-inheritance
class JoinLogBot(asynctwitch.ChatLogBot, asynctwitch.JoinRequestBot):
    pass

join_log_bot = JoinLogBot()
join_log_bot.start()


# You can add handling for any event:
class CustomBot(asynctwitch.BotBase):
    async def event_message(self, message: asynctwitch.Message):
        await super().event_message(message)
        print("Received a message!")
        print(message.content)

```

AsyncTwitch
=======================

This library is used to asynchronously interact with twitch chat.

----

Requirements: 

- Create a twitch.tv account
- Get an Oauth token

----

How to use:

```python
import asynctwitch


bot = asynctwitch.CommandBot(
    user = "Your twitch username",
	oauth = "Your twitch oauth token",	# oauth:1234567890abcdefghijklmnopqrst
	channel = "channel name",			# Defaults to Twitch
	prefix = "yourprefixhere",			# Defaults to '!'
)



# Example command:
@bot.command('example', alias=['moreexample'], desc='example command')
async def example(message, word1:str, number1:int, rest:str):
	bot.say('wow')



@bot.command('ping', alias=['pingme', 'alias2'], desc='ping command')
async def ping(message):
	message.reply("@{0.author}, pong!".format(message))

bot.start()	
```

It's also possible to handle messages your own way, just use

```python
@bot.override
async def parse_message(message):
	# your handling here
```
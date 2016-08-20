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

# Example subcommand:
@bot.command('say')
async def say(m, subcommand:str):
	pass
	
c = bot.get_command('say') # I suck at programming pls help
@c.subcommand('this')
async def this(m):
	bot.say("that")

bot.start()	
```




It's also possible to handle messages your own way, just use

```python
bot = asynctwitch.Bot(
    user = "Your twitch username",
	oauth = "Your twitch oauth token",	# oauth:1234567890abcdefghijklmnopqrst
	channel = "channel name",			# Defaults to Twitch
	prefix = "yourprefixhere",			# Defaults to '!'
)

@bot.override
async def parse_message(message):
	# your handling here
```

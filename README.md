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
@bot.command('example', alias=['moreexample','anothaone'], desc='example command')
async def example(message, word1:str, number1:int, rest:str):
	bot.say('wow')

# Example subcommand:
@bot.command('say')
async def say(m, subcommand:str):
	pass
	
@say.subcommand('this')
async def this(m):
	bot.say("that")

bot.start()	
```

To use a config file instead, use
```python
asynctwitch.Bot(config="your_settings.ini")
# or
asynctwitch.CommandBot(config="your_settings.ini")
```see config.ini for an example ini


It's also possible to handle messages your own way, just use

```python
bot = asynctwitch.Bot(
    user = "Your twitch username",
	oauth = "Your twitch oauth token",	# oauth:1234567890abcdefghijklmnopqrst
	channel = "channel name",			# Defaults to Twitch
	prefix = "yourprefixhere",			# Defaults to '!'
)

@bot.override
async def event_message(message):
	# your handling here
```


To use `await bot.play_file('file.mp3')`, ffplay has to be installed. It can be found on the ffmpeg website.

To use `await bot.play_ytdl('song')`, youtube_dl has to be installed. Use `pip install youtube_dl` to install it.

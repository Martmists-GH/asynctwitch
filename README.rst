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

# Use the pre-made CommandBot, to handle messages yourself, use asynctwitch.Bot and handle event_message.
bot = asynctwitch.CommandBot(
    user = "Your_bot_twitch_username",
    oauth = "Your_twitch_oauth_token",  # oauth:1234567890abcdefghijklmnopqrst
    channel = "channel_name",           # Defaults to Twitch
    prefix = "your_prefix_here",            # Defaults to '!'
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
```
see config.ini for an example file


It's also possible to handle messages your own way, just use

```python
@bot.override
async def event_message(message):
    # your handling here
```

The same applies to all bot.event_X functions.


To use `await bot.play_file('file.mp3')`, ffprobe, ffmpeg and ffplay have to be installed. They can be found on the ffmpeg website.

To use `await bot.play_ytdl('song')`, youtube_dl has to be installed. Use `pip install youtube_dl` to install it.
You will also need the requirements for `bot.play_file`


These examples use the `async/await` syntax added in python 3.5, to use this code in 3.4 use `@asyncio.coroutine` and `yield from` instead.
THIS DOES NOT WORK WITH PYTHON VERSIONS BELOW 3.4!

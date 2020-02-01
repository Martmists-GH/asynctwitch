import asyncio
import traceback
import sys
import os
import re
import math
import json
import configparser
import time
import subprocess
import functools
import sqlite3
import pathlib

from .dataclasses import Command, Message, User, Song

# Test if they have aiohttp installed in case they didn't use setup.py
try:
    import aiohttp
    aio_installed = True
except ImportError:
    print("To use stats from the API, make sure to install aiohttp. "
          "(pip install aiohttp)")

    aio_installed = False


def db_setup(func):  # easy wrapper for setring up databases
    def inner(file):
        open(file, 'a').close()
        con = sqlite3.connect(file)
        c = con.cursor()
        func(c)
        con.commit()
        con.close()
    return inner


@db_setup
def _setup_points_db(cursor):
    cursor.execute("CREATE TABLE currency (username VARCHAR(30), balance INT)")


@db_setup
def _setup_ranks_db(cursor):
    cursor.execute(
        "CREATE TABLE user_ranks (username VARCHAR(30), rankname TEXT)")
    cursor.execute("CREATE TABLE currency_ranks (currency INT, rankname TEXT)")
    cursor.execute("CREATE TABLE watched_ranks (time INT, rankname TEXT)")


@db_setup
def _setup_time_db(cursor):
    cursor.execute(
        "CREATE TABLE time_watched (username VARCHAR(30), time INT)")


@asyncio.coroutine
def _get_url(loop, url):
    session = aiohttp.ClientSession(loop=loop)
    with aiohttp.Timeout(10):
        response = yield from session.get(url)
        try:
            # other statements
            return (yield from response.json())
        finally:
            if sys.exc_info()[0] is not None:
                # on exceptions, close the connection altogether
                response.close()
            else:
                yield from response.release()
            session.close()


def _decrease_msgcount(self):
    self.message_count -= 1


def create_timer(message, channel, time):
    @asyncio.coroutine
    def wrapper(self):
        while True:
            yield from asyncio.sleep(time)
            yield from self.say(channel, message)
    return wrapper


def ratelimit_wrapper(coro):
    @asyncio.coroutine
    def wrapper(self, *args, **kwargs):
        max = 100 if self.is_mod else 20

        while self.message_count == max:
            yield from asyncio.sleep(1)

        self.message_count += 1
        r = yield from coro(self, *args, **kwargs)
        # make sure it doesn't block the event loop
        self.loop.call_later(20, _decrease_msgcount, self)
        return r
    return wrapper


class Bot:
    """
    A basic Bot. All others inherit from this.
    
    Parameters
    ----------
    oauth : str
        The oauth code for your account
    user : str
        Your username
    prefix : Optional[str]
        The prefix for the bot to listen to. (default: `!`)
    channel : Optional[str, list]
        The channel(s) to serve. (default: `twitch`)
    client_id : Optional[str]
        The application Client ID for the kraken API.
    cache : Optional[int]
        The amount of messages to cache. (default: 100)
    admins : Optional[list]
        The usernames with full access to the bot.
    allow_streams : Optional[bool]
        Allow music to play continuous streams
    """

    def __init__(self, **kwargs):

        if kwargs.get("config"):
            self.load(kwargs.get("config"))

        else:
            self.prefix = kwargs.get("prefix") or "!"
            self.oauth = kwargs.get("oauth")
            self.nick = kwargs.get("user").lower()
            channel = kwargs.get("channel") or "twitch"
            if isinstance(channel, str):
                self.chan = ["#" + channel.lower().strip('#')]
            else:
                self.chan = ["#" + c.lower().strip('#') for c in channel]
            self.client_id = kwargs.get("client_id")

        if os.name == 'nt':
            self.loop = asyncio.ProactorEventLoop()
        else:
            self.loop = asyncio.get_event_loop()

        self.cache_length = kwargs.get("cache") or 100

        asyncio.set_event_loop(self.loop)
        self.host = "irc.chat.twitch.tv"
        self.port = 6667

        self.admins = kwargs.get("admins") or []

        self.song = Song()
        self.is_mod = False
        self.is_playing = False
        self.allow_streams = kwargs.get("allow_streams")

        # Just in case some get sent almost simultaneously even though they
        # shouldn't, limit the message count to max-1
        self.message_count = 1

        self.regex = {
            "data": re.compile(
                r"^(?:@(?P<tags>\S+)\s)?:(?P<data>\S+)(?:\s)"
                r"(?P<action>[A-Z]+)(?:\s#)(?P<channel>\S+)"
                r"(?:\s(?::)?(?P<content>.+))?"),
            "ping": re.compile("PING (?P<content>.+)"),
            "author": re.compile(
                "(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                "@(?P=author).tmi.twitch.tv"),
            "mode": re.compile("(?P<mode>[\+\-])o (?P<user>.+)"),
            "host": re.compile(
                "(?P<channel>[a-zA-Z0-9_]+) "
                "(?P<count>[0-9\-]+)")}

        self.channel_stats = {}

        self.viewer_count = {}
        self.host_count = {}

        self.viewers = {}

        self.hosts = {}

        self.messages = []
        self.channel_moderators = {}
            
        for c in self.chan:
            self.channel_stats[c] = {}

            self.viewer_count[c] = 0
            self.host_count[c] = 0

            self.viewers[c] = {}

            self.hosts[c] = []

            self.channel_moderators[c] = []

    def debug(self):
        for x, y in self.__dict__.items():
            print(x, y)

    def load(self, path):
        """
        Load settings from a config file.
        
        Parameters
        ----------
        path : str
            path to the config file

        """
        config = configparser.ConfigParser(interpolation=None)
        config.read(path)
        self.oauth = config.get("Settings", "oauth", fallback=None)
        self.nick = config.get("Settings", "username", fallback=None)
        self.chan = "#" + config.get("Settings", "channel", fallback="twitch")
        self.prefix = config.get("Settings", "prefix", fallback="!")
        self.client_id = config.get("Settings", "client_id", fallback=None)

    def override(self, coro):
        """
        Decorator function to override events.

        .. code-block:: python

            @bot.override
            async def event_message(message):
                print(message.content)

        """
        if 'event' not in coro.__name__:
            raise Exception(
                "Accepted overrides start with 'event_' or 'raw_event'")
        setattr(self, coro.__name__, coro)

    @asyncio.coroutine
    def _get_stats(self):
        """ Gets JSON from the Kraken API """
        if not aio_installed:
            return

        global emotes
        emotes = (yield from _get_url(
            self.loop,
            "https://twitchemotes.com/api_cache/v2/global.json"))['emotes']

        if not self.client_id:
            return

        while True:
            try:
                for c in self.chan:
                    j = yield from _get_url(
                        self.loop,
                        'https://api.twitch.tv/kraken/channels/{}?client_id={}'
                        .format(c[1:], self.client_id))
                    self.channel_stats[c] = {
                        'mature': j['mature'],
                        'title': j['status'],
                        'game': j['game'],
                        'id': j['_id'],
                        'created_at': time.mktime(
                            time.strptime(
                                j['created_at'],
                                '%Y-%m-%dT%H:%M:%SZ')),
                        'updated_at': time.mktime(
                            time.strptime(
                                j['updated_at'],
                                '%Y-%m-%dT%H:%M:%SZ')),
                        'delay': j['delay'],
                        'offline_logo': j['video_banner'],
                        'profile_picture': j['logo'],
                        'profile_banner': j['profile_banner'],
                        'twitch_partner': j['partner'],
                        'views': j['views'],
                        'followers': j['followers']}

                    j = yield from _get_url(
                        self.loop,
                        'https://tmi.twitch.tv/hosts?target={}&include_logins=1'
                        .format(j['_id']))
                    self.host_count[c] = len(j['hosts'])
                    self.hosts[c] = [x['host_login'] for x in j['hosts']]

                    j = yield from _get_url(
                        self.loop,
                        'https://tmi.twitch.tv/group/user/{}/chatters'
                        .format(c[1:]))
                    self.viewer_count[c] = j['chatter_count']
                    self.channel_moderators[c] = j['chatters']['moderators']
                    self.viewers[c]['viewers'] = j['chatters']['viewers']
                    self.viewers[c]['moderators'] = j['chatters']['moderators']
                    self.viewers[c]['staff'] = j['chatters']['staff']
                    self.viewers[c]['admins'] = j['chatters']['admins']
                    self.viewers[c]['global_moderators'] = j[
                        'chatters']['global_mods']

            except Exception:
                traceback.print_exc()
            yield from asyncio.sleep(60)

    def start(self, tasked=False):
        """
        Starts the bot.
        
        Parameters
        ----------
        tasked : Optional[bool]
            Creates a task on the bot loop if True. (default: False)
        """
        if self.client_id is not None:
            self.loop.create_task(self._get_stats())

        if tasked:
            self.loop.create_task(self._tcp_echo_client())
        else:
            self.loop.run_until_complete(self._tcp_echo_client())

    @asyncio.coroutine
    def _pong(self, src):
        """ Tell remote we're still alive """
        self.writer.write("PONG {}\r\n".format(src).encode('utf-8'))

    @asyncio.coroutine
    @ratelimit_wrapper
    def say(self, channel, message):
        """
        Send a message to the specified channel.
        
        Parameters
        ----------
        channel : str
            The channel to send the message to.
        message : str
            The message to send.
        """

        if len(message) > 500:
            raise Exception(
                "The maximum amount of characters in one message is 500,"
                " you tried to send {} characters".format(
                    len(message)))

        while message.startswith("."):  # Use Bot.ban, Bot.timeout, etc instead
            message = message[1:]

        yield from self._send_privmsg(channel, message)

    @asyncio.coroutine
    def _nick(self):
        """ Send name """
        self.writer.write("NICK {}\r\n".format(self.nick).encode('utf-8'))

    @asyncio.coroutine
    def _pass(self):
        """ Send oauth token """
        self.writer.write("PASS {}\r\n".format(self.oauth).encode('utf-8'))

    @asyncio.coroutine
    def _join(self, channel):
        """ Join a channel """
        self.writer.write("JOIN {}\r\n".format(channel).encode('utf-8'))

    @asyncio.coroutine
    def _part(self, channel):
        """ Leave a channel """
        self.writer.write("PART #{}\r\n".format(channel).encode('utf-8'))

    @asyncio.coroutine
    def _special(self, mode):
        """ Allows for more events """
        self.writer.write(
            bytes("CAP REQ :twitch.tv/{}\r\n".format(mode), "UTF-8"))

    @asyncio.coroutine
    def _cache(self, message):
        self.messages.append(message)
        if len(self.messages) > self.cache_length:
            self.messages.pop(0)

    @asyncio.coroutine
    def _send_privmsg(self, channel, s):
        """ DO NOT USE THIS YOURSELF OR YOU RISK GETTING BANNED FROM TWITCH """
        s = s.replace("\n", " ")
        self.writer.write("PRIVMSG #{} :{}\r\n".format(
            channel, s).encode('utf-8'))

    # The following are Twitch commands, such as /me, /ban and /host, so I'm
    # not going to put docstrings on these

    # TODO Commands:
    # /cheerbadge /commercial

    @asyncio.coroutine
    @ratelimit_wrapper
    def ban(self, user, reason=''):
        """
        Ban a user.
        
        Parameters
        ----------
        user : :class:`User`
            The user to ban.
        reason : Optional[str]
            The reason a user was banned.
        """
        yield from self._send_privmsg(user.channel, ".ban {} {}".format(user.name, reason))

    @asyncio.coroutine
    @ratelimit_wrapper
    def unban(self, user):
        """
        Unban a banned user
        
        Parameters
        ----------
        user : :class:`User`
            The user to unban.
        """
        yield from self._send_privmsg(user.channel, ".unban {}".format(user.name))

    @asyncio.coroutine
    @ratelimit_wrapper
    def timeout(self, user, seconds=600, reason=''):
        """
        Timeout a user.
        
        Parameters
        ----------
        user : :class:`User`
            The user to time out.
        seconds : Optional[int]
            The amount of seconds to timeout for.
        reason : Optional[str]
            The reason a user was timed out.
        """
        yield from self._send_privmsg(user.channel, ".timeout {} {} {}".format(
                                                                 user.name, seconds,
                                                                 reason))

    @asyncio.coroutine
    @ratelimit_wrapper
    def me(self, channel, text):
        """
        The /me command.
        
        Parameters
        ----------
        channel : str
            The channel to use /me in.
        text : str
            The text to use in /me.
        """
        yield from self._send_privmsg(channel, ".me {}".format(text))

    @asyncio.coroutine
    @ratelimit_wrapper
    def whisper(self, user, message):
        """
        Send a private message to a user
        
        Parameters
        ----------
        user : :class:`User`
            The user to send a message to.
        message : str
            The message to send.
        """
        yield from self._send_privmsg(user.channel, ".w {} {}".format(user.name, msg))

    @asyncio.coroutine
    @ratelimit_wrapper
    def color(self, color):
        """
        Change the bot's color
        
        Parameters
        ----------
        user : :class:`Color`
            The color to use.
        """
        yield from self._send_privmsg(self.chan[0], ".color {}".format(color))

    @asyncio.coroutine
    def colour(self, colour):
        """
        See `bot.color`
        """
        yield from self.color(colour)

    @asyncio.coroutine
    @ratelimit_wrapper
    def mod(self, user):
        """
        Give moderator status to a user.
        
        Parameters
        ----------
        user : :class:`User`
            The user to give moderator.
        """
        yield from self._send_privmsg(user.channel, ".mod {}".format(user.name))

    @asyncio.coroutine
    @ratelimit_wrapper
    def unmod(self, user):
        """
        Remove moderator status from a user.
        
        Parameters
        ----------
        user : :class:`User`
            The user to remove moderator from.
        """
        yield from self._send_privmsg(user.channel, ".unmod {}".format(user.name))

    @asyncio.coroutine
    @ratelimit_wrapper
    def clear(self, channel):
        """
        Clear a channel.
        
        Parameters
        ----------
        channel : str
            The channel to clear.
        """
        yield from self._send_privmsg(channel, ".clear")

    @asyncio.coroutine
    @ratelimit_wrapper
    def subscribers_on(self, channel):
        """
        Set channel mode to subscribers only.
        
        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        yield from self._send_privmsg(channel, ".subscribers")

    @asyncio.coroutine
    @ratelimit_wrapper
    def subscribers_off(self, channel):
        """
        Unset channel mode to subscribers only.
        
        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        yield from self._send_privmsg(channel, ".subscribersoff")

    @asyncio.coroutine
    @ratelimit_wrapper
    def slow_on(self, channel):
        """
        Set channel mode to slowmode.
        
        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        yield from self._send_privmsg(channel, ".slow")

    @asyncio.coroutine
    @ratelimit_wrapper
    def slow_off(self, channel):
        """
        Unset channel mode to slowmode.
        
        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        yield from self._send_privmsg(channel, ".slowoff")

    @asyncio.coroutine
    @ratelimit_wrapper
    def r9k_on(self, channel):
        """
        Set channel mode to r9k.
        
        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        yield from self._send_privmsg(channel, ".r9k")

    @asyncio.coroutine
    @ratelimit_wrapper
    def r9k_off(self, channel):
        """
        Unset channel mode to r9k.
        
        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        yield from self._send_privmsg(channel, ".r9koff")

    @asyncio.coroutine
    @ratelimit_wrapper
    def emote_only_on(self, channel):
        """
        Set channel mode to emote-only.
        
        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        yield from self._send_privmsg(channel, ".emoteonly")

    @asyncio.coroutine
    @ratelimit_wrapper
    def emote_only_off(self, channel):
        """
        Unset channel mode to emote-only.
        
        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        yield from self._send_privmsg(channel, ".emoteonlyoff")

    @asyncio.coroutine
    @ratelimit_wrapper
    def host(self, channel, user):
        """
        Start hosting a channel.
        
        Parameters
        ----------
        channel : str
            The channel that will be hosting.
        user : str
            The channel to host.
        """
        yield from self._send_privmsg(channel, ".host {}".format(user))

    @asyncio.coroutine
    @ratelimit_wrapper
    def unhost(self, channel):
        """
        Stop hosting a channel.
        
        Parameters
        ----------
        channel : str
            The channel that was hosting.
        """
        yield from self._send_privmsg(channel, ".unhost")

    # End of Twitch commands

    @asyncio.coroutine
    def _tcp_echo_client(self):
        """ Receive events and trigger events """

        self.reader, self.writer = yield from asyncio.open_connection(
            self.host, self.port, loop=self.loop)

        if not self.nick.startswith('justinfan'):
            yield from self._pass()
        yield from self._nick()

        modes = ("commands", "tags", "membership")
        for m in modes:
            yield from self._special(m)

        for c in self.chan:
            yield from self._join(c)

        while True:
            rdata = (yield from self.reader.readline()).decode("utf-8").strip()

            if not rdata:
                continue

            yield from self.raw_event(rdata)

            try:

                if rdata.startswith("PING"):
                    p = self.regex["ping"]

                else:
                    p = self.regex["data"]

                m = p.match(rdata)

                try:
                    tags = m.group("tags")

                    tagdict = {}
                    for tag in tags.split(";"):
                        t = tag.split("=")
                        if t[1].isnumeric():
                            t[1] = int(t[1])
                        tagdict[t[0]] = t[1]
                    tags = tagdict
                except:
                    tags = None

                try:
                    action = m.group("action")
                except:
                    action = "PING"

                try:
                    data = m.group("data")
                except:
                    data = None

                try:
                    content = m.group('content')
                except:
                    content = None

                try:
                    channel = m.group('channel')
                except:
                    channel = None

            except:
                pass

            else:
                try:
                    if not action:
                        continue

                    if action == "PING":
                        yield from self._pong(content)

                    elif action == "PRIVMSG":
                        sender = self.regex["author"].match(
                            data).group("author")

                        messageobj = Message(content, sender, channel, tags)

                        yield from self._cache(messageobj)

                        yield from self.event_message(messageobj)

                    elif action == "WHISPER":
                        sender = self.regex["author"].match(
                            data).group("author")

                        messageobj = Message(content, sender, channel, tags)

                        yield from self._cache(messageobj)

                        yield from self.event_private_message(messageobj)

                    elif action == "JOIN":
                        sender = self.regex["author"].match(
                            data).group("author")

                        yield from self.event_user_join(User(sender, channel))

                    elif action == "PART":
                        sender = self.regex["author"].match(
                            data).group("author")

                        yield from self.event_user_leave(User(sender, channel))

                    elif action == "MODE":

                        m = self.regex["mode"].match(content)
                        mode = m.group("mode")
                        user = m.group("user")

                        if mode == "+":
                            yield from self.event_user_op(User(user, channel))
                        else:
                            yield from self.event_user_deop(User(user, channel))

                    elif action == "USERSTATE":

                        if tags["mod"] == 1:
                            self.is_mod = True
                        else:
                            self.is_mod = False

                        yield from self.event_userstate(User(self.nick, channel, tags))

                    elif action == "ROOMSTATE":
                        yield from self.event_roomstate(channel, tags)

                    elif action == "NOTICE":
                        yield from self.event_notice(channel, tags)

                    elif action == "CLEARCHAT":
                        if not content:
                            yield from self.event_clear(channel)
                        else:
                            if "ban-duration" in tags.keys():
                                yield from self.event_timeout(
                                    User(content, channel), tags)
                            else:
                                yield from self.event_ban(
                                    User(content, channel), tags)

                    elif action == "HOSTTARGET":
                        m = self.regex["host"].match(content)
                        hchannel = m.group("channel")
                        viewers = m.group("count")

                        if channel == "-":
                            yield from self.event_host_stop(channel, viewers)
                        else:
                            yield from self.event_host_start(channel, hchannel, viewers)

                    elif action == "USERNOTICE":
                        message = content or ""
                        user = tags["login"]

                        yield from self.event_subscribe(
                            Message(message, user, channel, tags), tags)

                    elif action == "CAP":
                        # We don"t need this for anything, so just ignore it
                        continue

                    else:
                        print("Unknown event:", action)
                        print(rdata)

                except Exception as e:
                    yield from self.parse_error(e)

    # Events called by TCP connection

    @asyncio.coroutine
    def event_notice(self, tags):
        """
        Called on NOTICE events (when commands are called).
        """
        pass

    @asyncio.coroutine
    def event_clear(self, channel):
        """
        Called when chat is cleared by someone else.
        """
        pass

    @asyncio.coroutine
    def event_subscribe(self, message, tags):
        """
        Called when someone (re-)subscribes.
        """
        pass

    @asyncio.coroutine
    def event_host_start(self, channel, hosted_channel, viewer_count):
        """
        Called when the streamer starts hosting.
        """
        pass

    @asyncio.coroutine
    def event_host_stop(self, channel, viewercount):
        """
        Called when the streamer stops hosting.
        """
        pass

    @asyncio.coroutine
    def event_ban(self, user, tags):
        """
        Called when a user is banned.
        """
        pass

    @asyncio.coroutine
    def event_timeout(self, user, tags):
        """
        Called when a user is timed out.
        """
        pass

    @asyncio.coroutine
    def event_roomstate(self, channel, tags):
        """
        Triggered when a channel's chat settings change.
        """
        pass

    @asyncio.coroutine
    def event_userstate(self, user):
        """
        Triggered when the bot sends a message.
        """
        pass

    @asyncio.coroutine
    def raw_event(self, data):
        """
        Called on all events after event_ready.
        """
        pass

    @asyncio.coroutine
    def event_user_join(self, user):
        """
        Called when a user joins a channel.
        """
        pass

    @asyncio.coroutine
    def event_user_leave(self, user):
        """
        Called when a user leaves a channel.
        """
        pass

    @asyncio.coroutine
    def event_user_deop(self, user):
        """
        Called when a user is de-opped.
        """
        pass

    @asyncio.coroutine
    def event_user_op(self, user):
        """
        Called when a user is opped.
        """
        pass

    @asyncio.coroutine
    def event_private_message(self, message):
        """
        Called when the bot receives a private message.
        """
        pass

    @asyncio.coroutine
    def event_message(self, message):
        """
        Called when a message is sent by someone in chat.
        """
        pass

    # End of events

    def stop(self, exit=False):
        """
        Stops the bot and disables using it again.
        
        Parameters
        ----------
        exit : Optional[bool]
            If True, this will close the event loop and raise SystemExit. (default: False)
        """

        if hasattr(self, "player"):
            self.player.terminate()

        if hasattr(self, "writer"):
            self.writer.close()

        pending = asyncio.Task.all_tasks()
        gathered = asyncio.gather(*pending)

        try:
            gathered.cancel()
            self.loop.run_until_complete(gathered)
            gathered.exception()
        except:  # Can be ignored
            pass

        if exit:
            self.loop.stop()
            sys.exit(0)

    @asyncio.coroutine
    def play_file(self, file):
        """
        Plays an audio file
        For this to work, ffplay, ffmpeg and ffprobe are required.
        These are downloadable from the ffmpeg website,
        and have to be in the same folder as the bot OR added to path.
        
        Parameters
        ----------
        file : str
            Filename of the file to play.
        """
        if self.song.is_playing:
            raise Exception("Already playing a song!")

        j = yield from self.loop.run_in_executor(
            None, subprocess.check_output, ["ffprobe", "-v", "-8",
                                            "-print_format", "json",
                                            "-show_format", file])

        j = json.loads(j.decode().strip())
        try:
            t = math.ceil(float(j["format"]["duration"])) + 2
        except:
            # Song is a stream
            if not self.allow_streams:
                return
            else:
                # TODO: Find a way to play streams, pass for now
                pass
        else:
            if self.song == Song():
                self.song.setattrs({
                    'title': ' '.join(file.split('.')[:-1]),
                    'duration': t})
            asyncio.ensure_future(self.song._play(file))

    @asyncio.coroutine
    def play_ytdl(self, query, *, filename="song.mp3", options={}, play=True):
        """
        Play a song using youtube_dl
        
        This requires youtube_dl to be installed
        `pip install youtube_dl`
        
        Parameters
        ----------
        query : str
            The text to search for or the url to play
        filename : Optional[str]
            The temporary filename to use. This file will be removed once done playing. (default: "song.mp3")
        options : Optional[dict]
            The arguments to pass to the YoutubeDL constructor.
        play : Optional[bool]
            Automatically plays the song if True. If False, this will return a :class:`Song` object. (default: True)
        """
        import youtube_dl

        args = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "audioformat": "mp3",
            "default_search": "auto",
            "noprogress": True,
            "outtmpl": filename
        }
        args.update(options)
        ytdl = youtube_dl.YoutubeDL(args)
        func = functools.partial(ytdl.extract_info, query, download=play)
        info = yield from self.loop.run_in_executor(None, func)
        try:
            info = info['entries'][0]
        except:
            pass
        song = Song()
        song.setattrs(info)
        if play:
            self.song = song
            yield from self.play_file(filename)
        else:
            return song

    @asyncio.coroutine
    def parse_error(self, e):
        """
        Called when something errors.
        """

        fname = e.__traceback__.tb_next.tb_frame.f_code.co_name
        print("Ignoring exception in {}:".format(fname))
        traceback.print_exc()


class CommandBot(Bot):
    """
    Allows the usage of Commands more easily
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands = {}
        self.playlist = []
        self.playing = None

    @asyncio.coroutine
    def event_message(self, m):
        """
        If you override this function, make sure to yield from/await `CommandBot.parse_commands`
        """
        yield from self.parse_commands(m)

    @asyncio.coroutine
    def parse_commands(self, rm):
        """
        The command parser. It is not recommended to override this.
        """

        if self.nick == rm.author.name:
            return

        if rm.content.startswith(self.prefix):

            m = rm.content[len(self.prefix):]
            cl = m.split(" ")
            w = cl.pop(0).lower().replace("\r", "")
            m = " ".join(cl)

            if w in self.commands:
                if not self.commands[w].unprefixed:
                    if self.commands[
                            w].admin and rm.author.name not in self.admins:
                        yield from self.say(
                            "You are not allowed to use this command")
                    yield from self.commands[w].run(rm)

        else:
            cl = rm.content.split(" ")
            w = cl.pop(0).lower()

            if w in self.commands:
                if not self.commands[w].unprefixed:
                    yield from self.commands[w].run(rm)

    def command(*args, **kwargs):
        """
        A decorator to add a command.
        see :ref:`Command` for usage.
        """
        return Command(*args, **kwargs)

    def add_timer(self, channel, message, time=60):
        """
        Send a message on a timer.
        
        Parameters
        ----------
        channel : str
            The channel to send the message to.
        message: str
            The message to send.
        time : Optional[int]
            The interval to send the message. (default: 60)
        """
        t = create_timer(message, time)
        self.loop.create_task(t(self))


class CurrencyBot(Bot):
    """ A Bot with support for currency """

    def __init__(self, *args, points_database='points.db',
                 currency='gold', **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_name = currency
        self.currency_database_name = points_database
        if not pathlib.Path(points_database).is_file():
            _setup_points_db(points_database)
        self.currency_database = sqlite3.connect(points_database)
        self.currency_cursor = self.currency_database.cursor()

    def check_user_currency(self, user):
        """ Check if the user is already in the database """
        return bool(list(self.currency_cursor.execute(
            "SELECT * FROM currency WHERE username = ?", (user,))))

    def add_user_currency(self, user):
        self.currency_cursor.execute(
            "INSERT INTO currency VALUES (?,0)", (user,))

    def add_currency(self, user, amount):
        balance = self.get_currency(user)[0]
        self.currency_cursor.execute(
            "UPDATE currency SET balance = ? WHERE username = ?",
            (balance + amount, user))

    def remove_currency(self, user, amount, force_remove=False):
        balance = self.get_currency(user)[0]
        if amount > balance and not force_remove:
            raise Exception(
                "{} owns {} {0.currency_name}, unable to remove {}."
                "Use force_remove=True to force this action.".format(
                    user, balance, self, amount))
        self.currency_cursor.execute(
            "UPDATE currency SET balance = ? WHERE username = ?",
            (balance - amount, user))

    def get_currency(self, user):
        entry = list(self.currency_cursor.execute(
            "SELECT balance FROM currency WHERE username = ?", (user,)))
        return entry[0]

    def save_currency_database(self):
        self.currency_database.commit()

    def reset_currency_database(self):
        self.currency_cursor.execute("DROP TABLE currency")
        _setup_points_db(self.currency_database_name)

    def undo_currency_database_changes(self):
        self.currency_database.rollback()


class ViewTimeBot(Bot):
    """ A Bot to track view time """

    def __init__(self, *args, time_database='time.db', **kwargs):
        super().__init__(*args, **kwargs)
        if not aio_installed:
            raise Exception("ViewTimeBot requires aiohttp to be installed!")
        self.time_database_name = time_database
        if not pathlib.Path(time_database).is_file():
            _setup_time_db(time_database)
        self.time_database = sqlite3.connect(time_database)
        self.time_cursor = self.time_database.cursor()
        self.loop.create_task(self.collect_task())

    @asyncio.coroutine
    def collect_task(self):
        yield from asyncio.sleep(10)
        while True:
            yield from asyncio.sleep(60)
            users = []
            for group in self.viewers.values():
                for viewer in group:
                    if not self.check_user_time(viewer):
                        self.add_user_time(viewer)
                    self.add_time(viewer, 60)
                    users.append(viewer)
            self.save_time_database()
            yield from self.event_viewtime_update(users)

    @asyncio.coroutine
    def event_viewtime_update(self, users):
        pass

    def check_user_time(self, user):
        """ Check if the user is already in the database """
        return bool(list(self.time_cursor.execute(
            "SELECT * FROM time_watched WHERE username = ?", (user,))))

    def add_user_time(self, user):
        self.time_cursor.execute(
            "INSERT INTO time_watched VALUES (?,0)", (user,))

    def add_time(self, user, amount):
        time = self.get_time(user)[0]
        self.time_cursor.execute(
            "UPDATE time_watched SET time = ? WHERE username = ?",
            (time + amount, user))

    def remove_time(self, user, amount, force_remove=False):
        time = self.get_time(user)
        if amount > time:
            amount = time
        self.time_cursor.execute(
            "UPDATE time_watched SET time = ? WHERE username = ?",
            (time - amount, user))

    def get_time(self, user):
        entry = list(self.time_cursor.execute(
            "SELECT time FROM time_watched WHERE username = ?", (user,)))
        return entry[0]

    def save_time_database(self):
        self.time_database.commit()

    def reset_time_database(self):
        self.time_cursor.execute("DROP TABLE time_watched")
        _setup_time_db(self.time_database_name)

    def undo_time_database_changes(self):
        self.time_database.rollback()


class RankedBot(ViewTimeBot, CurrencyBot):
    """ A Bot with ranks """

    def __init__(self, *args, ranks_database='ranks.db',
                 points_per_minute=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.autopoints = points_per_minute
        self.ranks_database_name = ranks_database
        if not pathlib.Path(ranks_database).is_file():
            _setup_ranks_db(ranks_database)
        self.rank_database = sqlite3.connect(ranks_database)
        self.rank_cursor = self.rank_database.cursor()

    def check_user_rank(self, user, rank):
        """ Check if the user is already in the database """
        return bool(list(self.time_cursor.execute(
            "SELECT * FROM user_ranks WHERE username = ? AND rank = ?",
            (user, rank))))

    @asyncio.coroutine
    def autoset_user(self, user):
        if not self.check_user_currency(user):
            self.add_user_currency(user)
        bal = self.get_currency(user)[0]
        if not self.check_user_time(user):
            self.add_user_time(user)
        time = self.get_time(user)[0]
        new_rank = None
        for rank in list(self.rank_cursor.execute(
                "SELECT * FROM currency_ranks ORDER BY currency")):
            cur = rank[0]
            if cur <= bal:
                new_rank = rank[1]
        for rank in list(self.rank_cursor.execute(
                "SELECT * FROM watched_ranks ORDER BY time")):
            tim = rank[0]
            if tim <= time:
                new_rank = rank[1]
        if new_rank:
            if not self.check_user_rank(user, new_rank):
                self.rank_cursor.execute(
                    "DELETE FROM user_ranks WHERE user = ?", (user,))
                self.rank_cursor.execute(
                    "INSERT INTO user_ranks VALUES (?,?)", (user, new_rank))
            yield from self.event_rankup(user, new_rank)

    @asyncio.coroutine
    def event_rankup(self, user, rank):
        pass

    @asyncio.coroutine
    def event_viewtime_update(self, users):
        for user in users:
            if not self.check_user_currency(user):
                self.add_user_currency(user)
            self.add_currency(user, self.autopoints)
        self.save_currency_database()

    def add_rank(self, name, points=0, time_watched=0, type_rank='points'):
        if type_rank == 'points':
            self.rank_cursor.execute(
                "INSERT INTO currency_ranks VALUES (?,?)", (points, name))
        elif type_rank == 'time_watched':
            self.rank_cursor.execute(
                "INSERT INTO watched_ranks VALUES (?,?)",
                (time_watched, name))
        else:
            raise Exception(
                "Invalid rank type! valid types: 'points', 'time_watched'.")

    def save_rank_database(self):
        self.rank_database.commit()

    def reset_rank_database(self):
        self.rank_cursor.execute("DROP TABLE currency_ranks")
        self.rank_cursor.execute("DROP TABLE watched_ranks")
        self.rank_cursor.execute("DROP TABLE user_ranks")
        _setup_ranks_db(self.ranks_database_name)

    def undo_rank_database_changes(self):
        self.rank_database.rollback()
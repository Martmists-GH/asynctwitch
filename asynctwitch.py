import asyncio
import traceback
import sys
import os
import re
import inspect
import math
import json
import configparser
import time
import subprocess
import time
import functools
import sqlite3

# Test if they have aiohttp installed in case they didn't use setup.py
try:
    import aiohttp
    aio_installed = True
except ImportError:
    print("To use stats from the API, make sure to install aiohttp. (pip install aiohttp)")
    aio_installed = False
    
try:
    import isodate
    iso_installed = True
except ImportError:
    print("To use music, please install isodate. (pip install isodate)")
    iso_installed = False

def _setup_sql_db(file):
    open(file,'a').close()
    connection = sqlite3.connect(file)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE currency VALUES (username VARCHAR(30), balance INT)")
    connection.commit()
    connection.close()

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

def create_timer(message, time):
    @asyncio.coroutine
    def wrapper(self):
        while True:
            yield from asyncio.sleep(time)
            yield from self.say(message)
    return wrapper

def ratelimit_wrapper(coro):
    @asyncio.coroutine
    def wrapper(self, *args, **kwargs):
        max = 100 if self.is_mod else 20

        while self.message_count == max:
            yield from asyncio.sleep(1)

        self.message_count += 1
        r = yield from coro(self, *args, **kwargs)
        self.loop.call_later(20, _decrease_msgcount, self) # make sure it doesn't block the event loop
        return r
    return wrapper

class Color:
    """ Available colors for non-turbo users when using Bot.color """
    def __init__(self, value):
        if not value:
            value = 0
        elif isinstance(value, str):
            value = int(value.strip("#"), 16)
        self.value = value

    def _get_part(self, byte):
        return (self.value >> (8 * byte)) & 0xff

    def __eq__(self, clr):
        return isinstance(clr, Color) and self.value == clr.value
    def __ne__(self, clr):
        return not self.__eq__(clr)
    def __str__(self):
        return '#{:0>6x}'.format(self.value)
    def __add__(self, clr):
        return Color.from_rgb((self.r+clr.r)/2, (self.g+clr.g)/2, (self.b+clr.b)/2)
        
    @property
    def r(self):
        return self._get_part(2)
    @property
    def g(self):
        return self._get_part(1)
    @property
    def b(self):
        return self._get_part(0)

    def get_tuple(self):
        """ Returns an (r, g, b) tuple of the color """
        return (self.r, self.g, self.b)

    @classmethod
    def blue(cls):
        return cls(0x0000FF)
    @classmethod
    def red(cls):
        return cls(0xFF0000)
    @classmethod
    def chocolate(cls):
        return cls(0xD2691E)
    @classmethod
    def green(cls):
        return cls(0x008000)
    @classmethod
    def hot_pink(cls):
        return cls(0xFF69B4)
    @classmethod
    def dodger_blue(cls):
        return cls(0x1E90FF)
    @classmethod
    def coral(cls):
        return cls(0xFF7F50)
    @classmethod
    def cadet_blue(cls):
        return cls(0x5F9EA0)
    @classmethod
    def firebrick(cls):
        return cls(0xB22222)
    @classmethod
    def blue_violet(cls):
        return cls(0x8A2BE2)
    @classmethod
    def golden_rod(cls):
        return cls(0xDAA520)
    @classmethod
    def orange_red(cls):
        return cls(0xFF4500)
    @classmethod
    def sea_green(cls):
        return cls(0x2E8B57)
    @classmethod
    def spring_green(cls):
        return cls(0x00FF7F)
    @classmethod
    def yellow_green(cls):
        return cls(0x9ACD32)
    @classmethod
    def from_rgb(cls, r, g, b):
        value = ((int(r) << 16) + (int(g) << 8) + int(b))
        return cls(value)

Colour = Color

class Song:
    """ Contains information about a mp3 file """
    def __init__(self):
        self.title = ""  # In case setattrs() isn't called
        self.is_playing = False

    def setattrs(self, obj):
        self.title = obj['title']
        try: # not available with play_file
            if isinstance(obj['duration'], str):
                self.duration = isodate.parse_duration(obj['duration']).total_seconds()
            else:
                self.duration = obj['duration']
            self.uploader = obj['uploader']
            self.description = obj['description']
            self.categories = obj['categories']
            self.views = obj['view_count']
            self.thumbnail = obj['thumbnail']
            self.id = obj['id']
            self.is_live = obj['is_live']
            self.likes = obj['like_count']
            self.dislikes = obj['dislike_count']
        except Exception:
            pass

    def __str__(self):
        return self.title
        
    @asyncio.coroutine
    def _play(self, file, cleanup=True):
        if self.is_playing:
            raise Exception("Already playing!")
        self.is_playing = True
        yield from asyncio.create_subprocess_exec("ffplay", "-nodisp", "-autoexit", "-v", "-8",
                                                  file, stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
        yield from asyncio.sleep(self.duration)
        self.is_playing = False
        if cleanup:
            os.remove(file)

class User:
    """ Custom author class """
    def __init__(self, a, tags=None):
        self.name = a
        if tags:
            self.badges = tags['badges']
            self.color = Color(tags['color'])
            self.mod = tags['mod']
            self.subscriber = tags['subscriber']
            self.type = tags['user-type']
            try:
                self.turbo = tags['turbo']
                self.id = tags['user-id']
            except:
                pass

class Message:
    """ Custom message object to combine message, author and timestamp """

    def __init__(self, m, a, tags):
        if tags:
            self.timestamp = tags['tmi-sent-ts']
            self.emotes = tags['emotes']
            self.id = tags['id']
            self.room_id = tags['room-id']
        self.content = m
        self.author = User(a, tags)
    def __str__(self):
        return self.content


class Command:
    """ A command class to provide methods we can use with it """

    def __init__(self, bot, comm, *, alias=None, desc="",
                 admin=False, unprefixed=False, listed=True):

        self.bot = bot
        self.comm = comm
        self.desc = desc
        self.alias = alias or []
        self.admin = admin
        self.listed = listed
        self.unprefixed = unprefixed
        self.subcommands = []
        bot.commands[comm] = self
        for a in self.alias:
            bot.commands[a] = self

    def subcommand(self, *args, **kwargs):
        """ Create subcommands """
        return SubCommand(self, *args, **kwargs)


    def __call__(self, func):
        """ Make it able to be a decorator """

        self.func = func

        return self


    @asyncio.coroutine
    def run(self, message):
        """ Does type checking for command arguments """

        args = message.content.split(" ")[1:]

        args_name = inspect.getfullargspec(self.func)[0][1:]

        if len(args) > len(args_name):
            args[len(args_name)-1] = " ".join(args[len(args_name)-1:])

            args = args[:len(args_name)]

        elif len(args) < len(args_name):
            raise Exception("Not enough arguments for {}, required arguments: {}"
                .format(self.comm, ", ".join(args_name)))

        ann = self.func.__annotations__

        for x in range(0, len(args_name)):
            v = args[x]
            k = args_name[x]

            if type(v) == ann[k]:
                pass

            else:
                try:
                    v = ann[k](v)

                except:
                    raise TypeError("Invalid type: got {}, {} expected"
                        .format(ann[k].__name__, v.__name__))

            args[x] = v

        if len(self.subcommands)>0:
            subcomm = args.pop(0)

            for s in self.subcommands:
                if subcomm == s.comm:
                    c = message.content.split(" ")
                    message.content = c[0] + " " + " ".join(c[2:])

                    yield from s.run(message)
                    break

        else:
            yield from self.func(message, *args)



class SubCommand(Command):
    """ Subcommand class """

    def __init__(self, parent, comm, *, desc=""):
        self.comm = comm
        self.parent = parent
        self.bot = parent.bot
        self.subcommands = []
        self.parent.subcommands.append(self)



class Bot:
    """ Bot class without command support """

    def __init__(self, *, oauth=None, user=None, channel="twitch",
                 prefix="!", admins=None, config=None, cache=100, 
                 client_id=None):

        if config:
            self.load(config)

        else:
            self.prefix = prefix
            self.oauth = oauth
            self.nick = user.lower()
            self.chan = "#" + channel.lower().strip('#')
            self.client_id = client_id

        if os.name == 'nt':
            self.loop = asyncio.ProactorEventLoop()
        else:
            self.loop = asyncio.get_event_loop()

        self.cache_length = cache

        asyncio.set_event_loop(self.loop)
        self.host = "irc.chat.twitch.tv"
        self.port = 6667

        self.admins = admins or []

        self.song = Song()
        self.is_mod = False
        self.is_playing = False

        self.message_count = 1 # Just in case some get sent almost simultaneously even though they shouldn't

        self.channel_stats = {}

        self.viewer_count = 0
        self.host_count = 0

        self.viewers = {}

        self.hosts = []

        self.messages = []
        self.channel_moderators = []

    def debug(self):
        for x, y in self.__dict__.items():
            print(x, y)

    def load(self, path):
        """ Loads settings from file """
        config = configparser.ConfigParser(interpolation=None)
        config.read(path)
        self.oauth = config.get("Settings", "oauth", fallback=None)
        self.nick = config.get("Settings", "username", fallback=None)
        self.chan = "#" + config.get("Settings", "channel", fallback="twitch")
        self.prefix = config.get("Settings", "prefix", fallback="!")
        self.client_id = config.get("Settings", "client_id", fallback=None)


    def override(self, coro):
        """ Allows for overriding certain functions """
        if not 'event' in coro.__name__:
            raise Exception("Accepted overrides start with 'event_' or 'raw_event'")
        setattr(self, coro.__name__, coro)

    @asyncio.coroutine
    def _get_stats(self):
        """ Gets JSON from the Kraken API """
        if not aio_installed or not self.client_id:
            return

        while True:
            try:
                j = yield from _get_url(self.loop, 'https://api.twitch.tv/kraken/channels/{}?client_id={}'.format(self.chan[1:], self.client_id))
                self.channel_stats = {
                    'mature':j['mature'],
                    'title':j['status'],
                    'game':j['game'],
                    'id':j['_id'],
                    'created_at':time.mktime(time.strptime(j['created_at'], '%Y-%m-%dT%H:%M:%SZ')),
                    'updated_at':time.mktime(time.strptime(j['updated_at'], '%Y-%m-%dT%H:%M:%SZ')),
                    'delay':j['delay'],
                    'offline_logo':j['video_banner'],
                    'profile_picture':j['logo'],
                    'profile_banner':j['profile_banner'],
                    'twitch_partner': j['partner'],
                    'views':j['views'],
                    'followers':j['followers']
                }

                j = yield from _get_url(self.loop, 'https://tmi.twitch.tv/hosts?target={}&include_logins=1'.format(j['_id']))
                self.host_count = len(j['hosts'])
                self.hosts = [x['host_login'] for x in j['hosts']]

                j = yield from _get_url(self.loop, 'https://tmi.twitch.tv/group/user/{}/chatters'.format(self.chan[1:]))
                self.viewer_count = j['chatter_count']
                self.channel_moderators = j['chatters']['moderators']
                self.viewers['viewers'] = j['chatters']['viewers']
                self.viewers['moderators'] = j['chatters']['moderators']
                self.viewers['staff'] = j['chatters']['staff']
                self.viewers['admins'] = j['chatters']['admins']
                self.viewers['global_moderators'] = j['chatters']['global_mods']

            except Exception:
                traceback.print_exc()
            yield from asyncio.sleep(120)

    def start(self):
        """ Starts the event loop, this blocks all other code below it from executing """
        if self.client_id is not None:
            self.loop.create_task(self._get_stats())
        self.loop.run_until_complete(self._tcp_echo_client())

    @asyncio.coroutine
    def _pong(self, src):
        """ Tell remote we're still alive """
        self.writer.write("PONG {}\r\n".format(src).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def say(self, msg):
        """ Send messages """
        msg = str(msg)

        if len(msg) > 500:
            raise Exception("The maximum amount of characters in one message is 500,"
                " you tried to send {} characters".format(len(msg)))

        while msg.startswith("."): # Use Bot.ban, Bot.timeout, etc instead
            msg = msg[1:]

        self.writer.write("PRIVMSG {} :{}\r\n".format(self.chan, msg).encode('utf-8'))


    @asyncio.coroutine
    def _nick(self):
        """ Send name """
        self.writer.write("NICK {}\r\n".format(self.nick).encode('utf-8'))


    @asyncio.coroutine
    def _pass(self):
        """ Send oauth token """
        self.writer.write("PASS {}\r\n".format(self.oauth).encode('utf-8'))


    @asyncio.coroutine
    def _join(self):
        """ Join a channel """
        self.writer.write("JOIN {}\r\n".format(self.chan).encode('utf-8'))


    @asyncio.coroutine
    def _part(self):
        """ Leave a channel """
        self.writer.write("PART {}\r\n".format(self.chan).encode('utf-8'))


    @asyncio.coroutine
    def _special(self, mode):
        """ Allows for more events """
        self.writer.write(bytes("CAP REQ :twitch.tv/{}\r\n".format(mode),"UTF-8"))

    @asyncio.coroutine
    def _cache(self, message):
        self.messages.append(message)
        if len(self.messages) > self.cache_length:
            self.messages.pop(0)

    # The following are Twitch commands, such as /me, /ban and /host, so I'm not going to put docstrings on these

    # TODO Commands:
    # /cheerbadge /commercial

    @ratelimit_wrapper
    @asyncio.coroutine
    def ban(self, user, reason=''):
        self.writer.write("PRIVMSG {} :.ban {} {}\r\n".format(self.chan, user, reason).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unban(self, user):
        self.writer.write("PRIVMSG {} :.unban {}\r\n".format(self.chan, user).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def timeout(self, user, seconds=600, reason=''):
        self.writer.write(bytes("PRIVMSG {} :.timeout {} {} {}\r\n".format(self.chan, user,
                                                                       seconds, reason), "UTF-8"))

    @ratelimit_wrapper
    @asyncio.coroutine
    def me(self, text):
        self.writer.write("PRIVMSG {} :.me {}\r\n".format(self.chan, text).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def whisper(self, user, msg):
        msg = str(msg)
        self.writer.write("PRIVMSG {} :.w {} {}\r\n".format(self.chan, user, msg).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def color(self, color):
        self.writer.write("PRIVMSG {} :.color {}\r\n".format(self.chan, color).encode('utf-8'))

    @asyncio.coroutine
    def colour(self, colour):
        yield from self.color(colour)

    @ratelimit_wrapper
    @asyncio.coroutine
    def mod(self, user):
        self.writer.write("PRIVMSG {} :.mod {}\r\n".format(self.chan, user).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unmod(self, user):
        self.writer.write("PRIVMSG {} :.unmod {}\r\n".format(self.chan, user).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def clear(self):
        self.writer.write("PRIVMSG {} :.clear\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def subscribers_on(self):
        self.writer.write("PRIVMSG {} :.subscribers\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def subscribers_off(self):
        self.writer.write("PRIVMSG {} :.subscribersoff\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def slow_on(self):
        self.writer.write("PRIVMSG {} :.slow\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def slow_off(self):
        self.writer.write("PRIVMSG {} :.slowoff\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def r9k_on(self):
        self.writer.write("PRIVMSG {} :.r9k\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def r9k_off(self):
        self.writer.write("PRIVMSG {} :.r9koff\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def emote_only_on(self):
        self.writer.write("PRIVMSG {} :.emoteonly\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def emote_only_on(self):
        self.writer.write("PRIVMSG {} :.emoteonlyoff\r\n".format(self.chan).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def host(self, user):
        self.writer.write("PRIVMSG {} :.host {}\r\n".format(self.chan, user).encode('utf-8'))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unhost(self):
        self.writer.write("PRIVMSG {} :.unhost\r\n".format(self.chan).encode('utf-8'))

    # End of Twitch commands

    @asyncio.coroutine
    def _tcp_echo_client(self):
        """ Receive events and trigger events """

        self.reader, self.writer = yield from asyncio.open_connection(self.host, self.port,
                                                                      loop=self.loop)

        if not self.nick.startswith('justinfan'):
            yield from self._pass()
        yield from self._nick()

        modes = ("commands","tags","membership")
        for m in modes:
            yield from self._special(m)

        yield from self._join()

        while True:
            rdata = (yield from self.reader.readline()).decode("utf-8").strip()

            if not rdata:
                continue

            yield from self.raw_event(rdata)

            try:

                if rdata.startswith("PING"):
                    p = re.compile("PING (?P<content>.+)")
                    
                else:
                    p = re.compile(r"^(?:@(?P<tags>\S+)\s)?:(?P<data>\S+)(?:\s)(?P<action>[A-Z]+)(?:\s#)(?P<channel>\S+)(?:\s(?::)?(?P<content>.+))?")

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
                        sender = re.match("(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")


                        messageobj = Message(content, sender, tags)

                        yield from self._cache(messageobj)

                        yield from self.event_message(messageobj)

                    elif action == "WHISPER":
                        sender = re.match("(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")

                        messageobj = Message(content, sender, tags)

                        yield from self._cache(messageobj)

                        yield from self.event_private_message(messageobj)

                    elif action == "JOIN":
                        sender = re.match("(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")

                        yield from self.event_user_join(User(sender))

                    elif action == "PART":
                        sender = re.match("(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")

                        yield from self.event_user_leave(User(sender))

                    elif action == "MODE":

                        m = re.match("(?P<mode>[\+\-])o (?P<user>.+)",
                                     content)
                        mode = m.group("mode")
                        user = m.group("user")

                        if mode == "+":
                            yield from self.event_user_op(User(user))
                        else:
                            yield from self.event_user_deop(User(user))

                    elif action == "USERSTATE":

                        if tags["mod"] == 1:
                            self.is_mod = True
                        else:
                            self.is_mod = False

                        yield from self.event_userstate(User(self.nick, tags))

                    elif action == "ROOMSTATE":
                        yield from self.event_roomstate(tags)

                    elif action == "NOTICE":
                        yield from self.event_notice(tags)

                    elif action == "CLEARCHAT":
                        if not content:
                            yield from self.event_clear()
                        else:
                            if "ban-duration" in tags.keys():
                                yield from self.event_timeout(User(content), tags)
                            else:
                                yield from self.event_ban(User(content), tags)

                    elif action == "HOSTTARGET":
                        m = re.match("(?P<channel>[a-zA-Z0-9_]+) (?P<count>[0-9\-]+)",
                                      content)
                        channel = m.group("channel")
                        viewers = m.group("count")

                        if channel == "-":
                            yield from self.event_host_stop(viewers)
                        else:
                            yield from self.event_host_start(channel, viewers)

                    elif action == "USERNOTICE":
                        message = content or ""
                        user = tags["login"]

                        yield from self.event_subscribe(Message(message, user, tags), tags)

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
        """ Called on NOTICE events (when commands are called) """
        pass

    @asyncio.coroutine
    def event_clear(self):
        """ Called when chat is cleared normally """
        pass

    @asyncio.coroutine
    def event_subscribe(self, message, tags):
        """ Called when someone (re-)subscribes. """
        pass

    @asyncio.coroutine
    def event_host_start(self, channel, viewercount):
        """ Called when the streamer starts hosting. """
        pass


    @asyncio.coroutine
    def event_host_stop(self, viewercount):
        """ Called when the streamer stops hosting. """
        pass


    @asyncio.coroutine
    def event_ban(self, user, tags):
        """ Called when a user is banned. """
        pass


    @asyncio.coroutine
    def event_timeout(self, user, tags):
        """ Called when a user is timed out. """
        pass


    @asyncio.coroutine
    def event_roomstate(self, tags):
        """
        Triggered when channel chat settings change.

        Example of what `tags` returns:

        {
            "emote-only": 0
        }
        """
        pass



    @asyncio.coroutine
    def event_userstate(self, User):
        """ Triggered when the bot sends a message. """
        pass


    @asyncio.coroutine
    def raw_event(self, data):
        """ Called on all events after event_ready """
        pass


    @asyncio.coroutine
    def event_user_join(self, user):
        """ Called when a user joins """
        pass


    @asyncio.coroutine
    def event_user_leave(self, user):
        """ Called when a user leaves """
        pass


    @asyncio.coroutine
    def event_user_deop(self, user):
        """ Called when a user is de-opped """
        pass


    @asyncio.coroutine
    def event_user_op(self, user):
        """ Called when a user is opped """
        pass

    @asyncio.coroutine
    def event_private_message(self, rm):
        """ Called on a private message """
        pass

    @asyncio.coroutine
    def event_message(self, rm):
        """ Called when a message is sent """
        pass

    # End of events

    def stop(self, exit=False):
        """
        Stops the bot and disables using it again.
        Useful for a restart command I guess
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
        except: # Can be ignored
            pass
        
        self.loop.stop()
        
        if exit:
            os._exit(0)

    @asyncio.coroutine
    def play_file(self, file):
        """
        Plays audio.
        For this to work, ffplay, ffmpeg and ffprobe, downloadable from the ffmpeg website,
        have to be in the same folder as the bot OR added to path.
        """
        if self.song.is_playing:
            raise Exception("Already playing a song!")

        j = yield from self.loop.run_in_executor(None, subprocess.check_output,
                                                 [
                                                     "ffprobe", "-v", "-8", "-print_format",
                                                     "json", "-show_format", file
                                                 ])

        j = json.loads(j.decode().strip())
        t = math.ceil( float( j["format"]["duration"] ) ) + 2
        if self.song == Song():
            self.song.setattrs({
                'title': ' '.join(file.split('.')[:-1]),
                'duration': t
            })
        asyncio.ensure_future(self.song._play(file))

    @asyncio.coroutine
    def play_ytdl(self, query, *, filename="song.flac", options={}):
        """
        Requires youtube_dl to be installed
        `pip install youtube_dl`
        """
        if self.is_playing:
            raise Exception("Already playing a song!")

        import youtube_dl

        args = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "audioformat": "flac",
            "default_search": "auto",
            "noprogress": True,
            "outtmpl": filename
        }
        args.update(options)
        ytdl = youtube_dl.YoutubeDL(args)
        func = functools.partial(ytdl.extract_info, query)
        info = yield from self.loop.run_in_executor(None, func)
        try:
            info = info['entries'][0]
        except:
            pass
        self.song = Song()
        self.song.setattrs(info)
        yield from self.play_file(filename)


    @asyncio.coroutine
    def parse_error(self, e):
        """ Called when something errors """

        fname = e.__traceback__.tb_next.tb_frame.f_code.co_name
        print("Ignoring exception in {}:".format(fname))
        traceback.print_exc()



class CommandBot(Bot):
    """ Allows the usage of Commands more easily """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands = {}
        self.playlist = []
        self.playing = None

    @asyncio.coroutine
    def event_message(self, m):
        yield from self.parse_commands(m)

    @asyncio.coroutine
    def parse_commands(self, rm):
        """ Shitty command parser I made """

        if self.nick == rm.author.name: return

        if rm.content.startswith(self.prefix):

            m = rm.content[len(self.prefix):]
            cl = m.split(" ")
            w = cl.pop(0).lower().replace("\r","")
            m = " ".join(cl)

            if w in self.commands:
                if not self.commands[w].unprefixed:
                    if self.commands[w].admin and not rm.author.name in self.admins:
                        yield from self.say("You are not allowed to use this command")
                    yield from self.commands[w].run(rm)

        else:
            cl = rm.content.split(" ")
            w = cl.pop(0).lower()

            if w in self.commands:
                if not self.commands[w].unprefixed:
                    yield from self.commands[w].run(rm)

    def command(*args, **kwargs):
        """ Add a command """
        return Command(*args, **kwargs)

    def add_timer(self, message, time=60):
        t = create_timer(message, time)
        self.loop.create_task(t(self))

    @asyncio.coroutine
    def play_list(self, l):
        """ play songs from a list using play_ytdl """
        # Broken

        self.playlist = l
        while self.playlist:
            if not self.is_playing:
                song = self.playlist.pop(0)
                self.playing = song
                yield from self.play_ytdl(song)

class CurrencyBot(Bot):
    """ A CommandBot with support for currency """
    def __init__(self, *args, database='points.db', currency='gold', **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_name = currency
        if not os.pathlib.is_file(database):
            _setup_sqlite_db()
        self.database = sqlite3.connect(database)
        self.cursor = self.database.cursor()

    def add_user(self, user):
        self.cursor.execute("INSERT INTO currency VALUES (?,0)", (user,))

    def add_currency(self, user, amount):
        for entry in self.cursor.execute("SELECT balance FROM currency WHERE username = ?", (user,)):
            # should be just one since usernames are unique
            balance = entry[0]
        self.cursor.execute("UPDATE currency SET balance = ? WHERE username = ?", (balance+amount, user))

    def remove_currency(self, user, amount, force_remove=False):
        for entry in self.cursor.execute("SELECT balance FROM currency WHERE username = ?", (user,)):
            # should be just one since usernames are unique
            balance = entry[0]
        if amount > balance and force_remove:
            raise Exception("{} owns {} {0.currency_name}, unable to remove {}."
                            "Use force_remove=True to force this action.".format(user, balance, self, amount))
        self.cursor.execute("UPDATE currency SET balance = ? WHERE username = ?", (balance-amount, user))

    def save_database(self):
        self.database.commit()

    def reset_database(self):
        self.cursor.execute("DROP TABLE currency")
        _setup_sqlite_db()

    def undo_database_changes(self):
        self.database.rollback()
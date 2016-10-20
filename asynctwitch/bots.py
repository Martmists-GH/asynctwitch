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
    print("To use stats from the API, make sure to install aiohttp. (pip install aiohttp)")
    aio_installed = False

def _setup_points_db(file):
    open(file,'a').close()
    connection = sqlite3.connect(file)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE currency VALUES (username VARCHAR(30), balance INT)")
    connection.commit()
    connection.close()

def _setup_ranks_db(file):
    open(file,'a').close()
    connection = sqlite3.connect(file)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE user_ranks VALUES (username VARCHAR(30), rankname TEXT)")
    cursor.execute("CREATE TABLE currency_ranks VALUES (currency INT, rankname TEXT)")
    cursor.execute("CREATE TABLE watched_ranks VALUES (time INT, rankname TEXT)")
    connection.commit()
    connection.close()

def _setup_time_db(file):
    open(file,'a').close()
    connection = sqlite3.connect(file)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE time_watched VALUES (username VARCHAR(30), time INT)")
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
        if not aio_installed:
            return
        
        global emotes
        emotes = (yield from _get_url(self.loop, 
                                      "https://twitchemotes.com/api_cache/v2/global.json"))['emotes']
        
        if not self.client_id:
            return
        
            
        while True:
            try:
                j = yield from _get_url(self.loop, 
                                        'https://api.twitch.tv/kraken/channels/{}?client_id={}'.format(
                                            self.chan[1:], self.client_id
                                        ))
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

                j = yield from _get_url(self.loop, 
                                        'https://tmi.twitch.tv/hosts?target={}&include_logins=1'.format(j['_id']))
                self.host_count = len(j['hosts'])
                self.hosts = [x['host_login'] for x in j['hosts']]

                j = yield from _get_url(self.loop, 
                                        'https://tmi.twitch.tv/group/user/{}/chatters'.format(self.chan[1:]))
                self.viewer_count = j['chatter_count']
                self.channel_moderators = j['chatters']['moderators']
                self.viewers['viewers'] = j['chatters']['viewers']
                self.viewers['moderators'] = j['chatters']['moderators']
                self.viewers['staff'] = j['chatters']['staff']
                self.viewers['admins'] = j['chatters']['admins']
                self.viewers['global_moderators'] = j['chatters']['global_mods']

            except Exception:
                traceback.print_exc()
            yield from asyncio.sleep(60)

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
    def say(self, *args):
        """ Send messages """
        msg = " ".join(str(arg) for arg in args)

        if len(msg) > 500:
            raise Exception("The maximum amount of characters in one message is 500,"
                " you tried to send {} characters".format(len(msg)))

        while msg.startswith("."): # Use Bot.ban, Bot.timeout, etc instead
            msg = msg[1:]

        yield from self._send_privmsg(msg)


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

    @asyncio.coroutine
    def _send_privmsg(self, s):
        """ DO NOT USE THIS YOURSELF OR YOU RISK GETTING BANNED FROM TWITCH """
        s = s.replace("\n", " ")
        self.writer.write("PRIVMSG {} :{}\r\n".format(self.chan, s).encode('utf-8'))
    
    # The following are Twitch commands, such as /me, /ban and /host, so I'm not going to put docstrings on these

    # TODO Commands:
    # /cheerbadge /commercial

    
    @ratelimit_wrapper
    @asyncio.coroutine
    def ban(self, user, reason=''):
        yield from self._send_privmsg(".ban {} {}".format(user, reason))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unban(self, user):
        yield from self._send_privmsg(".unban {}".format(user))

    @ratelimit_wrapper
    @asyncio.coroutine
    def timeout(self, user, seconds=600, reason=''):
        yield from self._send_privmsg(".timeout {} {} {}".format(user, seconds, 
                                                                       reason))

    @ratelimit_wrapper
    @asyncio.coroutine
    def me(self, text):
        yield from self._send_privmsg(".me {}".format(text))

    @ratelimit_wrapper
    @asyncio.coroutine
    def whisper(self, user, msg):
        msg = str(msg)
        yield from self._send_privmsg(".w {} {}".format(user, msg))

    @ratelimit_wrapper
    @asyncio.coroutine
    def color(self, color):
        yield from self._send_privmsg(".color {}".format(color))

    @asyncio.coroutine
    def colour(self, colour):
        yield from self.color(colour)

    @ratelimit_wrapper
    @asyncio.coroutine
    def mod(self, user):
        yield from self._send_privmsg(".mod {}".format(user))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unmod(self, user):
        yield from self._send_privmsg(".unmod {}".format(user))

    @ratelimit_wrapper
    @asyncio.coroutine
    def clear(self):
        yield from self._send_privmsg(".clear")

    @ratelimit_wrapper
    @asyncio.coroutine
    def subscribers_on(self):
        yield from self._send_privmsg(".subscribers")

    @ratelimit_wrapper
    @asyncio.coroutine
    def subscribers_off(self):
        yield from self._send_privmsg(".subscribersoff")

    @ratelimit_wrapper
    @asyncio.coroutine
    def slow_on(self):
        yield from self._send_privmsg(".slow")

    @ratelimit_wrapper
    @asyncio.coroutine
    def slow_off(self):
        yield from self._send_privmsg(".slowoff")

    @ratelimit_wrapper
    @asyncio.coroutine
    def r9k_on(self):
        yield from self._send_privmsg(".r9k")

    @ratelimit_wrapper
    @asyncio.coroutine
    def r9k_off(self):
        yield from self._send_privmsg(".r9koff")

    @ratelimit_wrapper
    @asyncio.coroutine
    def emote_only_on(self):
        yield from self._send_privmsg(".emoteonly")

    @ratelimit_wrapper
    @asyncio.coroutine
    def emote_only_on(self):
        yield from self._send_privmsg(".emoteonlyoff")

    @ratelimit_wrapper
    @asyncio.coroutine
    def host(self, user):
        yield from self._send_privmsg(".host {}".format(user))

    @ratelimit_wrapper
    @asyncio.coroutine
    def unhost(self):
        yield from self._send_privmsg(".unhost")

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
    def play_ytdl(self, query, *, filename="song.flac", options={}, play=True):
        """
        Requires youtube_dl to be installed
        `pip install youtube_dl`
        """

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
        if play:
            func = functools.partial(ytdl.extract_info, query)
        else:
            func = functools.partial(ytdl.extract_info, query, download=False)
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
    """ A Bot with support for currency """
    def __init__(self, *args, points_database='points.db', currency='gold', **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_name = currency
        self.currency_database_name = points_database
        if not pathlib.Path(points_database).is_file():
            _setup_points_db(points_database)
        self.currency_database = sqlite3.connect(points_database)
        self.currency_cursor = self.currency_database.cursor()

    def check_user_currency(self, user):
        """ Check if the user is already in the database """
        return bool(list(self.currency_cursor.execute("SELECT * FROM currency WHERE username = ?", (user,))))
        
    def add_user_currency(self, user):
        self.currency_cursor.execute("INSERT INTO currency VALUES (?,0)", (user,))

    def add_currency(self, user, amount):
        balance = self.get_currency(user)
        self.currency_cursor.execute("UPDATE currency SET balance = ? WHERE username = ?", (balance+amount, user))

    def remove_currency(self, user, amount, force_remove=False):
        balance = self.get_currency(user)
        if amount > balance and not force_remove:
            raise Exception("{} owns {} {0.currency_name}, unable to remove {}."
                            "Use force_remove=True to force this action.".format(user, balance, self, amount))
        self.currency_cursor.execute("UPDATE currency SET balance = ? WHERE username = ?", (balance-amount, user))
        
    def get_currency(self, user):
        entry = list(self.currency_cursor.execute("SELECT balance FROM currency WHERE username = ?", (user,)))
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
            for group in self.viewers:
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
        return bool(list(self.time_cursor.execute("SELECT * FROM time_watched WHERE username = ?", (user,))))
        
    def add_user_time(self, user):
        self.time_cursor.execute("INSERT INTO time VALUES (?,0)", (user,))

    def add_time(self, user, amount):
        time = self.get_time(user)
        self.time_cursor.execute("UPDATE time SET time_watched = ? WHERE username = ?", (time+amount, user))

    def remove_time(self, user, amount, force_remove=False):
        time = self.get_time(user)
        if amount > time:
            amount = time
        self.time_cursor.execute("UPDATE time_watched SET time = ? WHERE username = ?", (time-amount, user))
        
    def get_time(self, user):
        entry = list(self.time_cursor.execute("SELECT time_watched FROM time WHERE username = ?", (user,)))
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
    def __init__(self, *args, ranks_database='ranks.db', points_per_minute=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.autopoints = points_per_minute
        self.ranks_database_name = ranks_database
        if not pathlib.Path(ranks_database).is_file():
            _setup_ranks_db(ranks_database)
        self.rank_database = sqlite3.connect(ranks_database)
        self.rank_cursor = self.rank_database.cursor()
        
    def check_user_rank(self, user, rank):
        """ Check if the user is already in the database """
        return bool(list(self.time_cursor.execute("SELECT * FROM user_ranks WHERE username = ? AND rank = ?", (user,rank))))
        
    def autoset_user(self, user):
            if not self.check_user_currency(user):
                self.add_user_currency(user)
            bal = self.get_currency(user)
            if not self.check_user_time(user):
                self.add_user_time(user)
            time = self.get_time(user)
            new_rank = None
            for rank in list(self.time_cursor.execute("SELECT * FROM currency_ranks ORDER BY currency")):
                cur = rank[0]
                if cur <= bal:
                    new_rank = rank[1]
            for rank in list(self.time_cursor.execute("SELECT * FROM watched_ranks ORDER BY time")):
                tim = rank[0]
                if tim <= time:
                    new_rank = rank[1]
            if new_rank:
                if not check_user_rank(user, new_rank):
                    self.rank_cursor.execute("DELETE FROM user_ranks WHERE user = ?", (user,))
                    self.rank_cursor.execute("INSERT INTO user_ranks VALUES (?,?)", (user, new_rank))


    @asyncio.coroutine
    def event_viewtime_update(self, users):
        for user in users:
            if not self.check_user_currency():
                self.add_user_currency(user)
            self.add_currency(user, self.autopoints)
        self.save_points_database()
        
    def add_rank(self, name, points=0, time_watched=0, type_rank='points'):
        if type_rank == 'points':
            self.rank_cursor.execute("INSERT INTO currency_ranks VALUES (?,?)", (points, name))
        elif type_rank == 'time_watched':
            self.rank_cursor.execute("INSERT INTO watched_ranks VALUES (?,?)", (time_watched, name))
        else:
            raise Exception("Invalid rank type! valid types: 'points', 'time_watched'.")

    def save_rank_database(self):
        self.rank_database.commit()

    def reset_rank_database(self):
        self.rank_cursor.execute("DROP TABLE currency_ranks")
        self.rank_cursor.execute("DROP TABLE watched_ranks")
        self.rank_cursor.execute("DROP TABLE user_ranks")
        _setup_ranks_db(self.ranks_database_name)

    def undo_rank_database_changes(self):
        self.rank_database.rollback()
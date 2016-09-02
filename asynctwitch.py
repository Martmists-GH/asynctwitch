import asyncio
import traceback
import sys
import os
import io
import re
import inspect
import math
import json
import configparser
import datetime
import subprocess
    
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding=sys.stdout.encoding, 
                              errors="backslashreplace", line_buffering=True)
# fix unicode characters breaking the bot on windows
    
class Message:
    """ Custom message object to combine message, author and timestamp """
    
    def __init__(self, m, a, tags):
        if tags:
            for k, v in tags.items():
                setattr(self, k, v)
        self.content = m
        self.author = a
        self.timestamp = datetime.datetime.utcnow()
    
    
    
class Command:
    """ A command class to provide methods we can use with it """
    
    def __init__(self, bot, comm, *, alias=[], desc="", 
                 admin=False, unprefixed=False, listed=True):
        
        self.bot = bot
        self.comm = comm
        self.desc = desc
        self.alias = alias
        self.admin = admin
        self.listed = listed
        self.unprefixed = unprefixed
        self.subcommands = []
        bot.commands.append(self)
    
    
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
                 prefix="!", admins=[], config=None):
        
        if config:
            self.load(config)
            
        else:
            self.prefix = prefix
            self.oauth = oauth
            self.nick = user.lower()
            self.chan = "" + channel.lower()
        
        self.loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(self.loop)
        self.host = "irc.twitch.tv"
        self.port = 6667
        
        self.admins = admins
        
        self.mod = False
        
        self.message_count = 0
        
        
        self.channel_moderators = []
    
    
    def load(self, path):
        """ Loads settings from file """
        config = configparser.ConfigParser(interpolation=None)
        config.read(path)
        self.oauth = config.get("Settings", "oauth", fallback=None)
        self.nick = config.get("Settings", "username", fallback=None)
        self.chan = "" + config.get("Settings", "channel", fallback="twitch")
        self.prefix = config.get("Settings", "prefix", fallback="!")
    
    
    def override(self, func):
        """ Allows for overriding certain functions """
        setattr(self, func.__name__, func)
    
    
    def start(self):
        """ Starts the event loop, this blocks all other code below it from executing """
        
        self.loop.run_until_complete(self._tcp_echo_client())
    
    @asyncio.coroutine
    def _pong(self, src):
        """ Tell remote we"re still alive """
        self.writer.write(bytes("PONG %s\r\n" % src, "UTF-8"))
    

    @asyncio.coroutine
    def say(self, msg):
        """ Send messages """
        if len(msg) > 500:
            raise Exception("The maximum amount of characters in one message is 1000,"
                " you tried to send {} characters".format(len(msg)))
        
        max = 100 if self.mod else 20
        
        while self.message_count == max:
            yield from asyncio.sleep(1)
        
        self.message_count += 1
        self.writer.write(bytes("PRIVMSG %s :%s\r\n" % (self.chan, str(msg)), "UTF-8"))
        yield from asyncio.sleep(30)
        self.message_count -= 1
    

    @asyncio.coroutine
    def _nick(self):
        """ Send name """
        self.writer.write(bytes("NICK %s\r\n" % self.nick, "UTF-8"))
    

    @asyncio.coroutine
    def _pass(self):
        """ Send oauth token """
        self.writer.write(bytes("PASS %s\r\n" % self.oauth, "UTF-8"))
    
    
    @asyncio.coroutine
    def _join(self):
        """ Join a channel """
        self.writer.write(bytes("JOIN %s\r\n" % self.chan, "UTF-8"))
    

    @asyncio.coroutine
    def _part(self):
        """ Leave a channel """
        self.writer.write(bytes("PART %s\r\n" % self.chan, "UTF-8"))
    

    @asyncio.coroutine
    def _special(self, mode):
        """ Allows for more events """
        self.writer.write(bytes("CAP REQ :twitch.tv/%s\r\n" % mode,"UTF-8"))
    
    
    @asyncio.coroutine
    def _tcp_echo_client(self):
        """ Receive events and trigger events """
    
        self.reader, self.writer = yield from asyncio.open_connection(self.host, self.port,
                                                                      loop=self.loop)
        
        yield from self._pass()
        yield from self._nick()
        
        modes = ["commands","tags","membership"]
        for m in modes:
            yield from self._special(m)
        
        yield from self._join()
        
        yield from self.event_ready()
        
        while True:
            rdata = (yield from self.reader.read(1024)).decode("utf-8")
            
            if not rdata:
                continue
                
            yield from self.raw_event(rdata)
                
            try:
                if rdata.startswith("@"):
                    p = re.compile("@(?P<tags>.*?) (?P<data>.*?) (?P<action>[A-Z]+?) (?P<data2>.*)")
                else:
                    p = re.compile("(?P<data>.*?) (?P<action>[A-Z]+?) (?P<data2>.*)")
                
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
                
                action = m.group("action")
                data = m.group("data")
                data2 = m.group("data2")
                
            except:
                pass
            else:
                
                try:
                    if action == "PING":
                        yield from self._pong(data)
                        
                    elif action == "PRIVMSG":
                        sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")
                            
                        message = re.match("[a-zA-Z0-9_]+ "
                            ":(?P<content>.+)", data2).group("content")
                        
                        messageobj = Message(message, sender, tags)
                        
                        yield from self.event_message(messageobj)
                    
                    elif action == "JOIN":
                        sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")
                            
                        yield from self.event_user_join(sender)
                        
                    elif action == "PART":
                        sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)"
                            "@(?P=author).tmi.twitch.tv", data).group("author")
                            
                        yield from self.event_user_leave(sender)
                    
                    elif action == "MODE":
                        
                        m = re.match("[a-zA-Z0-9]+ (?P<mode>[+-])o (?P<user>.+?)", 
                                     data2)
                        mode = m.group("mode")
                        user = m.group("user")
                        
                        if mode == "+":
                            self.channel_moderators.append(user)
                            yield from self.event_user_op(user)
                        else:
                            [
                                self.channel_moderators.pop(x) for x, u in 
                                enumerate(self.channel_moderators) if u == user
                            ]
                             
                            yield from self.event_user_deop(user)
                    
                    elif action == "USERSTATE":
                        if not tags: 
                            continue
                            
                        if tags["mod"] == 1:
                            self.mod = True
                        else:
                            self.mod = False
                            
                        yield from self.event_userstate(tags)
                    
                    elif action == "ROOMSTATE":
                        yield from self.event_roomstate(tags)
                        
                    elif action == "NOTICE":
                        yield from self.event_notice(tags)
                    
                    elif action == "CLEARCHAT":
                        user = re.match("[a-zA-Z0-9_]+ :(?P<user>.+)", data2).group("user")
                        
                        if "ban-duration" in tags.keys():
                            yield from self.event_timeout(user, tags)
                        else:
                            yield from self.event_ban(user, tags)
                            
                    elif action == "HOSTTARGET":
                        m = re.match("[a-zA-Z0-9_]+ :(?P<channel>.+?) (?P<count>[0-9]+)", 
                                      data2)
                        channel = m.group("channel")
                        viewcount = m.group("count")
                        
                        if channel == "-":
                            yield from self.event_host_stop(viewers)
                        else:
                            yield from self.event_host_start(channel, viewers)
                        
                    elif action == "USERNOTICE":
                        if re.search(":", data2):
                            message = re.match("[a-zA-Z0-9_]+ :(?P<message>.+?)", 
                                                data2).group("message")
                        else:
                            message = ""
                            
                        user = tags["login"]
                        
                        yield from self.event_subscribe(user, message, tags)
                        
                    elif action == "CAP": 
                        # We don"t need this for anything, so just ignore it
                        continue 
                    
                    else:
                        print("Unknown event:", action) 
                        print(rdata)
                        
                except Exception as e:
                    yield from self.parse_error(e)
    
    
    @asyncio.coroutine
    def event_subscribe(self, user, message, tags):
        """ Called when someone (re-)subscribes. """
    
    @asyncio.coroutine
    def event_host_start(self, viewercount):
        """ Called when the streamer starts hosting. """
        pass
    
    
    @asyncio.coroutine
    def event_host_stop(self, channel, viewercount):
        """ Called when the streamer stops hosting. """
        pass
    
    
    @asyncio.coroutine
    def event_ban(self, user, tags):
        """
        Called when a user is banned.
        
        Example of what `tags` returns:
        
        {
            "ban-reason": "I dont like you"
        }
        """
        pass
    
    
    @asyncio.coroutine
    def event_timeout(self, user, tags):
        """
        Called when a user is timed out.
        
        Example of what `tags` returns:
        
        {
            "ban-reason": "take 10 seconds to think about what you just said",
            "ban-duration": 10
        }
        """
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
    def event_userstate(self, tags):
        """
        Triggered when the bot sends a message.
        
        Example for what `tags` can return:
        
        {
            "badges": "moderator/1",
            "color": "00FF7F",
            "display-name": "martmistsbot",
            "emote-sets": 0,
            "mod": 1,
            "subscriber": 0,
            "turbo": 0,
            "user-type": "mod"
        }
        """
        pass
       
    
    @asyncio.coroutine
    def event_ready(self):
        """ Called when the bot is ready for use """
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
    def event_message(self, rm):
        """ Called when a message is sent """
        pass
    
    
    @asyncio.coroutine
    def stop(self, exit=False):
        """
        Stops the bot and disables using it again.
        Useful for a restart command I guess
        """
        if hasattr(self, "player"):
            self.player.terminate()
        self.loop.stop()
        while self.loop.is_running():
            pass
        self.loop.close()
        if exit:
            os._exit(0)
    
    
    @asyncio.coroutine
    def play_file(self, file):
        """
        Plays audio.
        For this to work, ffplay, ffmpeg and ffprobe, downloadable from the ffmpeg website,
        have to be in the same folder as the bot OR added to path.
        """
        
        j = yield from self.loop.run_in_executor(None, subprocess.check_output, 
                                                 [
                                                     "ffprobe", "-v", "-8", "-print_format", 
                                                     "json", "-show_format", file
                                                 ])
        
        j = json.loads(j.decode().strip())
        
        self.player = yield from asyncio.create_subprocess_exec("ffplay", "-nodisp", "-autoexit", 
                                                                "-v", "-8", file, 
                                                                stdout=asyncio.subprocess.DEVNULL, 
                                                                stderr=asyncio.subprocess.DEVNULL)
                                                                
        yield from asyncio.sleep( math.ceil( float( j["format"]["duration"] )) + 2)
        return True
    
    
    @asyncio.coroutine
    def play_ytdl(self, query, *, filename="song.mp3", cleanup=True, options={}):
        """
        Requires youtube_dl to be installed
        `pip install youtube_dl`
        """
        import youtube_dl
        
        args = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "audioformat": "mp3",
            "default_search": "auto",
            "loglevel":"quiet",
            "outtmpl": filename
        }
        args.update(options)
        ytdl = youtube_dl.YoutubeDL(args)
        yield from self.loop.run_in_executor(None, ytdl.download, ([query]))
        yield from self.play_file(filename)
        if cleanup:
            os.remove(filename)
    
    
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
        self.commands = []
        self.playlist = []
        self.playing = None
    
    
    @asyncio.coroutine
    def event_message(self, rm):
        """ Shitty command parser I made """
        
        if rm.content.startswith(self.prefix):
    
            m = rm.content[len(self.prefix):]
            cl = m.split(" ")
            w = cl.pop(0).lower().replace("\r","")
            m = " ".join(cl)
            
            for c in self.commands:
                if (w == c.comm or w in c.alias) and not c.unprefixed:

                    if c.admin and not rm.author in self.admins:
                        yield from bot.say("You are not allowed to use this command")
                        return
                    yield from c.run(rm)

        else:
            cl = rm.content.split(" ")
            w = cl.pop(0).lower()
            
            for c in self.commands:
                if (w == c.comm or w in c.alias) and c.unprefixed:
                    yield from c.run(rm)
                    break
    
    
    def command(self, *args, **kwargs):
        """ Add a command """
        
        return Command(self, *args, **kwargs)
    
    
    @asyncio.coroutine
    def play_list(self, l):
        """ play songs from a list using play_ytdl """
        
        self.playlist = l
        while self.playlist:
            song = self.playlist.pop(0)
            self.playing = song
            yield from self.play_ytdl(song)
    
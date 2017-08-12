import asyncio
import uuid
import datetime
import inspect
import os

try:
    import isodate
    iso_installed = True
except ImportError:
    print("To use music, please install isodate. (pip install isodate)")
    iso_installed = False

try:
    import aiohttp
    aio_installed = True
except ImportError:
    print("To use stats from the API, make sure to install aiohttp. "
          "(pip install aiohttp)")
    aio_installed = False


def _parse_badges(s):
    if not s:
        return []
    if "," in s:
        # multiple badges
        badges = s.split(",")
        return [Badge(*badge.split("/")) for badge in badges]
    else:
        return [Badge(*s.split("/"))]


def _parse_emotes(s):
    emotelist = []  # 25:8-12 354:14-18
    if not s:
        return []
    if "/" in s:
        # multiple emotes
        emotes = s.split("/")
        for emote in emotes:
            res = emote.split(":")
            emote_id = res[0]
            locations = res[1]
            if "," in locations:
                for loc in locations.split(","):
                    emotelist.append(Emote(emote_id, loc))
            else:
                emotelist.append(Emote(emote_id, locations))
    else:
        res = s.split(":")
        emote_id = res[0]
        locations = res[1]
        if "," in locations:
            for loc in locations.split(","):
                emotelist.append(Emote(emote_id, loc))
        else:
            emotelist.append(Emote(emote_id, locations))
    return emotelist

class Object:
    """
    An object that may be created as substitute for functions.
    """
    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

class Emote:
    """
    A class to hold emote data

    Attributes
    ----------
    id : int
        The ID of the emote.
    location : str
        The location of the emote in the message.
    url : str
        The url of the emote.
    """
    def __init__(self, id, loc):
        self.id = int(id)
        self.location = loc
        self.url = "https://static-cdn.jtvnw.net/emoticons/v1/{}/3.0".format(
            id)

    def __str__(self):
        global emotes
        if not aio_installed:
            raise Exception("Please install aiohttp to use this feature")
        else:
            for k, v in emotes.items():
                if v['image_id'] == self.id:
                    return k
            return ""


class Badge:
    """
    A class to hold badge data.

    Attributes
    ----------
    name : str
        Name of the badge.
    value : str
        Variant of the badge.
    """
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return "{0.name}/{0.value}".format(self)

    @classmethod
    def from_str(cls, s):
        """ e.g. Moderator/1 """
        n, v = s.split("/")
        return cls(n, v)


class Color:
    """
    Available colors for non-turbo users when using Bot.color

    Conversions are not working perfectly:

    .. code-block:: python

        >>> str( Color.blue() ) #0000FF
        '#0000ff'

        #0000FF to and from yiq
        >>> str( Color.from_yiq( *Color.blue().to_yiq() ) )
        '#0000fe'

        #0000FF to and from hsv
        >>> str( Color.from_hsv( *Color.blue().to_hsv() ) )
        '#00ffff'
        """

    def __init__(self, value):
        if not value:
            value = 0
        elif isinstance(value, str):
            value = int(value.strip("#"), 16)
        self.value = value

    def _get_rgb(self, byte):
        return (self.value >> (8 * byte)) & 0xff

    def _get_yiq(self, rm, gm, bm, mode):
        if mode == "y":
            v1 = v2 = 1
        elif mode == "i":
            v1 = v2 = -1
        elif mode == "q":
            v1 = -1
            v2 = 1
        return round((rm * (self.r / 255)) + v1 *
                     (gm * (self.g / 255)) + v2 * (bm * (self.b / 255)), 3)

    def __eq__(self, clr):
        return isinstance(clr, Color) and self.value == clr.value

    def __ne__(self, clr):
        return not self.__eq__(clr)

    def __str__(self):
        return '#{:0>6x}'.format(self.value)

    def __add__(self, clr):
        return Color.from_rgb(
            min(self.r + clr.r, 255),
            min(self.g + clr.g, 255),
            min(self.b + clr.b, 255)
        )

    def __sub__(self, clr):
        return Color.from_rgb(
            max(self.r - clr.r, 0),
            max(self.g - clr.g, 0),
            max(self.b - clr.b, 0)
        )

    def blend(self, clr):
        return Color.from_rgb(
            (self.r + clr.r) / 2,
            (self.g + clr.g) / 2,
            (self.b + clr.b) / 2)

    @property
    def r(self):
        return self._get_rgb(2)

    @property
    def g(self):
        return self._get_rgb(1)

    @property
    def b(self):
        return self._get_rgb(0)

    @r.setter
    def r(self, value):
        self = Color.from_rgb(value, self.g, self.b)

    @g.setter
    def g(self, value):
        self = Color.from_rgb(self.r, value, self.b)

    @b.setter
    def b(self, value):
        self = Color.from_rgb(self.r, self.g, value)

    @property
    def y(self):
        return self._get_yiq(0.299, 0.587, 0.114, "y")

    @property
    def i(self):
        return self._get_yiq(0.596, 0.275, 0.321, "i")

    @property
    def q(self):
        return self._get_yiq(0.212, 0.528, 0.311, "q")

    @y.setter
    def y(self, value):
        self = Color.from_yiq(value, self.i, self.q)

    @i.setter
    def i(self, value):
        self = Color.from_yiq(self.y, value, self.q)

    @q.setter
    def q(self, value):
        self = Color.from_yiq(self.y, self.i, value)

    def to_rgb(self):
        """ Returns an (r, g, b) tuple of the color """
        return (self.r, self.g, self.b)

    def to_yiq(self):
        """ Returns a (y, i, q) tuple of the color """
        return (self.y, self.i, self.q)

    def to_hsv(self):
        """ Returns a (h, s, v) tuple of the color """
        r = self.r / 255
        g = self.b / 255
        b = self.b / 255
        _min = min(r, g, b)
        _max = max(r, g, b)
        v = _max
        delta = _max - _min
        if _max == 0:
            return 0, 0, v
        s = delta / _max
        if delta == 0:
            delta = 1
        if r == _max:
            h = 60 * (((g - b) / delta) % 6)
        elif g == _max:
            h = 60 * (((b - r) / delta) + 2)
        else:
            h = 60 * (((r - g) / delta) + 4)
        return (round(h, 3), round(s, 3), round(v, 3))

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
        """ (0,0,0) to (255,255,255) """
        value = ((int(r) << 16) + (int(g) << 8) + int(b))
        return cls(value)

    @classmethod
    def from_yiq(cls, y, i, q):
        r = y + (0.956 * i) + (0.621 * q)
        g = y - (0.272 * i) - (0.647 * q)
        b = y - (1.108 * i) + (1.705 * q)
        r = 1 if r > 1 else max(0, r)
        g = 1 if g > 1 else max(0, g)
        b = 1 if b > 1 else max(0, b)
        return cls.from_rgb(
            round(
                r * 255,
                3),
            round(
                g * 255,
                3),
            round(
                b * 255,
                3))

    @classmethod
    def from_hsv(cls, h, s, v):
        c = v * s
        h /= 60
        x = c * (1 - abs((h % 2) - 1))
        m = v - c
        if h < 1:
            res = (c, x, 0)
        elif h < 2:
            res = (x, c, 0)
        elif h < 3:
            res = (0, c, x)
        elif h < 4:
            res = (0, x, c)
        elif h < 5:
            res = (x, 0, c)
        elif h < 6:
            res = (c, 0, x)
        else:
            raise Exception("Unable to convert from HSV to RGB")
        r, g, b = res
        return cls.from_rgb(
            round(
                (r + m) * 255,
                3),
            round(
                (g + m) * 255,
                3),
            round(
                (b + m) * 255,
                3))


class Song:
    """
    Contains information about a song

    Attributes
    ----------
    title : str
        The title of the song
    """

    def __init__(self):
        self.title = ""  # In case setattrs() isn't called
        self.is_playing = False

    def setattrs(self, obj):
        self.title = obj['title']
        try:  # not available with play_file
            if isinstance(obj['duration'], str):
                self.duration = isodate.parse_duration(
                    obj['duration']).total_seconds()
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
        yield from asyncio.create_subprocess_exec(
            "ffplay", "-nodisp", "-autoexit", "-v", "-8", file,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        # add 2 to make sure it's not in use by ffplay anymore
        yield from asyncio.sleep(self.duration + 2)
        self.is_playing = False
        if cleanup:
            os.remove(file)


class User:
    """ Custom user class """

    def __init__(self, a, channel, tags=None):
        self.name = a
        self.channel = channel
        if tags:
            self.badges = _parse_badges(tags['badges'])
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

    def __init__(self, m, a, channel, tags):
        if tags:
            self.raw_timestamp = tags['tmi-sent-ts']
            self.timestamp = datetime.datetime.fromtimestamp(
                int(tags['tmi-sent-ts']) / 1000)
            self.emotes = _parse_emotes(tags['emotes'])
            self.id = uuid.UUID(tags['id'])
            self.room_id = tags['room-id']
        self.content = m
        self.author = User(a, channel, tags)
        self.channel = channel

    def __str__(self):
        return self.content


class Command:
    """ A command class to provide methods we can use with it """

    def __init__(self, bot, comm, desc='', alias=[], admin=False, unprefixed=False, listed=True):
        self.comm = comm
        self.desc = desc
        self.alias = alias
        self.admin = admin
        self.listed = listed
        self.unprefixed = unprefixed
        self.subcommands = {}
        self.bot = bot
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
        args = message.content[len(self.bot.prefix):].split(" ")[1:]

        args_name = inspect.getfullargspec(self.func)[0][1:]

        if len(args) > len(args_name):
            args[len(args_name)-1] = " ".join(args[len(args_name)-1:])

            args = args[:len(args_name)]

        ann = self.func.__annotations__

        for x in range(0, len(args_name)):
            try:
                v = args[x]
                k = args_name[x]

                if not type(v) == ann[k]:
                    try:
                        v = ann[k](v)

                    except Exception:
                        raise TypeError("Invalid type: got {}, {} expected"
                            .format(ann[k].__name__, v.__name__))

                args[x] = v
            except IndexError:
                break

        if len(list(self.subcommands.keys())) > 0:
            try:
                subcomm = args.pop(0).split(" ")[0]
            except Exception:
                yield from self.func(message, *args)
                return
            if subcomm in self.subcommands.keys():
                c = message.content.split(" ")
                c.pop(1)
                message.content = " ".join(c)
                yield from self.subcommands[subcomm].run(message)

            else:
                yield from self.func(message, *args)

        else:
            try:
                yield from self.func(message, *args)
            except TypeError as e:
                if len(args) < len(args_name):
                    raise Exception("Not enough arguments for {}, required arguments: {}"
                        .format(self.comm, ", ".join(args_name)))
                else:
                    raise e


class SubCommand(Command):
    """ Subcommand class """

    def __init__(self, parent, comm, desc, *alias):
        self.comm = comm
        self.parent = parent
        self.subcommands = {}
        parent.subcommands[comm] = self
        for a in alias:
            parent.subcommands[a] = self

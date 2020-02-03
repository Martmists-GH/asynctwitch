from __future__ import annotations

import re
import traceback
from typing import TYPE_CHECKING

from anyio import run, connect_tcp, run_async_from_thread, create_task_group

from asynctwitch.entities.channel_status import ChannelStatus
from asynctwitch.entities.message import Message
from asynctwitch.entities.user import User
from asynctwitch.utils import ratelimit_wrapper

if TYPE_CHECKING:
    from typing import List
    from anyio import SocketStream, TaskGroup


class BotBase:
    regex = {
        "data": re.compile(
            r"^(?:@(?P<tags>\S+)\s)?:(?P<data>\S+)\s(?P<action>[A-Z]+)"
            r"(?:\s#)(?P<channel>\S+)(?:\s(?::)?(?P<content>.+))?"
        ),
        "ping": re.compile("PING (?P<content>.+)"),
        "author": re.compile(r"(?P<author>[^!]+)!(?P=author)@(?P=author).tmi.twitch.tv"),
        "mode": re.compile(r"(?P<mode>[+\-])o (?P<user>.+)"),
        "host": re.compile(r"(?P<channel>[\S_]+) (?P<count>[\d\-]+)")
    }

    def __init__(self, *, username: str = "justinfan100", oauth: str = "",
                 backend: str = "asyncio", channels: List[str] = None):
        self._sock: SocketStream = None
        self._task_group: TaskGroup = None
        self._backend = backend
        self.username = username
        self.oauth_token = oauth
        self.channels = [channel
                         if channel.startswith("#")
                         else "#" + channel
                         for channel in channels]
        self.channel_status = {}
        self._count = 1  # Used for ratelimits
        self.do_loop = True

    def start(self):
        """ Start the bot """
        run(self.run, backend=self._backend)

    async def run(self):
        async with create_task_group() as self._task_group:
            await self._task_group.spawn(self._tcp_echo_client)

    def _send_all(self, data: str):
        """ shorthand for sending data """
        raw = (data + "\r\n").encode('utf-8')
        return self._sock.send_all(raw)

    async def _pong(self, src: str):
        """ Tell remote we're still alive """
        await self._send_all(f"PONG {src}")

    @ratelimit_wrapper
    async def say(self, channel: str, message: str):
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

        await self._send_privmsg(channel, message)

    async def _nick(self):
        """ Send name """
        await self._send_all(f"NICK {self.username}")

    async def _pass(self):
        """ Send oauth token """
        await self._send_all(f"PASS {self.oauth_token}")

    async def _join(self, channel):
        """ Join a channel """
        self.channel_status[channel] = ChannelStatus()
        await self._send_all(f"JOIN {channel}")

    async def _part(self, channel):
        """ Leave a channel """
        del self.channel_status[channel]
        await self._send_all(f"PART {channel}")

    async def _special(self, mode: str):
        """ Allows for more events """
        await self._send_all(f"CAP REQ :twitch.tv/{mode}")

    @ratelimit_wrapper
    async def _send_privmsg(self, channel: str, content: str):
        filtered = content.replace('\n', ' ')
        await self._send_all(f"PRIVMSG #{channel} :{filtered}")

    # The following are Twitch commands, such as /me, /ban and /host, so I'm
    # not going to put docstrings on these
    # TODO Commands:
    # - /cheerbadge
    # - /commercial
    # - Stuff that was added ages ago

    async def ban(self, user: User, reason: str = ''):
        """
        Ban a user.

        Parameters
        ----------
        user : :class:`User`
            The user to ban.
        reason : Optional[str]
            The reason a user was banned.
        """
        await self._send_privmsg(user.channel, f".ban {user.name} {reason}")

    async def unban(self, user: User):
        """
        Unban a banned user

        Parameters
        ----------
        user : :class:`User`
            The user to unban.
        """
        await self._send_privmsg(user.channel, f".unban {user.name}")

    async def timeout(self, user: User, seconds: int = 600, reason: str = ''):
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
        await self._send_privmsg(user.channel, f".timeout {user.name} {seconds} {reason}")

    async def me(self, channel: str, text: str):
        """
        The /me command.

        Parameters
        ----------
        channel : str
            The channel to use /me in.
        text : str
            The text to use in /me.
        """
        await self._send_privmsg(channel, f".me {text}")

    async def whisper(self, user: User, message: str):
        """
        Send a private message to a user

        Parameters
        ----------
        user : :class:`User`
            The user to send a message to.
        message : str
            The message to send.
        """
        await self._send_privmsg(user.channel, f".w {user.name} {message}")

    async def color(self, color: str):
        """
        Change the bot's color

        Parameters
        ----------
        color : str
            The color to use.
        """
        await self._send_privmsg(self.channels[0], f".color {color}")

    async def mod(self, user: User):
        """
        Give moderator status to a user.

        Parameters
        ----------
        user : :class:`User`
            The user to give moderator.
        """
        await self._send_privmsg(user.channel, f".mod {user.name}")

    async def unmod(self, user: User):
        """
        Remove moderator status from a user.

        Parameters
        ----------
        user : :class:`User`
            The user to remove moderator from.
        """
        await self._send_privmsg(user.channel, f".unmod {user.name}")

    async def clear(self, channel: str):
        """
        Clear a channel.

        Parameters
        ----------
        channel : str
            The channel to clear.
        """
        await self._send_privmsg(channel, ".clear")

    async def subscribers_on(self, channel: str):
        """
        Set channel mode to subscribers only.

        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        await self._send_privmsg(channel, ".subscribers")

    async def subscribers_off(self, channel: str):
        """
        Unset channel mode to subscribers only.

        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        await self._send_privmsg(channel, ".subscribersoff")

    async def slow_on(self, channel: str):
        """
        Set channel mode to slowmode.

        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        await self._send_privmsg(channel, ".slow")

    async def slow_off(self, channel: str):
        """
        Unset channel mode to slowmode.

        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        await self._send_privmsg(channel, ".slowoff")

    async def r9k_on(self, channel: str):
        """
        Set channel mode to r9k.

        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        await self._send_privmsg(channel, ".r9k")

    async def r9k_off(self, channel: str):
        """
        Unset channel mode to r9k.

        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        await self._send_privmsg(channel, ".r9koff")

    async def emote_only_on(self, channel: str):
        """
        Set channel mode to emote-only.

        Parameters
        ----------
        channel : str
            The channel to enable this on.
        """
        await self._send_privmsg(channel, ".emoteonly")

    async def emote_only_off(self, channel: str):
        """
        Unset channel mode to emote-only.

        Parameters
        ----------
        channel : str
            The channel to disable this on.
        """
        await self._send_privmsg(channel, ".emoteonlyoff")

    async def host(self, channel: str, user: str):
        """
        Start hosting a channel.

        Parameters
        ----------
        channel : str
            The channel that will be hosting.
        user : str
            The channel to host.
        """
        await self._send_privmsg(channel, f".host {user}")

    async def unhost(self, channel: str):
        """
        Stop hosting a channel.

        Parameters
        ----------
        channel : str
            The channel that was hosting.
        """
        await self._send_privmsg(channel, ".unhost")

    # End of Twitch commands

    async def _tcp_echo_client(self):
        async with await connect_tcp("irc.chat.twitch.tv", 6667) as self._sock:
            if not self.username.startswith('justinfan'):
                print("[AsyncTwitch] WARNING: User is a justinfan client, and will be unable to send messages!")
                await self._pass()
            await self._nick()
            for m in ("commands", "tags", "membership"):
                await self._special(m)
            await self._join("#"+self.username)
            for c in self.channels:
                await self._join(c)

            await self.event_ready()

            MAX_SIZE = 2 ** 16

            while self.do_loop:
                raw_data = await self._sock.receive_until(b"\r\n", MAX_SIZE)

                if not raw_data:
                    continue

                decoded_data = raw_data.decode('utf-8').strip()

                await self.raw_event(decoded_data)

                if decoded_data.startswith("PING"):
                    p = self.regex["ping"]
                else:
                    p = self.regex["data"]
                m = p.match(decoded_data)

                if m is None:
                    all_groups = []
                else:
                    all_groups = [key
                                  for key, value in m.groupdict().items()
                                  if value is not None]

                if "tags" in all_groups:
                    _tags = m.group("tags")

                    tag_dict = {}
                    for tag in _tags.split(";"):
                        t = tag.split("=")
                        if t[1].isnumeric():
                            t[1] = int(t[1])
                        tag_dict[t[0]] = t[1]
                    tags = tag_dict
                else:
                    tags = None

                if "action" in all_groups:
                    action = m.group("action")
                else:
                    action = "PING"

                if "data" in all_groups:
                    data = m.group("data")
                else:
                    data = None

                if "content" in all_groups:
                    content = m.group('content')
                else:
                    content = None

                if "channel" in all_groups:
                    channel = m.group('channel')
                else:
                    channel = None

                try:
                    if not action:
                        continue

                    if action == "PING":
                        await self._pong(content)

                    elif action == "PRIVMSG":
                        sender = self.regex["author"].match(data).group("author")

                        message_obj = Message(content, sender, channel, tags)

                        await self.event_message(message_obj)

                    elif action == "WHISPER":
                        sender = self.regex["author"].match(data).group("author")

                        message_obj = Message(content, sender, channel, tags)

                        await self.event_private_message(message_obj)

                    elif action == "JOIN":
                        sender = self.regex["author"].match(data).group("author")

                        await self.event_user_join(User(sender, channel))

                    elif action == "PART":
                        sender = self.regex["author"].match(data).group("author")

                        await self.event_user_leave(User(sender, channel))

                    elif action == "MODE":

                        m = self.regex["mode"].match(content)
                        mode = m.group("mode")
                        user = m.group("user")

                        if mode == "+":
                            await self.event_user_op(User(user, channel))
                        else:
                            await self.event_user_deop(User(user, channel))

                    elif action == "USERSTATE":

                        if tags["mod"] == 1:
                            self.channel_status[channel].is_mod = True
                        else:
                            self.channel_status[channel].is_mod = False

                        await self.event_userstate(User(self.username, channel, tags))

                    elif action == "ROOMSTATE":
                        await self.event_roomstate(channel, tags)

                    elif action == "NOTICE":
                        await self.event_notice(channel, tags)

                    elif action == "CLEARCHAT":
                        if not content:
                            await self.event_clear(channel)
                        else:
                            if "ban-duration" in tags.keys():
                                await self.event_timeout(User(content, channel), tags)
                            else:
                                await self.event_ban(User(content, channel), tags)

                    elif action == "CLEARMSG":
                        sender = tags.pop("login")
                        await self.event_delete_message(Message(content, sender, channel, {}))

                    elif action == "HOSTTARGET":
                        m = self.regex["host"].match(content)
                        hchannel = m.group("channel")
                        viewers = int(m.group("count"))

                        if channel == "-":
                            await self.event_host_stop(channel, viewers)
                        else:
                            await self.event_host_start(channel, hchannel, viewers)

                    elif action == "USERNOTICE":
                        message = content or ""
                        user = tags["login"]

                        await self.event_subscribe(Message(message, user, channel, tags), tags)

                    elif action == "CAP":
                        # We don"t need this for anything, so just ignore it
                        continue

                    else:
                        print("Unknown event:", action)
                        print(decoded_data)

                except Exception as e:  # pylint: disable=broad-except flake8: noqa
                    await self.on_error(e)

    async def event_ready(self):
        """
        Called when ready to start reading data
        """
        await self._send_privmsg(self.username, "fetching client ID")

    async def event_notice(self, channel: str, tags: dict):
        """
        Called on NOTICE events (when commands are called).
        """
        pass

    async def event_clear(self, channel: str):
        """
        Called when chat is cleared by someone else.
        """
        pass

    async def event_delete_message(self, message: Message):
        """
        Called when a single message is deleted
        """
        pass

    async def event_subscribe(self, message: Message, tags: dict):
        """
        Called when someone (re-)subscribes.
        """
        pass

    async def event_host_start(self, channel: str, hosted_channel: str, viewer_count: int):
        """
        Called when the streamer starts hosting.
        """
        pass

    async def event_host_stop(self, channel: str, viewercount: int):
        """
        Called when the streamer stops hosting.
        """
        pass

    async def event_ban(self, user: User, tags: dict):
        """
        Called when a user is banned.
        """
        pass

    async def event_timeout(self, user: User, tags: dict):
        """
        Called when a user is timed out.
        """
        pass

    async def event_roomstate(self, channel: str, tags: dict):
        """
        Triggered when a channel's chat settings change.
        """
        pass

    async def event_userstate(self, user: User):
        """
        Triggered when the bot sends a message.
        """
        pass

    async def raw_event(self, data: str):
        """
        Called on all events after event_ready.
        """
        pass

    async def event_user_join(self, user: User):
        """
        Called when a user joins a channel.
        """
        pass

    async def event_user_leave(self, user: User):
        """
        Called when a user leaves a channel.
        """
        pass

    async def event_user_deop(self, user: User):
        """
        Called when a user is de-opped.
        """
        pass

    async def event_user_op(self, user: User):
        """
        Called when a user is opped.
        """
        pass

    async def event_private_message(self, message: Message):
        """
        Called when the bot receives a private message.
        """
        pass

    async def event_message(self, message: Message):
        """
        Called when a message is sent by someone in chat.
        """
        pass

    async def on_error(self, error: Exception):
        print("An error occured!")
        traceback.print_exc()

    # End of events

    async def stop(self):
        """
        Stops the bot and disables using it again.

        Parameters
        ----------
        do_exit : Optional[bool]
            If True, this will close the event loop and raise SystemExit. (default: False)
        """

        self.do_loop = False
        await self._task_group.cancel_scope.cancel()

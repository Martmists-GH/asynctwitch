import asyncio
import traceback
import sys
import io
import re
import inspect


class CommandError(Exception):
	pass
	
	
class Message:
	def __init__(self, m, a, bot):
		self.content = m
		self.author = a
		self.bot = bot
	#
	
	async def reply(self, m):
		await self.bot.say("@{}, {}".format(self.author, m))
	#
	
class Command:
	def __init__(self, bot, comm, *, alias=[], desc='', admin=False, unprefixed=False, listed=True):
		self.comm = comm
		self.desc = desc
		self.alias = alias
		self.admin = admin
		self.listed = listed
		self.unprefixed = unprefixed
		self.isParent = isParent
		if self.isParent:
			self.subcomms = []
		bot.commands.append(self)
	#
	
	def subcommand(self, *args, **kwargs)
		return SubCommand(self, *args, **kwargs)
	
	def __call__(self, func):
		self.func = func
		print("Added command: " + self.comm)
		return func
	#
	
	async def run(self, message):
		args = message.content.split(" ")
		del args[0]
		
		args_name = inspect.getfullargspec(self.func)[0]
		del args_name[0]
		
		if len(args) > len(args_name):
			args[len(args_name)-1] = " ".join(args[len(args_name)-1:])
			
			for i in range(len(args_name),len(args)):
				del args[len(args_name)]
				
		elif len(args) < len(args_name):
			raise CommandError('Not enough arguments for {}, required arguments: {}'.format(self.comm, ', '.join(args_name)))
			
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
					raise CommandError("Invalid type: got {}, {} expected".format(ann[k].__name__, v.__name__))
					
			args[x] = v
			
		await self.func(message, *args)
	#

	
class SubCommand:
	def __init__(self, bot, parent, comm, *, desc=''):
		self.comm = comm
		self.parent = [c for c in bot.commands if c.comm==parent][0]
		self.parent.subcomms.append(self)
	#
	
	def __call__(self, func):
		self.func = func
		print("Added subcommand: " + self.comm)
		return func
	#
	
	async def run(self, message):
		args = message.content.split(" ")
		del args[0]
		del args[1]
		
		args_name = inspect.getfullargspec(self.func)[0]
		del args_name[0]
		
		if len(args) > len(args_name):
			args[len(args_name)-1] = " ".join(args[len(args_name)-1:])
			
			for i in range(len(args_name),len(args)):
				del args[len(args_name)]
				
		elif len(args) < len(args_name):
			raise CommandError('Not enough arguments for {}, required arguments: {}'.format(self.comm, ', '.join(args_name)))
			
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
					raise CommandError("Invalid type: got {}, {} expected".format(ann[k].__name__, v.__name__))
					
			args[x] = v
			
		await self.func(message, *args)
	#
	
	
class Bot:
	def __init__(self, *, oauth=None, user=None, channel='#twitch', prefix='!', admins=[]):
		sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding=sys.stdout.encoding, errors="backslashreplace", line_buffering=True)
		self.prefix = prefix
		self.loop = asyncio.get_event_loop()
		self.host = 'irc.twitch.tv'
		self.port = 6667
		self.commands = []
		self.oauth = oauth
		self.nick = user
		self.chan = "#" + channel
		self.admins = admins
	#
	
	def override(self, func):
		setattr(self, func.__name__, func)
	
	def start(self):
		self.loop.run_until_complete(self._tcp_echo_client())
	#
	
	async def _sender(self, msg):
		result = ''
		for char in msg:
			if char == '!':
				break
			if char != ':':
				result += char
		return result
	#

	async def _message(self, msg):
		result = ''
		i = 3
		length = len(msg)
		while i < length:
			result += msg[i] + ' '
			i += 1
		result = result.lstrip(':')
		return result
	#
	
	async def _pong(self, msg):
		self.writer.write(bytes('PONG %s\r\n' % msg, 'UTF-8'))
	#

	async def say(self, msg):
		self.writer.write(bytes('PRIVMSG %s :%s\r\n' % (self.chan, msg), 'UTF-8'))
	#

	async def _nick(self):
		self.writer.write(bytes('NICK %s\r\n' % self.nick, 'UTF-8'))
	#

	async def _pass(self):
		self.writer.write(bytes('PASS %s\r\n' % self.oauth, 'UTF-8'))
	#
	
	async def _join(self):
		self.writer.write(bytes('JOIN %s\r\n' % self.chan, 'UTF-8'))
	#

	async def _part(self):
		self.writer.write(bytes('PART %s\r\n' % self.chan, 'UTF-8'))
	#
		
	async def _tcp_echo_client(self):
		self.reader, self.writer = await asyncio.open_connection(self.host, self.port, loop=self.loop)
		await self._pass()
		await self._nick()
		await self._join()
		
		while True: 
			data = (await self.reader.read(1024)).decode('utf-8')
			data_split = re.split(r'[~\r\n]+', data)
			data = data_split.pop()
			
			for line in data_split:
				line = str.rstrip(line)
				line = str.split(line)
				
				if len(line) >= 1:
					if line[0] == 'PING':
						await self._pong(line[1])
						
					if line[1] == 'PRIVMSG':
						sender = await self._sender(line[0])
						message = await self._message(line)
						messageobj = Message(message, sender, self)
						try:
							await self.parse_message(messageobj)
						except:
							print('Ignoring error in parse_message:')
							traceback.print_exc()
	#
	
	async def parse_message(self, rm):
		pass
	#
	
	
class CommandBot(Bot):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
	#
	
	async def parse_message(self, rm):
		if rm.content.startswith(self.prefix):
			m = rm.content[len(self.prefix):]
			l = m.split(" ")
			w = l.pop(0).lower()
			m = " ".join(l)
			
			
			for c in self.commands:
				if (w == c.comm or w in c.alias) and not c.unprefixed:
					if c.admin and not rm.author in self.admins:
						await self.say("You are not allowed to use this command")
						return
						
					try:
						await c.run(rm)
						
					except:
						traceback.print_exc()
						break
						
		else:
			l = rm.content.split(" ")
			w = l.pop(0).lower()
			
			for c in self.commands:
				if (w == c.comm or w in c.alias) and c.unprefixed:
					await c.run(rm)
	#
	
	def command(self, *args, **kwargs):
		return Command(self, *args, **kwargs)
	#
	
	def subcommand(self, *args, **kwargs):
		return SubCommand(self, *args, **kwargs)
	#
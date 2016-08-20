import asyncio
import traceback
import sys
import io
import re
import inspect

class CommandError(Exception):
	"""\
	Custom exception
	"""
	pass
	
	
class Message:
	"""\
	Custom message object to combine message and author 
	and to add an easy reply method
	"""
	
	def __init__(self, m, a, bot):
		self.content = m
		self.author = a
		self.bot = bot
	#
	
	async def reply(self, m):
		"""\
		Reply, should mention author
		"""
		
		await self.bot.say("@{}, {}".format(self.author, m))
	#
	
class Command:
	
	"""\
	A command class to provide methods we can use with it
	"""
	
	def __init__(self, bot, comm, *, alias=[], desc='', admin=False, unprefixed=False, listed=True):
		self.bot = bot
		self.comm = comm
		self.desc = desc
		self.alias = alias
		self.admin = admin
		self.listed = listed
		self.unprefixed = unprefixed
		bot.commands.append(self)
	#
	
	def subcommand(self, *args, **kwargs):
		"""\
		Create subcommands 
		"""
		if not hasattr(self, 'subcommands'): # check if commands is already on the command
			self.subcommands = []
		return SubCommand(self, *args, **kwargs) # set subcommand
	#
	
	def __call__(self, func):
		"""\
		Make it able to be a decorator
		"""
		
		self.func = func
		
		if self.bot.debug:
			print("Added command: " + self.comm)
			
		return self
	#
	
	async def run(self, message):
		if self.bot.debug:
			print("Preparing to run {0.comm}".format(self))
		"""\
		Does type checking for command arguments
		"""
	
		args = message.content.split(" ") # Get arguments from message
		del args[0]
		
		args_name = inspect.getfullargspec(self.func)[0] # Get amount of arguments needed
		del args_name[0]
		
		if len(args) > len(args_name):
			args[len(args_name)-1] = " ".join(args[len(args_name)-1:]) # Put all leftovers in final argument
			
			for i in range(len(args_name),len(args)):
				del args[len(args_name)] # Remove from original
				
		elif len(args) < len(args_name): # Not enough arguments, Error
			raise CommandError('Not enough arguments for {}, required arguments: {}'.format(self.comm, ', '.join(args_name)))
			
		ann = self.func.__annotations__ # Get type hints
		
		for x in range(0, len(args_name)): # loop through arguments
			v = args[x]
			k = args_name[x]
			
			if type(v) == ann[k]: 
				pass # Content is correct type already
				
			else:
				try:
					v = ann[k](v) # Try calling __init__() with the argument
					
				except: # Invalid type or type unsupported
					raise CommandError("Invalid type: got {}, {} expected".format(ann[k].__name__, v.__name__))
					
			args[x] = v # add to arguments
			
		try:
			if hasattr(self, 'subcommands'): # Command has subcommands
				subcomm = args.pop(0) # Find subcommands
				
				for s in self.subcommands:
					if subcomm == s.comm:
						if self.bot.debug:
							print("Calling {0.comm} with arguments: {1}".format(s, args))
						await s.func(message, *args) # Run subcommand
						break
				
			else: # Run command
				if self.bot.debug:
					print("Calling {0.comm} with arguments: {1}".format(self, args))
				await self.func(message, *args)
				
		except:
			await self.bot.say(self.desc)
	#

	
class SubCommand(Command):
	"""\
	Subcommand class
	"""
	
	def __init__(self, parent, comm, *, desc=''):
		self.comm = comm
		self.parent = parent
		self.bot = parent.bot
		self.parent.subcommands.append(self) # add to parent command
	#
	
	def __call__(self, func):
		"""\
		Make it a decorator
		"""
		self.func = func
		
		if self.bot.debug:
			print("Added subcommand: " + self.comm)
			
		return self
	#
	
	
class Bot:
	"""\
	Bot class without command support 
	"""
	
	def __init__(self, *, oauth=None, user=None, channel='#twitch', prefix='!', admins=[], debug=False):
		sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding=sys.stdout.encoding, errors="backslashreplace", line_buffering=True) # I should probably remove this but fuck it
		self.prefix = prefix
		self.loop = asyncio.get_event_loop()
		self.host = 'irc.twitch.tv'
		self.port = 6667
		self.commands = [] # Add this in case people want to use it
		self.oauth = oauth
		self.nick = user
		self.chan = "#" + channel
		self.admins = admins
		self.debug = debug
	#
	
	def override(self, func):
		"""\
		Allows for overriding certain functions
		"""
		setattr(self, func.__name__, func)
	#
	
	def start(self):
		"""\
		Starts the event loop,
		Blocking call
		"""
		
		self.loop.run_until_complete(self._tcp_echo_client())
	#
	
	
	# ------------------------ #
	# --- Needed Functions --- #
	# ------------------------ #
	
	async def _pong(self, msg):
		"""\
		Tell remote we're still alive
		"""
		self.writer.write(bytes('PONG %s\r\n' % msg, 'UTF-8'))
	#

	async def say(self, msg):
		"""\
		Send messages
		"""
		if self.debug:
			print(self.chan, msg)
		self.writer.write(bytes('PRIVMSG %s :%s\r\n' % (self.chan, str(msg)), 'UTF-8'))
	#

	async def _nick(self):
		"""\
		Send name
		"""
		self.writer.write(bytes('NICK %s\r\n' % self.nick, 'UTF-8'))
	#

	async def _pass(self):
		"""\
		Send oauth token
		"""
		self.writer.write(bytes('PASS %s\r\n' % self.oauth, 'UTF-8'))
	#
	
	async def _join(self):
		"""\
		Join a channel
		"""
		self.writer.write(bytes('JOIN %s\r\n' % self.chan, 'UTF-8'))
	#

	async def _part(self):
		"""\
		Leave a channel
		"""
		self.writer.write(bytes('PART %s\r\n' % self.chan, 'UTF-8'))
	#

	async def _special(self, mode):
		"""\
		Allows for more events
		"""
		self.writer.write(bytes('CAP REQ :twitch.tv/%s\r\n' % mode,'UTF-8'))
	#
	
	async def _tcp_echo_client(self):
		"""\
		Receive messages and send to parser
		"""
	
		self.reader, self.writer = await asyncio.open_connection(self.host, self.port, loop=self.loop) # Open connections
		
		await self._pass()		#
		await self._nick()		# Log in and join
		await self._join()		#
		
		modes = ['JOIN','PART','MODE']
		for m in modes:
			await self._special(m)
		
		while True: # Loop to keep receiving messages
			rdata = (await self.reader.read(1024)).decode('utf-8') # Received bytes to str
			
			if self.debug:
				print(rdata)
			try:
				p = re.compile("(?P<data>.*?) (?P<action>[A-Z]*?) (?P<data2>.*)")
				m = p.match(rdata)
			
				action = m.group('action')
				data = m.group('data')
				data2 = m.group('data2')
			except:
				pass
			else:
				try:
					if action == 'PING':
						await self._pong(line[1]) # Send PONG to server
						
					elif action == 'PRIVMSG':
						sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)@(?P=author).tmi.twitch.tv", data).group('author')
						message = re.match("#[a-zA-Z0-9_]+ :(?P<content>.+)", data2).group('content')

						if self.debug:
							print(sender, message)
							
						messageobj = Message(message, sender, self) # Create Message object
						
						await self.message(messageobj) # Try parsing
					
					elif action == 'JOIN':
						sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)@(?P=author).tmi.twitch.tv", data).group('author')
						await self.user_join(sender)
						
					elif action == 'PART':
						sender = re.match(":(?P<author>[a-zA-Z0-9_]+)!(?P=author)@(?P=author).tmi.twitch.tv", data).group('author')
						await self.user_leave(sender)
					
					elif action == 'MODE':
						m = re.match("#[a-zA-Z0-9]+ (?P<mode>[+-])o (?P<user>.+?)", data2)
						mode = m.group('mode')
						user = m.group('user')
						await self.user_mode(mode, user)
					
					else:
						pass # Unhandled type
						
				except Exception as e:
					fname = e.__traceback__.tb_next.tb_frame.f_code.co_name
					print("Ignoring exception in {}:".format(fname))
					traceback.print_exc()
	#
	
	async def user_join(self, user):
		"""\
		Called when a user joins
		"""
		pass
	#
	
	async def user_leave(self, user):
		"""\
		Called when a user leaves
		"""
		pass
	#
	
	async def user_mode(self, mode, user):
		"""\
		Called when a user is opped/de-opped
		"""
		pass
	#
	
	async def message(self, rm):
		"""\
		Called when a message is sent
		"""
		pass
	#
	
	
class CommandBot(Bot):
	"""\
	Allows the usage of Commands more easily
	"""
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
	#
	
	async def message(self, rm):
		"""\
		Shitty command parser I made
		"""
		
		if self.debug:
			print(rm.content)
			
		if rm.content.startswith(self.prefix):
			if self.debug:
				print("Found prefix")
	
			m = rm.content[len(self.prefix):]
			l = m.split(" ")
			w = l.pop(0).lower().replace("\r","")
			m = " ".join(l)
			
			if self.debug:
				print("Searching for:", w)
			
			for c in self.commands:
				if (w == c.comm or w in c.alias) and not c.unprefixed:
					if self.debug:
						print("Found command: {0.comm}".format(c))

					if c.admin and not rm.author in self.admins:
						await rm.reply("You are not allowed to use this command")
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
					if self.debug:
						print("Found unprefixed command")
					
					await c.run(rm)
	#
	
	def command(self, *args, **kwargs):
		"""\
		Add a command 
		"""
		
		return Command(self, *args, **kwargs)
	#
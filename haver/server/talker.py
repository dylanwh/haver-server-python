import time
from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import reactor
from twisted.internet          import task

from haver.server.errors  import Fail, Bork
from haver.server.thing   import User, Room
from haver.server.asserts import *
from haver.server.help    import Help
import haver.server
import haver.protocol

assert hasattr(Room, 'join')

def login(func):
	func.phase = 'login'
	return func

def connect(func):
	func.phase = 'connect'
	return func

def normal(func):
	func.phase = 'normal'
	return func

def magical(func):
	func.phase = 'magical'
	return func


def noreply(func):
	func.noreply = True
	return func

def phase(phase):
	def code(func):
		func.phase = phase
		return func
	return code

def ext(name):
	def code(func):
		func.extension = name
		return func
	return code

def failures(*failures):
	def code(func):
		func.failures = failures
		return func
	return code

def reply(*reply):
	def code(func):
		if not hasattr(func, 'replies'):
			func.replies = []
		func.replies.append(reply)
		return func
	return code

help = None

class HaverFactory(Factory):

	def __init__(self, house, ssl = False):
		global help
		if help is None:
			help = Help(HaverTalker)
		self.house    = house
		self.protocol = HaverTalker
		self.ssl = ssl

	def buildProtocol(self, addr):
		p = self.protocol(addr)
		p.factory = self
		p.house   = self.house
		return p
		
class HaverTalker(LineOnlyReceiver):
	def __init__(self, addr):
		self.addr      = addr
		self.delimiter = "\n"
		self.phase     = 'none'

		self.lastCmd   = time.time()
		self.tardy     = None
		self.pingTime  = 60
		self.pingLoop  = task.LoopingCall(self.checkPing)
		self.pingLoop.start(self.pingTime)

	def invoke(self, cmd, args):
		self.cmd = cmd
		self.lastCmd = time.time()
		try:
			method = cmd.replace(':', '_')
			func  = getattr(self, method)
			phase = func.phase
		except AttributeError:
			raise Fail('unknown.command')
		
		if phase != self.phase and phase != 'magical':
			raise Fail('strange.command', self.phase, phase)

		assert_cmd(cmd)
		assert_arity(func, args)

		newphase = func(*args)
		if newphase is not None:
			self.phase = newphase

	def lineReceived(self, line):
		try:
			try:
				cmd, args = haver.protocol.parse( line.rstrip("\r") )
				self.tag = None
				self.invoke(cmd, args)
			except Fail, failure:
				log.msg('Command %s failed with failure %s (%s)' % (self.cmd, failure.name, str(failure.args)))
				if self.phase != 'connect':
					self.sendMsg('FAIL', self.cmd, failure.name, *failure.args)
				else:
					self.transport.loseConnection()

			except Bork, bork:
				log.msg('Borking client: %s' % bork.msg)
				if self.phase != 'connect':
					self.phase = 'bork'
					self.sendMsg('BORK', bork.msg)
				self.disconnect('bork')
		finally:
			self.tag = None

	def sendMsg(self, cmd, *args):
		if self.tag is not None:
			args = (self.tag, cmd) + args
			cmd = 'TAG'
		self.sendLine(haver.protocol.deparse(cmd, args) + "\r")
	
	def connectionMade(self):
		self.phase = 'connect'
		log.msg('New client from ' + str(self.addr))

	def connectionLost(self, reason):
		log.msg('Lost client from ' + str(self.addr))
		self.quit('closed')

	def init(self, user):
		self.user = user
		user['address'] = self.addr.host
		user['version'] = self.version
		if self.factory.ssl:
			user['secure'] = 'yes'
		else:
			user['secure'] = 'no'
		del self.version

	def quit(self, why, reason = None):
		house = self.factory.house
		
		if self.phase == 'normal':
			for room in list(self.user.rooms):
				if reason is not None:
					why = "%s: %s" % (why, reason)
				room.part(self.user, 'quit', why)

			house.remove(self.user)
			self.phase = 'quit'

	def disconnect(self, *args):
		self.sendMsg('BYE', *args)
		self.transport.loseConnection()
		self.quit(*args)

	def checkPing(self):
		"""Called every once and a while. Issues a ping if this client hasn't sent a command recently"""
		now      = time.time()
		duration = int (now - self.lastCmd)

		if self.phase != 'normal':
			self.tardy = None
			return

		if self.tardy is not None:
			self.sendMsg('BYE', 'ping')
			self.disconnect('ping')
			return

		if duration > self.pingTime:
			self.sendMsg('PING', 'foo')
			self.tardy = 'foo'
	
	@connect
	@reply('HAVER', 'host', 'server_version', 'server_extensions')
	def HAVER(self, version, extensions = '', *rest):
		"""Clients must issue this message before any others."""
		self.version = version
		self.extensions = set(extensions.split(','))
		ver = "%s/%s" % (haver.server.name, haver.server.version)
		print(type(help.extensions))
		self.sendMsg('HAVER', self.factory.house.host, ver, ",".join(help.extensions))
		return 'login'

	@login
	@failures('reserved.name', 'invalid.name', 'existing.thing')
	@reply('HELLO', 'name', 'address')
	def IDENT(self, name):
		"""Associate a client connection with name {name}. May not be used after the server sends HELLO."""
		house = self.factory.house
		assert_name(name)
		assert_name_unreserved(name)
		user = User(name, self)
		house.add(user)
		self.sendMsg('HELLO', name, str(self.addr.host))

		self.init(user)
		return 'normal'

	@login
	@ext('ghost')
	@failures('reserved.name', 'invalid.name', 'existing.thing', 'mismatch.ip')
	@reply('HELLO', 'name', 'address')
	def GHOST(self, name, *rest):
		"""Disconnect a stuck nick and login as it."""
		try:
			return self.IDENT(name)
		except Fail, f:
			if f.name == 'existing.thing':
				house = self.factory.house
				user  = house.lookup('user', name)
				if user['address'] != self.addr.host:
					# TODO: I don't think failure name.
					raise Fail('mismatch.ip')
				user.talker.disconnect('ghost')
				return self.IDENT(name, *rest)
			else:
				raise f

	@normal
	@failures('invalid.name', 'unknown.thing')
	@reply('FROM', 'yourname', 'kind', 'msg', '[rest...]')
	def TO(self, name, kind, msg, *rest):
		"""Send a private message"""
		assert_name(name)
		house = self.factory.house
		user  = house.lookup('user', name)
		user.sendMsg('FROM', self.user.name, kind, msg, *rest)
		self.user.updateIdle()

	@normal
	@failures('invalid.name', 'unknown.thing')
	@reply('IN', 'name', 'yourname', 'kind', 'msg', '[rest...]')
	def IN(self, name, kind, msg, *rest):
		"""Send a public message"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		room.sendMsg('IN', room.name, self.user.name, kind, msg, *rest)
		self.user.updateIdle()

	@normal
	@failures('invalid.name', 'unknown.thing', 'strange.join', 'insecure')
	@reply('JOIN', 'room', 'yourname')
	def JOIN(self, name):
		"""Join room {name}"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		if room['secure'] == 'yes' and self.user['secure'] != 'yes':
			raise Fail('insecure')
		room.join(self.user)

	@normal
	@failures('invalid.name', 'unknown.thing', 'strange.part')
	@reply('PART', 'room', 'yourname')
	def PART(self, name):
		"""Part room {name}"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		room.part(self.user, 'normal')

	@normal
	def BYE(self, detail = None):
		"""Disconnect from the server."""
		if detail is None:
			self.disconnect('bye')
		else:
			self.disconnect('bye', detail)

	@normal
	@noreply
	def PONG(self, token):
		"""Respond to a PING."""
		if self.tardy is None:
			raise Bork("You already did that.")
		else:
			self.tardy = None

	@normal
	@reply('OUCH', 'token')
	def POKE(self, token="datetime"):
		"""Hurt the server. Server will respond with OUCH"""
		self.sendMsg('OUCH', token)

	@normal
	@failures('invalid.name', 'existing.thing', 'reserved.name')
	@reply('OPEN', 'name')
	def OPEN(self, name):
		"""Create a new room. This command may be restricted to server-admins only."""
		assert_name(name)
		assert_name_unreserved(name)

		house = self.factory.house
		room  = Room(name, owner = self.user.name)
		house.add(room)
		self.sendMsg('OPEN', name)

	@normal
	@failures('invalid.name', 'unknown.thing', 'access.owner')
	@reply('CLOSE', 'name')
	def CLOSE(self, name):
		"""Destroy a room. Only the owner can do this."""
		assert_name(name)
		assert_name_unreserved(name)

		house = self.factory.house
		room = house.lookup('room', name)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room.name, room['owner'], self.user.name)

		for user in room:
			user.part(room.name, 'close', self.user.name)
		house.remove(room)
		self.sendMsg('CLOSE', name)

	@normal
	@failures('unknown.namespace', 'unknown.thing')
	@reply('INFO', 'ns', 'name', 'key', 'value', '...')
	def INFO(self, ns, name):
		"""DEPRECATED. Get a listing of information for a particular thing."""
		house = self.factory.house
		thing = house.lookup(ns, name)
		self.sendMsg('INFO', ns, name, *thing.info())

	@normal
	@failures('unknown.room')
	@reply('ROOMINFO', 'name', 'key', 'value', '...')
	def ROOMINFO(self, name):
		"""Query metadata about a user"""
		house = self.factory.house
		room = house.lookup("room", name)
		self.sendMsg('ROOMINFO', name, *room.info())

	@normal
	@failures('unknown.user')
	@reply('USERINFO', 'name', 'key', 'value', '...')
	def USERINFO(self, name):
		"""Query metadata about a user"""
		house = self.factory.house
		user = house.lookup("user", name)
		self.sendMsg('USERINFO', name, *user.info())

	@normal
	@reply('USERS', 'names...')
	def USERS(self):
		"""Return a list of users on the server."""
		house = self.factory.house
		names = [ x for x in house.lookup_namespace('user') ]
		self.sendMsg('USERS', *names)
	
	@normal
	@reply('ROOMS', 'names...')
	def ROOMS(self):
		"""Return a list of rooms on the server"""
		house = self.factory.house
		names = [ x for x in house.lookup_namespace('room') ]
		self.sendMsg('ROOMS', *names)
	
	@normal
	@failures('invalid.name', 'unknown.thing')
	@reply('USERSOF', 'name', 'users...')
	def USERSOF(self, name):
		"""Return a list of users in the channel $name"""
		house = self.factory.house
		room = house.lookup('room', name)
		names = [ x.name for x in room.users ]
		self.sendMsg('USERSOF', room.name,  *names)

	@normal
	@failures('invalid.name', 'unknown.thing')
	def KICK(self, rname, uname):
		house = self.factory.house
		room = house.lookup('room', rname)
		user = house.lookup('user', uname)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		room.part(user, 'kick', self.user.name)

	@normal
	@failures('unknown.thing', 'invalid.name')
	def SECURE(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		names = []
		for user in room.users:
			if user['secure'] == 'no':
				room.part(user, 'secure', self.user.name)
				names.append(user.name)

		room['secure'] = 'yes'
		self.sendMsg('SECURE', name, *names)

	@normal
	@ext('help')
	@reply('HELP:COMMANDS', 'commands...')
	def HELP_COMMANDS(self):
		commands = [ x.replace('_', ':') for x in help.commands ]
		self.sendMsg('HELP:COMMANDS', *commands)

	@magical
	@ext('tag')
	def TAG(self, tag, cmd, *args):
		"""ehird's tagging thing"""
		self.tag = tag
		self.invoke(cmd, args)

	@normal
	@ext('help')
	@reply('HELP:FAILURES', 'failures...')
	def HELP_FAILURES(self):
		self.sendMsg('HELP:FAILURES', *help.failures)

	@normal
	@ext('help')
	@failures('unknown.command')
	def HELP_COMMAND(self, cmd):
		"""Get usage information on a particular command"""
		try:
			info = help.command(cmd.replace(':', '_'))
			args = []
			for k in info:
				args.append(k)
				args.append(info[k])
			self.sendMsg('HELP:COMMAND', cmd, *args)
		except AttributeError, a:
			print a
			raise Fail('unknown.command', cmd)

	HELP = HELP_COMMAND

	@normal
	@ext('help')
	def HELP_FAILURE(self, name):
		"""The server will respond to this with a string describing the failure $name.
		The string will contain shell-style argument variables ($0, $1, etc).
		$0 should be replaced by the command that triggered the failure, and $1..$n should be replaced by the arguments of it."""
		self.sendMsg('HELP:FAILURE', name, help.fail(name))

	@normal
	@ext('help')
	def HELP_REPLIES(self, command):
		"""Displays the reply for a command."""
		self.sendMsg('HELP:REPLIES', command, *help.reply(command))

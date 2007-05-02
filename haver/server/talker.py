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

def command(phase, exten = None):
	def code(func):
		func.phase = phase
		if exten is not None:
			func.extension = exten
		return func
	return code

def failure(*failures):
	def code(func):
		func.failures = failures
		return func
	return code

class HaverFactory(Factory):

	def __init__(self, house, ssl = False):
		self.house    = house
		self.help     = Help(HaverTalker)
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

	def lineReceived(self, line):
		try:
			cmd, args = haver.protocol.parse( line.rstrip("\r") )
			self.cmd = cmd
			self.lastCmd = time.time()
			try:
				method = cmd.replace(':', '_')
				func  = getattr(self, method)
				phase = func.phase
			except AttributeError:
				raise Fail('unknown.command')
			
			if phase != self.phase:
				raise Fail('strange.command', self.phase, phase)

			assert_cmd(cmd)
			assert_arity(func, args)

			newphase = func(*args)
			if newphase is not None:
				self.phase = newphase
		
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

	def sendMsg(self, cmd, *args):
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
	
	@command('connect')
	def HAVER(self, version, extensions = '', *rest):
		"""Clients must issue this message before any others."""
		self.version = version
		self.extensions = set(extensions.split(','))
		ver = "%s/%s" % (haver.server.name, haver.server.version)
		self.sendMsg('HAVER', self.factory.house.host, ver, ",".join(self.factory.help.extensions))
		return 'login'

	@command('login')
	@failure('reserved.name', 'invalid.name', 'existing.thing')
	def IDENT(self, name):
		"""Request user name."""
		house = self.factory.house
		assert_name(name)
		assert_name_unreserved(name)
		user = User(name, self)
		house.add(user)
		self.sendMsg('HELLO', name, str(self.addr.host))

		self.init(user)
		return 'normal'

	@command('login', 'ghost')
	@failure('reserved.name', 'invalid.name', 'existing.thing', 'mismatch.ip')
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

	@command('normal')
	@failure('invalid.name', 'unknown.thing')
	def TO(self, name, kind, msg, *rest):
		"""Send a private message"""
		assert_name(name)
		house = self.factory.house
		user  = house.lookup('user', name)
		user.sendMsg('FROM', self.user.name, kind, msg, *rest)
		self.user.updateIdle()

	@command('normal')
	@failure('invalid.name', 'unknown.thing')
	def IN(self, name, kind, msg, *rest):
		"""Send a public message"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		room.sendMsg('IN', room.name, self.user.name, kind, msg, *rest)
		self.user.updateIdle()

	@command('normal')
	@failure('invalid.name', 'unknown.thing', 'strange.join', 'insecure')
	def JOIN(self, name):
		"""Join room {name}"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		if room['secure'] == 'yes' and self.user['secure'] != 'yes':
			raise Fail('insecure')
		room.join(self.user)

	@command('normal')
	@failure('invalid.name', 'unknown.thing', 'strange.part')
	def PART(self, name):
		"""Part room {name}"""
		assert_name(name)
		house = self.factory.house
		room  = house.lookup('room', name)
		room.part(self.user, 'normal')

	@command('normal')
	def BYE(self, detail = None):
		"""Disconnect from the server."""
		if detail is None:
			self.disconnect('bye')
		else:
			self.disconnect('bye', detail)

	@command('normal')
	def PONG(self, token):
		"""Respond to a PING."""
		if self.tardy is None:
			raise Bork("You already did that.")
		else:
			self.tardy = None

	@command('normal')
	def POKE(self, token):
		"""Hurt the server. Server will respond with OUCH"""
		self.sendMsg('OUCH', token)

	@command('normal')
	@failure('invalid.name', 'existing.thing', 'reserved.name')
	def OPEN(self, name):
		"""Create a new room"""
		assert_name(name)
		assert_name_unreserved(name)

		house = self.factory.house
		room  = Room(name, owner = self.user.name)
		house.add(room)
		self.sendMsg('OPEN', name)

	@command('normal')
	@failure('invalid.name', 'unknown.thing', 'access.owner')
	def CLOSE(self, name):
		"""Destroy a room."""
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

	@command('normal')
	@failure('unknown.namespace', 'unknown.thing')
	def INFO(self, ns, name):
		"""Get a listing of information for a particular thing"""
		house = self.factory.house
		thing = house.lookup(ns, name)
		self.sendMsg('INFO', ns, name, *thing.info())

	@command('normal')
	@failure('unknown.namespace')
	def LIST(self, ns):
		"""Return a list of things in the namespace $ns"""
		house = self.factory.house
		names = [ x.name for x in house.things(ns) ]
		self.sendMsg('LIST', ns, *names)

	@command('normal')
	@failure('invalid.name', 'unknown.thing')
	def USERS(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		names = [ x.name for x in room.users ]
		self.sendMsg('USERS', *names)

	@command('normal')
	@failure('invalid.name', 'unknown.thing')
	def KICK(self, rname, uname):
		house = self.factory.house
		room = house.lookup('room', rname)
		user = house.lookup('user', uname)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		room.part(user, 'kick', self.user.name)

	@command('normal')
	@failure('unknown.thing', 'invalid.name')
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

	@command('normal', 'help')
	def HELP_COMMANDS(self):
		commands = [ x.replace('_', ':') for x in self.factory.help.commands ]
		self.sendMsg('HELP:COMMANDS', *commands)

	@command('normal', 'help')
	def HELP_FAILURES(self):
		self.sendMsg('HELP:FAILURES', *self.factory.help.failures)

	@failure('unknown.command')
	@command('normal', 'help')
	def HELP_COMMAND(self, cmd):
		"""Get usage information on a particular command"""
		try:
			info = self.factory.help.command(cmd.replace(':', '_'))
			args = []
			for k in info:
				args.append(k)
				args.append(info[k])
			self.sendMsg('HELP:COMMAND', cmd, *args)
		except AttributeError, a:
			print a
			raise Fail('unknown.command', cmd)

	@command('normal', 'help')
	def HELP_FAILURE(self, name):
		"""The server will respond to this with a string describing the failure $name.
		The string will contain shell-style argument variables ($0, $1, etc).
		$0 should be replaced by the command that triggered the failure, and $1..$n should be replaced by the arguments of it."""
		self.sendMsg('HELP:FAILURE', name, *self.factory.help.fail(name))

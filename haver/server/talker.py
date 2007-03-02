import re, inspect, time

from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import reactor
from twisted.internet          import task

from haver.server.errors import Fail, Bork
from haver.server.entity import User, Room, assert_name
from haver.server.help   import Help
import haver.server


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

def check_arity(f, args):
	arity_max = f.func_code.co_argcount - 1

	if f.func_defaults is None:
		arity_min = arity_max
		arity_text = str(arity_min)
	else:
		arity_min = arity_max - len(f.func_defaults)
		arity_text = "%d-%d" % (arity_min, arity_max)

	catchall = lambda x: inspect.getargspec(x)[2] is None

	if (len(args) > arity_max and catchall(f)) or len(args) < arity_min:
		raise Fail('arity', arity_text, str(len(args)))

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
		self.cmdpat    = re.compile('^[A-Z][A-Z:]*$')
		self.delimiter = "\n"
		self.phase     = 'none'

		self.lastCmd   = time.time()
		self.tardy     = None
		self.pingTime  = 60
		self.pingLoop  = task.LoopingCall(self.checkPing)
		self.pingLoop.start(self.pingTime)

	def parseLine(self, line):
		if len(line) == 0 or line == "\r":
			print "Got empty line"
			raise Bork('Your line is empty')

		msg = line.rstrip("\r").split("\t")

		if not self.cmdpat.match(msg[0]):
			print "This is an example of a badly formed command: %s" % msg[0]
			raise Bork("You're not the man I married!")

		return (msg[0], msg[1:])


	def lineReceived(self, line):
		try:
			cmd, args = self.parseLine(line)
			self.cmd = cmd
			self.lastCmd = time.time()
			method = cmd.replace(':', '_')
			if hasattr(self, method):
				f = getattr(self, method)
				if not hasattr(f, 'phase'):
					raise Fail('unknown.command', cmd)
				if f.phase != self.phase:
					raise Fail('invalid.command', cmd, "wrong phase")

				check_arity(f, args)
				newphase = f(*args)
				if newphase is not None:
					self.phase = newphase
			else:
				raise Fail('unknown.command', cmd)
			
		except Fail, failure:
			log.msg('Command %s failed with failure %s (%s)' % (self.cmd, failure.name, str(failure.args)))
			if self.phase != 'connect':
				self.sendMsg('FAIL', self.cmd, failure.name, *failure.args)
			else:
				self.transport.loseConnection()

		except Bork, bork:
			log.msg('Borking client: %s' % bork.msg)
			if self.phase != 'connect':
				self.sendMsg('BORK', bork.msg)
			self.disconnect('bork')

	def sendMsg(self, *msg):
		self.sendLine("\t".join(msg) + "\r")
	
	
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
			for name in self.user.rooms:
				room = house.lookup('room', name)
				room.remove(self.user)
				if reason is None:
					room.sendMsg('QUIT', self.user.name, why)
				else:
					room.sendMsg('QUIT', self.user.name, why, reason)

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
		self.sendMsg('HAVER', self.factory.house.name, ver, ",".join(self.factory.help.extensions))
		return 'login'

	
	@command('login', 'spoon')
	def SPOON_ATTACH(self, name, key):
		"""Resume a detached session."""
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		user = house.lookup('user', name)
		if user.is_attached():
			raise Fail('already.attached')
		user.attach(self, key)

		self.init(user)
		return 'normal'

	@command('normal', 'spoon')
	def SPOON_DETACH(self, key):
		"""Detach session, to be later resumed by SPOON:ATTACH"""
		self.user.detach(key)
		self.transport.loseConnection()
		return 'spoon'

	@command('login')
	@failure('reserved.name', 'invalid.name', 'existing.entity')
	def IDENT(self, name):
		"""Request user name."""
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		user = User(name, self)
		house.add(user)
		self.sendMsg('HELLO', name, str(self.addr.host))

		self.init(user)
		return 'normal'

	@command('login', 'ghost')
	@failure('reserved.name', 'invalid.name', 'existing.entity', 'mismatch.ip')
	def GHOST(self, name, *rest):
		"""Disconnect a stuck nick and login as it."""
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		try:
			return self.IDENT(name, *rest)
		except Fail, f:
			if f.name == 'existing.entity':
				user = house.lookup('user', name)
				if user['address'] != self.addr.host:
					# TODO: I don't think failure name.
					raise Fail('mismatch.ip')
				user.talker.disconnect('ghost')
				return self.IDENT(name, *rest)
			else:
				raise f

	@command('normal')
	@failure('invalid.name', 'unknown.entity')
	def TO(self, target, type, msg, *rest):
		"""Send a private message"""
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('user', target).sendMsg('FROM', self.user.name, type, msg, *rest)

	@command('normal')
	@failure('invalid.name', 'unknown.entity')
	def IN(self, name, type, msg, *rest):
		"""Send a public message"""
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('room', name).sendMsg('IN', name, self.user.name, type, msg, *rest)

	@command('normal')
	@failure('invalid.name', 'unknown.entity', 'already.joined', 'insecure')
	def JOIN(self, name):
		"""Join a room"""
		house = self.factory.house
		room = house.lookup('room', name)
		if room['secure'] == 'yes' and self.user['secure'] == 'no':
			raise Fail('insecure', name)

		self.user.join(name)
		try:
			room.add(self.user)
		except Fail, f:
			self.user.part(name)
			raise f

		room.sendMsg('JOIN', name, self.user.name)

	@command('normal')
	@failure('invalid.name', 'unknown.entity', 'already.parted')
	def PART(self, name):
		"""Part a room"""
		house = self.factory.house
		room = house.lookup('room', name)
		self.user.part(name)
		room.sendMsg('PART', name, self.user.name)
		room.remove(self.user)

	@command('normal')
	def BYE(self, detail = None):
		"""Disconnect from the server. detail must not contain any spaces."""
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
	@failure('invalid.name', 'existing.entity')
	def OPEN(self, name):
		"""Create a new room"""
		house = self.factory.house
		room  = Room(name, owner = self.user.name)
		house.add(room)
		self.sendMsg('OPEN', name)

	@command('normal')
	@failure('invalid.name', 'unknown.entity', 'access.owner')
	def CLOSE(self, name):
		"""Destroy a room."""
		house = self.factory.house
		room = house.lookup('room', name)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room.name, room['owner'], self.user.name)

		for user in room:
			user.sendMsg('PART', name, user.name, 'close', self.user.name)
			user.part(room.name)
		house.remove(room)
		self.sendMsg('CLOSE', name)


	@command('normal')
	@failure('invalid.namespace', 'unknown.entity', 'access.owner')
	def INFO(self, ns, name):
		"""Get a listing of attributes for a particular entity"""
		house = self.factory.house
		entity = house.lookup(ns, name)
		self.sendMsg('INFO', ns, name, *entity.info)

	@command('normal')
	def LIST(self, name, ns):
		"""Deprecated. See LS and USERS"""
		house = self.factory.house
		if ns == 'channel':
			ns = 'room'
		if name == '&lobby':
			names = [ x.name for x in house.members(ns) ]
			self.sendMsg('LIST', name, ns, *names)
		else:
			room = house.lookup('room', name)
			names = [ x.name for x in room ]
			self.sendMsg('LIST', name, ns, *names)

	@command('normal')
	@failure('unknown.namespace')
	def LS(self, ns):
		house = self.factory.house
		names = [ x.name for x in house.members(ns) ]
		self.sendMsg('LS', ns, *names)

	@command('normal')
	@failure('invalid.name', 'unknown.entity')
	def USERS(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		names = [ x.name for x in room ]
		self.sendMsg('USERS', *names)

	@command('normal')
	@failure('invalid.name', 'unknown.entity')
	def KICK(self, rname, uname):
		house = self.factory.house
		room = house.lookup('room', rname)
		user = house.lookup('user', uname)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		user.part(rname)
		room.sendMsg('PART', room.name, user.name, 'kick', self.user.name)
		room.remove(user)

	@command('normal')
	@failure('unknown.entity', 'invalid.name')
	def SECURE(self, name):

		house = self.factory.house
		room = house.lookup('room', name)
		names = []
		for user in room:
			if user['secure'] == 'no':
				user.part(name)
				room.sendMsg('PART', room.name, user.name, 'secure', self.user.name)
				room.remove(user)
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
	def HELP_FAILURE(self, name, cmd = None, *args):
		self.sendMsg('HELP:FAILURE', name, self.factory.help.fail(name, cmd, *args))

import re

from time import time
from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import reactor
from twisted.internet          import task

from haver.server.errors import Fail, Bork
from haver.server.entity import User, Room, assert_name
import haver.server

def phase(phase):
	def code(func):
		func.phase = phase
		return func
	return code

def check_arity(f, args):
	arity_max = f.func_code.co_argcount - 1;
	if f.func_defaults is None:
		arity_min = arity_max
		arity_text = str(arity_min)
	else:
		arity_min = arity_max - len(f.func_defaults)
		arity_text = "%d-%d" % (arity_min, arity_max)

	if len(args) > arity_max or len(args) < arity_min:
		raise Fail('arity', f.__name__, arity_text, str(len(args)))

class HaverFactory(Factory):

	def __init__(self, house, ssl = False):
		self.house = house
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
		self.cmdpat    = re.compile('^[A-Z][A-Z:_-]*$')
		self.delimiter = "\n"
		self.phase     = 'none'

		self.lastCmd   = time()
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
			self.lastCmd = time()
			method = cmd.replace(':', '_')
			if hasattr(self, method):
				f = getattr(self, method)
				if not hasattr(f, 'phase'):
					raise Fail('unknown.command', cmd)
				if f.phase != self.phase:
					raise Fail('invalid.command', cmd)

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
		now      = time()
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
	

	@phase('connect')
	def HAVER(self, version, supports = '', *rest):
		self.version = version
		self.supports = supports.split(',')
		self.sendMsg('HAVER', self.factory.house.name, "%s/%s" % (haver.server.name, haver.server.version))
		return 'login'

	@phase('login')
	def SPOON_ATTACH(self, name, key):
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

	@phase('normal')
	def SPOON_DETACH(self, key):
		self.user.detach(key)
		self.transport.loseConnection()
		return 'spoon'

	@phase('login')
	def IDENT(self, name, *rest):
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		user = User(name, self)
		house.add(user)
		self.sendMsg('HELLO', name, str(self.addr.host))

		self.init(user)
		return 'normal'

	@phase('login')
	def GHOST(self, name, *rest):
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		try:
			return self.IDENT(name, *rest)
		except Fail, f:
			if f.name == 'exists.user':
				user = house.lookup('user', name)
				if user['address'] != self.addr.host:
					# TODO: I don't think failure name.
					raise Fail('mismatch.ip')
				user.talker.disconnect('ghost')
				return self.IDENT(name, *rest)
			else:
				raise f

	@phase('normal')
	def TO(self, target, kind, msg, *rest):
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('user', target).sendMsg('FROM', self.user.name, kind, msg, *rest)

	@phase('normal')
	def IN(self, name, kind, msg, *rest):
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('room', name).sendMsg('IN', name, self.user.name, kind, msg, *rest)

	@phase('normal')
	def JOIN(self, name):
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

	@phase('normal')
	def PART(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		self.user.part(name)
		room.sendMsg('PART', name, self.user.name)
		room.remove(self.user)

	@phase('normal')
	def BYE(self, detail = None):
		if detail is None:
			self.disconnect('bye')
		else:
			self.disconnect('bye', detail)


	@phase('normal')
	def PONG(self, nonce):
		if self.tardy is None:
			raise Bork('You smell like SPAM!')
		else:
			self.tardy = None

	@phase('normal')
	def POKE(self, nonce):
		self.sendMsg('OUCH', nonce)

	@phase('normal')
	def OPEN(self, name):
		house = self.factory.house
		room  = Room(name, owner = self.user.name)
		house.add(room)
		self.sendMsg('OPEN', name)

	@phase('normal')
	def CLOSE(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		for user in room:
			user.sendMsg('PART', name, user.name, 'close', self.user.name)
			user.part(room.name)
		house.remove(room)
		self.sendMsg('CLOSE', name)


	@phase('normal')
	def INFO(self, ns, name):
		house = self.factory.house
		entity = house.lookup(ns, name)
		self.sendMsg('INFO', ns, name, *entity.info)

	@phase('normal')
	def LIST(self, name, ns):
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

	@phase('normal')
	def LS(self, ns):
		house = self.factory.house
		names = [ x.name for x in house.members(ns) ]
		self.sendMsg('LS', ns, *names)

	@phase('normal')
	def USERS(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		names = [ x.name for x in room ]
		self.sendMsg('USERS', *names)

	@phase('normal')
	def KICK(self, rname, uname):
		house = self.factory.house
		room = house.lookup('room', rname)
		user = house.lookup('user', uname)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		user.part(rname)
		room.sendMsg('PART', room.name, user.name, 'kick', self.user.name)
		room.remove(user)

	@phase('normal')
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



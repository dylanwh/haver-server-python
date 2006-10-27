import re

from time import time
from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import reactor
from twisted.internet          import task

from haver.server.errors import Fail, Bork
from haver.server.entity import User, Room, Ghost, assert_name
import haver.server

def state(state):
	def code(func):
		func.state = state
		return func
	return code

def is_arity_error(f, e):
	pat = re.compile("^" + f.func_name + '\(\) takes (at least|exactly) (\d+) arguments \((\d+) given\)')
	return pat.match(e.args[0])


def catch_arity(f, args):
	try:
		return f(*args)
	except TypeError, e:
		fix = lambda s: str(int(s) - 1)
		m = is_arity_error(f, e)
		if m:
			raise Fail('arity', m.group(1), fix(m.group(2)), fix(m.group(3)))
		else:
			raise e

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
		self.state     = 'none'


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
				if not hasattr(f, 'state'):
					raise Fail('unknown.command', cmd)
				if f.state != self.state:
					raise Fail('invalid.command', cmd)

				newstate = catch_arity(f, args)
				if newstate is not None:
					self.state = newstate
			else:
				raise Fail('unknown.command', cmd)
			
		except Fail, failure:
			log.msg('Command %s failed with failure %s' % (self.cmd, failure.name))
			if self.state != 'connect':
				self.sendMsg('FAIL', self.cmd, failure.name, *failure.args)
			else:
				self.transport.loseConnection()

		except Bork, bork:
			log.msg('Borking client: %s' % bork.msg)
			if self.state != 'connect':
				self.sendMsg('BORK', bork.msg)
			self.disconnect('bork')


	def sendMsg(self, *msg):
		self.sendLine("\t".join(msg) + "\r")
	
	
	def connectionMade(self):
		self.state = 'connect'
		log.msg('New client from ' + str(self.addr))

	def connectionLost(self, reason):
		log.msg('Lost client from ' + str(self.addr))
		self.quit('closed')

	def quit(self, why, reason = None):
		house = self.factory.house
		
		if self.state == 'normal':
			for name in self.user.rooms:
				room = house.lookup('room', name)
				room.remove(self.user)
				if reason is None:
					room.sendMsg('QUIT', self.user.name, why)
				else:
					room.sendMsg('QUIT', self.user.name, why, reason)

			house.remove(self.user)
			self.state = 'quit'

	def disconnect(self, *args):
		self.sendMsg('BYE', *args)
		self.transport.loseConnection()
		self.quit(*args)

	def checkPing(self):
		"""Called every once and a while. Issues a ping if this client hasn't sent a command recently"""
		now      = time()
		duration = int (now - self.lastCmd)

		if self.state != 'normal':
			self.tardy = None
			return

		if self.tardy is not None:
			self.sendMsg('BYE', 'ping')
			self.disconnect('ping')
			return

		if duration > self.pingTime:
			self.sendMsg('PING', 'foo')
			self.tardy = 'foo'
	

	@state('connect')
	def HAVER(self, version, supports = '', *rest):
		self.version = version
		self.supports = supports.split(',')
		self.sendMsg('HAVER', self.factory.house.name, "%s/%s" % (haver.server.name, haver.server.version))
		return 'login'

	@state('login')
	def IDENT(self, name, *rest):
		house = self.factory.house
		assert_name(name)
		if name[0] == '&' or '@' in name:
			raise Fail('reserved.name', name)

		user = User(name, self)
		house.add(user)
		self.sendMsg('HELLO', name, str(self.addr.host))
		self.user = user
		user['address'] = self.addr.host
		user['version'] = self.version
		if self.factory.ssl:
			user['secure'] = 'yes'
		else:
			user['secure'] = 'no'
		del self.version

		return 'normal'

	@state('login')
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

	@state('normal')
	def TO(self, target, kind, msg, *rest):
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('user', target).sendMsg('FROM', self.user.name, kind, msg, *rest)

	@state('normal')
	def IN(self, name, kind, msg, *rest):
		self.user.updateIdle()
		house = self.factory.house
		house.lookup('room', name).sendMsg('IN', name, self.user.name, kind, msg, *rest)

	@state('normal')
	def JOIN(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		self.user.join(name)
		try:
			room.add(self.user)
		except Fail, f:
			self.user.part(name)
			raise f

		room.sendMsg('JOIN', name, self.user.name)

	@state('normal')
	def PART(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		self.user.part(name)
		room.sendMsg('PART', name, self.user.name)
		room.remove(self.user)

	@state('normal')
	def BYE(self, detail = None):
		self.disconnect('bye', detail)

	@state('normal')
	def PONG(self, nonce):
		if self.tardy is None:
			raise Bork('You smell like SPAM!')
		else:
			self.tardy = None

	@state('normal')
	def POKE(self, nonce):
		self.sendMsg('OUCH', nonce)

	@state('normal')
	def OPEN(self, name):
		house = self.factory.house
		room  = Room(name, owner = self.user.name)
		house.add(room)
		self.sendMsg('OPEN', name)

	@state('normal')
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


	@state('normal')
	def INFO(self, ns, name):
		house = self.factory.house
		entity = house.lookup(ns, name)
		self.sendMsg('INFO', ns, name, *entity.statInfo())

	@state('normal')
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

	@state('normal')
	def LS(self, ns):
		house = self.factory.house
		names = [ x.name for x in house.members(ns) ]
		self.sendMsg('LS', ns, *names)

	@state('normal')
	def USERS(self, name):
		house = self.factory.house
		room = house.lookup('room', name)
		names = [ x.name for x in room ]
		self.sendMsg('USERS', *names)

	@state('normal')
	def KICK(self, rname, uname):
		house = self.factory.house
		room = house.lookup('room', rname)
		user = house.lookup('user', uname)
		if room['owner'] != self.user.name:
			raise Fail('access.owner', room['owner'], self.user.name)

		user.part(rname)
		room.sendMsg('PART', room.name, user.name, 'kick', self.user.name)
		room.remove(user)
	

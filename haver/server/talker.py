import re

from time import time
from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import reactor
from twisted.internet          import task

from haver.server.errors import Fail, Bork
from haver.server.entity import User, Group, Ghost


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

	def __init__(self, lobby):
		self.lobby = lobby

	def buildProtocol(self, addr):
		p = self.protocol(addr)
		p.factory = self
		p.lobby   = self.lobby
		return p
		
class HaverTalker(LineOnlyReceiver):
	def __init__(self, addr):
		self.addr      = addr
		self.cmdpat    = re.compile('^[A-Z][A-Z:_-]+$')
		self.delimiter = "\n"
		self.state     = 'none'


		self.lastCmd   = time()
		self.tardy     = None
		self.pingTime  = 6
		self.pingLoop  = task.LoopingCall(self.checkPing)
		self.pingLoop.start(self.pingTime)

	def parseLine(self, line):
		if len(line) == 0:
			print "Got empty line"
			raise Bork('Your line is empty')

		msg = line.rstrip("\r").split("\t")

		if not self.cmdpat.match(msg[0]):
			print "This is an example of a badly formed command: %s" % name
			raise Bork("You're not the man I married!")

		return (msg[0], msg[1:])


	def lineReceived(self, line):
		try:
			cmd, args = self.parseLine(line)
			self.cmd = cmd
			self.lastCmd = time()

			if hasattr(self, cmd):
				f = getattr(self, cmd)
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
			self.transport.loseConnection()
			self.quit('bork')


	def sendMsg(self, *msg):
		self.sendLine("\t".join(msg))
	
	
	def connectionMade(self):
		self.state = 'connect'
		log.msg('New client from ' + str(self.addr))

	def connectionLost(self, reason):
		log.msg('Lost client from ' + str(self.addr))
		self.quit('closed')

	def quit(self, why, reason = None):
		lobby = self.factory.lobby
		
		if self.state == 'normal':
			for name in self.user.groups:
				group = lobby.lookup('group', name)
				group.remove(self.user)
				if reason is None:
					group.sendMsg('QUIT', self.user.name, why)
				else:
					group.sendMsg('QUIT', self.user.name, why, reason)

			lobby.remove(self.user)
			self.state = 'quit'

	def checkPing(self):
		"""Called every once and a while. Issues a ping if this client hasn't sent a command recently"""
		now      = time()
		duration = int (now - self.lastCmd)
		if self.tardy is not None:
			self.sendMsg('BYE', 'ping')
			self.transport.loseConnection()
			self.quit('ping')
			return

		if duration > self.pingTime:
			self.sendMsg('PING', 'foo')
			self.tardy = 'foo'
	

	@state('connect')
	def HAVER(self, version, supports = '', *rest):
		self.version = version
		self.supports = supports.split(',')
		self.sendMsg('HAVER', self.factory.hostname, self.factory.version)
		return 'login'

	@state('login')
	def IDENT(self, name, *rest):
		lobby = self.factory.lobby
		try:
			ghost = lobby.lookup('ghost', name)
			self.ghost = ghost
			self.sendMsg('AUTH:TYPES', 'AUTH:BASIC')
		except Fail, fail:
			if fail.name != 'unknown.ghost': raise fail
			user = User(name, self)
			lobby.add(user)
			self.sendMsg('HELLO', name, str(self.addr.host))
			self.user = user
			return 'normal'


	@state('normal')
	def TO(self, target, kind, msg, *rest):
		lobby = self.factory.lobby
		lobby.lookup('user', target).sendMsg('FROM', self.user.name, kind, msg, *rest)

	@state('normal')
	def IN(self, name, kind, msg, *rest):
		lobby = self.factory.lobby
		lobby.lookup('group', name).sendMsg('IN', name, self.user.name, kind, msg, *rest)

	@state('normal')
	def JOIN(self, name):
		lobby = self.factory.lobby
		group = lobby.lookup('group', name)
		self.user.join(name)
		group.add(self.user)
		group.sendMsg('JOIN', name, self.user.name)

	@state('normal')
	def PART(self, name):
		lobby = self.factory.lobby
		group = lobby.lookup('group', name)
		self.user.part(name)
		group.sendMsg('PART', name, self.user.name)
		group.remove(self.user)

	@state('normal')
	def BYE(self, detail = None):
		self.sendMsg('BYE', 'bye')
		self.transport.loseConnection()
		self.quit('bye', detail)

	@state('normal')
	def PONG(self, nonce):
		if self.tardy is None:
			raise Bork('You smell like SPAM!')
		else:
			self.tardy = None

	@state('normal')
	def POKE(self, nonce):
		self.sendMsg('OUCH', nonce)
	

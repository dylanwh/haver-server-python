import time
from twisted.python            import log
from twisted.protocols.basic   import LineOnlyReceiver
from twisted.internet.protocol import Factory
from twisted.internet          import task

from haver.server.errors  import Fail, Bork
from haver.server.thing   import User, Room
from haver.server.asserts import *
import haver.server

badchars = re.compile('[\[\[\\\|\`\^#]')
def purify(s):
	return re.sub(badchars, '', s)

def parsemsg(s):
    """Breaks a message from an IRC server into its prefix, command, and arguments.
    """
    prefix = ''
    trailing = []
    assert s
    if s[0] == ':':
        prefix, s = s[1:].split(' ', 1)
    if s.find(' :') != -1:
        s, trailing = s.split(' :', 1)
        args = s.split()
        args.append(trailing)
    else:
        args = s.split()
    command = args.pop(0)
    return prefix, command, args

class IRCFactory(Factory):

	def __init__(self, house, ssl = False):
		self.house    = house
		self.protocol = IRCTalker
		self.ssl = ssl

	def buildProtocol(self, addr):
		p = self.protocol(addr)
		p.factory = self
		p.house   = self.house
		return p
		
class IRCTalker(LineOnlyReceiver):
	def __init__(self, addr):
		self.addr      = addr
		self.delimiter = "\n"

		self.lastCmd   = time.time()
		#self.tardy     = None
		#self.pingTime  = 60
		#self.pingLoop  = task.LoopingCall(self.checkPing)
		#self.pingLoop.start(self.pingTime)

	def lineReceived(self, line):
		log.msg('C: ' + line.rstrip("\r"))
		try:
			prefix, cmd, args = parsemsg(line.rstrip("\r"))
			self.cmd = cmd
			try:
				f = getattr(self, "C_" + cmd)
			except AttributeError:
				log.msg('FIXME: C_' + cmd)
				return
			f(*args)
		except Fail, failure:
			log.msg('Command %s failed with failure %s (%s)' % (self.cmd, failure.name, str(failure.args)))
			self.sendMsg('FAIL', self.cmd, failure.name, *failure.args)
		except Bork, bork:
			log.msg('Borking client: %s' % bork.msg)
			self.sendMsg('BORK', bork.msg)
			self.disconnect('bork')

	def sendMsg(self, cmd, *args):
		log.msg('sendMsg: %s (%s)' % (cmd, ', '.join(args)))
		try:
			f = getattr(self, 'S_' + cmd)
		except AttributeError:
			log.msg('FIXME: S_' + cmd)
			return
		f(*args)

	def sendRaw(self, s):
		log.msg('S: ' + s)
		self.sendLine(s + "\r")


	def connectionMade(self):
		self.phase = 'connect'
		log.msg('New client from ' + str(self.addr))

	def connectionLost(self, reason):
		log.msg('Lost client from ' + str(self.addr))
		self.quit('closed')

	def quit(self, why, reason = None):
		house = self.factory.house
		
		if self.phase == 'normal':
			for name in list(self.user.rooms):
				room = house.lookup('room', name)
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

	def S_FAIL(self, cmd, error, *rest):
		if cmd == 'JOIN' and error == 'unknown.thing' and rest[0] in ['user', 'room']:
			self.sendRaw(":haver 403 %s #%s :No such channel" % (self.user.name, rest[1]))
		elif error == 'unknown.thing':
			self.sendRaw(":haver 401 %s %s :No such entity.  Please choose another" % (self.user.name, rest[1]))
		elif error == 'invalid.name':
			self.sendRaw(":haver 432  %s :Your chosen identifier is invalid (Illegal characters)" % rest[0])
		else:
			log.msg('unknown error: ' + error)

	def S_JOIN(self, rname, uname):
		house = self.factory.house
		self.sendRaw(':%s!%s@haver JOIN :#%s' % (uname, 'user', rname))
		if (uname.lower() == self.user.name.lower()):
			self.sendRaw(":haver 332 %s #%s :Haver" % (uname, rname))
			room = house.lookup('room', rname)
			users = ' '.join(map(lambda x: x.name, list(room.users)))
			msg = ":haver 353 %s = #%s :%s" % (uname, rname, users)
			self.sendRaw(msg)
			self.sendRaw(':haver 366 %s #%s :End of NAMES feed.' % (uname, rname))

	def S_PART(self, rname, uname, *rest):
		self.sendRaw(':%s!user@haver PART #%s' % (uname, rname))

	def irc_init(self):
		house = self.factory.house
		log.msg('irc init')
		name, info = ('', dict())
		try:
			name, info = self.name, self.info
			del self.name
			del self.info
		except AttributeError, e:
			return
		name = house.genname(root = name)
		user = User(name, self)
		self.user = user
		user['address'] = self.addr.host
		user['version'] = 'irc'

		if self.factory.ssl:
			user['secure'] = 'yes'
		else:
			user['secure'] = 'no'
		
		house.add(user)
		self.sendRaw(':haver NOTICE %s :*** You will be known as %s' % (name, name))
		self.sendRaw(':haver 001 %s :Welcome to the strange and perverse world of haver!' % name)

	def C_NICK(self, name, *rest):
		log.msg('got NICK')
		if hasattr(self, 'name') or hasattr(self, 'user'):
			pass
		else:
			house = self.factory.house
			assert_name_unreserved(name)
			self.name = name
			self.irc_init()

	def C_USER(self, user, host, server, real, *rest):
		log.msg('got USER')
		house = self.factory.house
		self.info = dict(
				username   = user,
				hostname   = host,
				servername = server,
				realname   = real,
		)
		self.irc_init()

	def C_PING(self, s, *rest):
		self.sendRaw(':haver PONG haver :' + s)

	def C_JOIN(self, name, *rest):
		house = self.factory.house
		name = name[1:]
		room = house.lookup('room', name)
		room.join(self.user)

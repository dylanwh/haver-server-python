from haver.server.errors import Fail, Bork
import time, re

def val(x):
	try:
		return str(x())
	except TypeError:
		return str(x)

class Thing(object):
	name = property(lambda self: self.__name)
	
	def __init__(self, name):
		self.__name = name
		self.__info = dict()

	def __getitem__(self, key):
		try:
			return val(self.__info[key])
		except KeyError:
			raise Fail('unknown.infokey', self.namespace, self.name, key)

	def __setitem__(self, key, val):
		self.__info[key] = val
		return self.__info[key]

	def __str__(self):
		return "%s:%s" % (self.namespace, self.name)

	def info(self):
		for (x, y) in self.__info.iteritems():
			yield x
			yield val(y)

class User(Thing):
	namespace = 'user'

	def __init__(self, name, talker):
		Thing.__init__(self, name)
		self.rooms     = set()
		self.talker    = talker
		self.idleTime  = time.time()
		self['idle']   = lambda: int (time.time() - self.idleTime)

	def updateIdle(self):
		self.idleTime = time.time()

	def sendMsg(self, *msg):
		if self.talker is not None:
			self.talker.sendMsg(*msg)

class Room(Thing):
	namespace = 'room'

	def __init__(self, name, owner = '&root'):
		Thing.__init__(self, name)
		self.users   = set()
		self['owner']  = owner
		self['secure'] = 'no'

	def sendMsg(self, *msg):
		for user in self.users:
			user.sendMsg(*msg)

	def join(self, user, *args):
		if user in self.users:
			raise Fail('strange.join')
		self.users.add(user)
		user.rooms.add(self)
		self.sendMsg('JOIN', self.name, user.name, *args)

	def part(self, user, *args):
		if user not in self.users:
			raise Fail('strange.part')
		self.sendMsg('PART', self.name, user.name, *args)
		self.users.remove(user)
		user.rooms.remove(self)


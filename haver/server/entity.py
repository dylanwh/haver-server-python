from haver.server.errors import Fail, Bork
import time, re

namepattern = re.compile("^&?[A-Za-z][A-Za-z0-9_.'\@-]+$")

class Entity(object):
	info = property(lambda self: flatten( self.__info.items() ) )
	name = property(lambda self: self.__name)

	def __init__(self, name):
		assert_name(name)
		self.__name = name
		self.__info = dict()

	def __getitem__(self, key):
		try:
			return self.__info[key]
		except KeyError:
			raise Fail('unknown.attribute', self.namespace, self.name, key)

	def __setitem__(self, key, val):
		self.__info[key] = val
		return self.__info[key]

class User(Entity):
	namespace = 'user'

	def __init__(self, name):
		Entity.__init__(self, name)
		self.idleTime  = time.time()
		#self['rooms']  = lambda: ','.join(self.rooms)
		self['idle']   = self.getIdle

	def updateIdle(self):
		self.idleTime = time.time()

	def getIdle(self):
		return int (time.time() - self.idleTime)

class Room(Entity):
	namespace = 'room'

	def __init__(self, name, owner = '&root'):
		Entity.__init__(self, name)
		self['owner']  = owner
		#self['users']  = len(self.users)
		self['secure'] = 'no'

def assert_name(n):
	if not namepattern.match(n):
		raise Fail('invalid.name', n)

def flatten(tuples):
	for (key, value) in tuples:
		yield key
		try:
			yield str(value())
		except TypeError:
			yield str(value)

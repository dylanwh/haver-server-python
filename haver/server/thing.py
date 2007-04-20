from haver.server.errors import Fail, Bork
import time, re

namepattern = re.compile("^&?[A-Za-z][A-Za-z0-9_.'\@-]+$")

def assert_name(n):
	if not namepattern.match(n):
		raise Fail('invalid.name', n)

def assert_ns(n):
	if n not in ['soul', 'user', 'room']:
		raise Fail('unknown.namespace', n)

def val(x):
	try:
		return str(x())
	except TypeError:
		return str(x)

class Thing(object):
	name = property(lambda self: self.__name)
	
	def __init__(self, name):
		assert_name(name)
		self.__name = name
		self.__info = dict()

	def __getitem__(self, key):
		try:
			return val(self.__info[key])
		except KeyError:
			raise Fail('unknown.attribute', self.namespace, self.name, key)

	def __setitem__(self, key, val):
		self.__info[key] = val
		return self.__info[key]

	def info(self):
		for (x, y) in self.__info.iteritems():
			yield x
			yield val(y)

class User(Thing):
	namespace = 'user'

	def __init__(self, name):
		Thing.__init__(self, name)
		self.idleTime  = time.time()
		self['idle']   = lambda: int (time.time() - self.idleTime)

	def updateIdle(self):
		self.idleTime = time.time()

class Room(Thing):
	namespace = 'room'

	def __init__(self, name, owner = '&root'):
		Thing.__init__(self, name)
		self['owner']  = owner
		self['secure'] = 'no'

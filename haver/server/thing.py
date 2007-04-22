from haver.server.errors import Fail, Bork
from haver.server.asserts import assert_cmd, assert_ns, assert_name
import time, re

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

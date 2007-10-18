from haver.server.errors import Fail, Bork
from haver.server.asserts import assert_name, assert_ns

class House(set):
	def __init__(self, host):
		self.host      = host
		self.__things = dict( user = dict(), room = dict () )

	def lookup_namespace(self, ns):
		try:
			return self.__things[ns]
		except KeyError:
			raise Fail('unknown.namespace', ns)
	
	def lookup(self, ns, name):
		things = self.lookup_namespace(ns)
		try:
			return things[ name.lower() ]
		except KeyError:
			raise Fail('unknown.thing', ns, name)
	
	def add(self, thing):
		assert hasattr(thing, 'namespace')
		assert hasattr(thing, 'name')

		ns, name = (thing.namespace, thing.name.lower())
		things = self.lookup_namespace(ns)
		if things.has_key(name):
			raise Fail('existing.thing', ns, thing.name)
		things[name] = thing
		
	def remove(self, thing):
		ns       = thing.namespace
		name     = thing.name
		lname    = name.lower()
		things = self.lookup_namespace(ns)
		try:
			del things[lname]
		except KeyError:
			raise Fail('unknown.thing', ns, name)

	def list(self, ns):
		things = self.lookup_namespace(ns)
		return things.values()

	def genname(self, root = 'random'):
		users = self.lookup_namespace('user')
		name = root
		i    = 1
		while True:
			if name in users:
				name = root + str(i)
				i    = i + 1
			else:
				break
		return name



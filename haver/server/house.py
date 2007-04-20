from haver.server.errors import Fail, Bork
from haver.server.thing import assert_name, assert_ns

class House(set):
	def __init__(self, host):
		self.host      = host
		self.__members = dict()
	
	def lookup(self, ns, name):
		assert_ns(ns)
		assert_name(name)

		try:
			return things[ name.lower() ]
		except KeyError:
			raise Fail('unknown.thing', ns, name)
		
	def add(self, thing):
		ns, name = (thing.namespace, thing.name.lower())
		
		things = self
		if things.has_key(name):
			raise Fail('existing.thing', ns, thing.name)
		things[name] = thing
		
	def remove(self, thing):
		ns       = thing.namespace
		name     = thing.name
		lname    = name.lower()
		things = self.__fetch(ns)
		try:
			del things[lname]
		except KeyError:
			raise Fail('unknown.thing', ns, name)

	def members(self, ns):
		assert_ns(ns)
		return things.values()

from haver.server.errors import Fail, Bork

class House(object):
	def __init__(self, host):
		self.host = host
		self.__entities = dict(user = {}, room = {}, soul = {})
		self.__joined  = set()
	
	def __fetch(self, ns):
		try:
			return self.__members[ns]
		except KeyError:
			raise Fail('invalid.namespace', ns)

	def lookup(self, ns, name):
		assert_name(name)
		ents = self.__fetch(ns)
		try:
			return ents[ name.lower() ]
		except KeyError:
			raise Fail('unknown.entity', ns, name)
		
	def add(self, entity):
		ns, name = (entity.namespace, entity.name.lower())
		
		ents = self.__fetch(ns)
		if ents.has_key(name):
			raise Fail('existing.entity', ns, entity.name)
		ents[name] = entity
		
	def remove(self, ent):
		ns    = ent.namespace
		name  = ent.name
		lname = name.lower()
		ents  = self.__fetch(ns)
		try:
			del ents[lname]
		except KeyError:
			raise Fail('unknown.entity', ns, name)

	def members(self, ns):
		ents = self.__fetch(ns)
		return ents.values()


	def join(self, uname, rname):
		pair = (uname, rname)
		if pair in self.__joined:
			raise Fail('already.joined')
		else:
			self.__joined

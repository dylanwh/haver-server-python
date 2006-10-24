from haver.server.errors import Fail, Bork
import time, re

namepattern = re.compile("^&?[A-Za-z][A-Za-z0-9_.'\@-]+$")

def assert_name(n):
	if not namepattern.match(n):
		raise Fail('invalid.name', n)

def mask_ip(ip):
	parts = ip.split('.')
	assert len(parts) == 4
	parts[3] = '*'
	return '.'.join(parts)

class Entity(object):
	def __init__(self, name):
		self.name = name

	def __str__(self):
		return self.namespace + "/" + self.__name

	def getName(self): return self.__name
	def delName(self): del self.__name
	def setName(self, name):
		assert_name(name)
		self.__name = name

	name = property(getName, setName, delName, "I'm the 'name' property.")

class Ghost(Entity):
	pass

class Avatar(Entity):
	def __init__(self, name, talker):
		Entity.__init__(self, name)
		
		self.talker        = talker

	def sendMsg(self, *msg):
		self.talker.sendMsg(*msg)

class User(Avatar):
	namespace = 'user'

	def __init__(self, *args, **kwargs):
		Avatar.__init__(self, *args, **kwargs)
		self.email        = None
		self.lastActivity = int(time.time())
		self.groups     = set()

	def joinGroup(self, group):
		name = group.name.lower()
		if name in self.groups:
			raise Fail('already.joined', group.name)
		else:
			self.groups.add(name)
			group.add(self)
			
	def partGroup(self, group):
		name = group.name.lower()
		if name in self.groups:
			self.groups.remove(name)
			group.remove('user', self.name)
		else:
			raise Fail('already.parted', group.name)

	def quit(self, lobby):
		groups = []
		for name in list(self.groups):
			group = lobby.lookup('group', name)
			self.partGroup(group)
			groups.append(group)

		return groups
			
	def updateIdle(self):
		self.lastActivity = int(time.time())

	def getIdle(self):
		return int(time.time()) - self.lastActivity
	
	idle  = property(getIdle)
	

class Group(Entity):
	namespace = 'group'

	def __init__(self, name, owner = '&root'):
		Entity.__init__(self, name)
		self.owner = owner
		self.__users = dict()
		self.__members = dict(user = {}, group = {}, ghost = {})
		
	def sendMsg(self, *msg):
		for user in self.members('user'):
			user.sendMsg(*msg)

	def _get_ns(self, ns):
		try:
			return self.__members[ns]
		except KeyError:
			raise Fail('invalid.namespace', ns)

	def lookup(self, ns, name):
		assert_name(name)
		ents = self._get_ns(ns)
		try:
			return ents[ name.lower() ]
		except KeyError:
			raise Fail('unknown.%s' % ns, name)
		
	def add(self, entity):
		ns, name = (entity.namespace, entity.name.lower())
		
		ents = self._get_ns(ns)
		if ents.has_key(name):
			raise Fail('exists.%s' % ns, entity.name)
		ents[name] = entity
		
	def remove(self, ns, name):
		assert_name(name)
		lname = name.lower()
		ents = self._get_ns(ns)
		try:
			del ents[lname]
		except KeyError:
			raise Fail('unknown.%s' % ns, name)

	def members(self, ns):
		ents = self._get_ns(ns)
		return ents.values()

class Lobby(Group):
	namespace = 'lobby'
	def __init__(self):
		Group.__init__(self, '&lobby')

	def lookup(self, ns, name):
		if name == '&lobby':
			return self
		else:
			return Group.lookup(self, ns, name)

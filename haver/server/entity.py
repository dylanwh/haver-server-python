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
		self.info = dict()

	def __str__(self):
		return self.namespace + "/" + self.__name

	def getName(self): return self.__name
	def delName(self): del self.__name
	def setName(self, name):
		assert_name(name)
		self.__name = name

	name = property(getName, setName, delName, "I'm the 'name' property.")

	def statInfo(self):
		for (key, value) in self.info.items():
			yield key
			try:
				yield str(value())
			except TypeError:
				yield str(value)

class Ghost(Entity):
	pass

class Avatar(Entity):
	def __init__(self, name, talker):
		Entity.__init__(self, name)
		self.talker        = talker

		self.updateIdle()
		self.info['idle'] = self.getIdle

	def updateIdle(self):
		self.idleTime = time.time()

	def getIdle(self):
		return int (time.time() - self.idleTime)

	def sendMsg(self, cmd, *args):
		self.talker.sendMsg(cmd, *args)



class User(Avatar):
	namespace = 'user'

	def __init__(self, *args, **kwargs):
		Avatar.__init__(self, *args, **kwargs)
		self.rooms     = set()
		self.info['rooms'] = lambda: ','.join(self.rooms)

	def join(self, name):
		name = name.lower()
		if name in self.rooms:
			raise Fail('already.joined', name)
		else:
			self.rooms.add(name)
			
	def part(self, name):
		name = name.lower()
		if name in self.rooms:
			self.rooms.remove(name)
		else:
			raise Fail('already.parted', name)

class Room(Entity):
	namespace = 'room'

	def __init__(self, name, owner = '&root'):
		Entity.__init__(self, name)
		self.info['owner'] = owner
		self.__users = dict()
		self.__members = dict(user = {}, room = {}, ghost = {})
		
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
		
	def remove(self, ent):
		ns    = ent.namespace
		name  = ent.name
		lname = name.lower()
		ents  = self._get_ns(ns)
		try:
			del ents[lname]
		except KeyError:
			raise Fail('unknown.%s' % ns, name)

	def members(self, ns):
		ents = self._get_ns(ns)
		return ents.values()

class Lobby(Room):
	namespace = 'lobby'
	def __init__(self):
		Room.__init__(self, '&lobby')

	def lookup(self, ns, name):
		if name == '&lobby':
			return self
		else:
			return Room.lookup(self, ns, name)

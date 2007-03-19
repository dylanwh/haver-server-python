from haver.server.errors import Fail, Bork
import time, re

namepattern = re.compile("^&?[A-Za-z][A-Za-z0-9_.'\@-]+$")

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

	def __str__(self):
		return self.namespace + "/" + self.__name

class Avatar(Entity):
	def __init__(self, name, talker):
		Entity.__init__(self, name)
		self.talker        = talker

		self.updateIdle()
		self['idle'] = self.getIdle

	def updateIdle(self):
		self.idleTime = time.time()

	def getIdle(self):
		return int (time.time() - self.idleTime)

	def sendMsg(self, cmd, *args):
		self.talker.sendMsg(cmd, *args)



class User(Avatar):
	namespace = 'user'

	def __init__(self, name, talker):
		Avatar.__init__(self, name, talker)
		self.rooms     = set()
		self.spoonkey = None
		self['rooms'] = lambda: ','.join(self.rooms)

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

	def attach(self, talker, key):
		"""Associate a new talker with the Spooner, send the message log, and clear it."""
		if self.spoonkey != key:
			raise Fail('mismatch.spoonkey', key)
		else:
			msglog, self.msglog = self.msglog, []
			self.talker = talker
			for (t, msg) in msglog:
				talker.sendMsg('SPOON:AT', time.strftime("%Y/%m/%d %H:%M:%S UTC", time.gmtime(t)), *msg)

	def detach(self, key):
		self.talker = None
		self.msglog = []
		self.spoonkey = key

	def is_attached(self):
		return self.talker is not None

	def sendMsg(self, *msg):
		if self.talker is None:
			self.msglog.append((time.time(), msg))
		else:
			self.talker.sendMsg(*msg)


class Room(Entity):
	namespace = 'room'
	users = property(lambda self: self.__users.values())

	def __init__(self, name, owner = '&root'):
		Entity.__init__(self, name)
		self.__users       = dict()
		self['owner'] = owner
		self['users'] = self.users
		self['secure'] = 'no'

	def __iter__(self):
		return iter( self.users )


	def sendMsg(self, *msg):
		for user in self.users:
			user.sendMsg(*msg)
	
	def lookup(self, name):
		assert_name(name)
		try:
			return self.__users[ name.lower() ]
		except KeyError:
			raise Fail('unknown.entity', 'user', name)

	def add(self, user):
		name = user.name.lower()
		if self.__users.has_key(name):
			raise Fail('existing.entity', 'user', user.name)
		self.__users[name] = user

	def remove(self, user):
		try:
			del self.__users[ user.name.lower() ]
		except KeyError:
			raise Fail('unknown.entity', 'user', user.name)


class Lobby(Entity):
	namespace = 'room'
	name      = '&lobby'
	users     = property(lambda self: self.house.members('user'))
	info      = property(lambda self: self.house.info)

	def __init__(self, house):
		self.house = house

	def __iter__(self):
		return iter ( self.users )

	def __getitem__(self, key):
		return self.house[key]

	def __setitem__(self, key, val):
		self.house[key] = val
		return self.house[key]

	def add(self, user):
		raise Fail('forbidden')

	def remove(self, user):
		raise Fail('forbidden')

	def lookup(self, name):
		raise Fail('forbidden')

	def sendMsg(self, *msg):
		raise Fail('forbidden')
	

class Root(User):
	namespace = 'user'

	def __init__(self):
		User.__init__(self, '&root', None)
	
	def sendMsg(self, *msg):
		if msg[0] == 'FROM' and msg[2] == 'say':
			print "%s: %s" % (msg[1], msg[3])

class Echo(User):
	namespace = 'user'

	def __init__(self, house):
		User.__init__(self, '&echo', None)
		self.house = house
	
	def sendMsg(self, *msg):
		if msg[0] == 'FROM':
			user = self.house.lookup('user', msg[1])
			user.sendMsg('FROM', self.name, *msg[2:])

class House(Entity):
	namespace = 'house'

	def __init__(self, name):
		Entity.__init__(self, name)

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
			raise Fail('unknown.entity', ns, name)
		
	def add(self, entity):
		ns, name = (entity.namespace, entity.name.lower())
		
		ents = self._get_ns(ns)
		if ents.has_key(name):
			raise Fail('existing.entity', ns, entity.name)
		ents[name] = entity
		
	def remove(self, ent):
		ns    = ent.namespace
		name  = ent.name
		lname = name.lower()
		ents  = self._get_ns(ns)
		try:
			del ents[lname]
		except KeyError:
			raise Fail('unknown.entity', ns, name)

	def members(self, ns):
		ents = self._get_ns(ns)
		return ents.values()

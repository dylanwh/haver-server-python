import inspect

FAILS = {
	'mismatch.ip': [
		[],
		"Your IP address does not match that one associated with this nick",
	],
	'insecure': [
		['room'],
		"Unable to join secure room from insecure connection",
	],
	'access.owner': [
		['room', 'owner', 'user'],
		"Access denied to room %(room)s, because owner is %(owner)s and you are %(user)s",
	],
	'unknown.command': [
		['cmd'],
		"The server did not understand %(cmd)s",
	],
	'arity': [
		['arity', 'argc'],
		"%(cmd)s has an arity of %(arity)s but was passed %(argc)s arguments.",
	],
	'reserved.name': [
		['name'],
		"The name %(name)s is reserved by the server",
	],
	'already.attached': [
		[],
		"The user is already attached",
	],
	'undocumented.failure': [
		['name'],
		"The failure %(name)s is not documented",
	],
}

class Help(object):
	def __init__(self, talker):
		self.commands   = list()
		self.extensions = set()
		
		self.failures   = set()
		self.talker     = talker

		for name in dir(talker):
			if name[0] == '_': continue
			func = getattr(talker, name)
			if hasattr(func, 'phase'):
				self.commands.append(name)
				if hasattr(func, 'extension'):
					self.extensions.add(func.extension)
				if hasattr(func, 'failures'):
					for x in func.failures:
						self.failures.add(x)


	def fail(self, name, cmd, *args):
		try:
			fail = FAILS[name]
			var = dict()
			if cmd is not None:
				var['cmd'] = name
			else:
				var['cmd'] = '$0'

			if len(args) > 0:
				for i in xrange(len(args)):
					try:
						var[ fail[0][i] ] = args[i]
					except IndexError:
						pass
			else:
				i = 1
				for k in fail[0]:
					var[k] = "$%d" % i
					i = i + 1
			
			return fail[1] % var
		except KeyError:
			return "undocumented failure: %s" % name

	def command(self, name):
		"""Return info about a client command"""
		cmd = getattr(self.talker, name)

		try: exten = cmd.extension
		except AttributeError: exten = 'core'
		
		try: failures = cmd.failures
		except AttributeError: failures = []
		desc = inspect.getdoc(cmd)
		if desc is None: desc = "<none>"
		if len(failures) == 0:
			failures = ['<none>']
		return dict(
			NAME      = cmd.__name__.replace('_', ':'),
			EXTENSION = exten,
			FAILURES  = ",".join(failures),
			DESC      = desc,
			ARGS      = getargs(cmd)
		)

def getargs(cmd):
	result = []
	args, rest, krest, defaults = inspect.getargspec(cmd)
	args     = args[1:]
	if defaults is None:
		defaults = []
		optional = []
	else:
		optional = args[-len(defaults):]
	required = args[0:(len(args) - len(defaults))]
	for arg in required:
		result.append(arg)
	for arg in optional:
		result.append("[%s]" % arg)
	if rest is not None:
		result.append("[%s...]" % rest)
	return "  ".join(result)

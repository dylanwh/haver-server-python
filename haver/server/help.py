import inspect

FAILS = {
	'mismatch.ip': "Your IP address does not match that one associated with this nick",
	'insecure': "Unable to join secure room from insecure connection",
	'access.owner': "Access denied to room $1, because owner is $2 and you are $3",
	'unknown.command': "The server did not understand $1",
	'arity': "$0 has an arity of $1 but was passed $2 arguments.",
	'reserved.name': "The name $1 is reserved by the server",
	'already.attached': "The user is already attached",
	'strange.command': "Command from phase $2 sent while server expecting commands from phase $1",
}

class Help(object):
	def __init__(self, talker):
		self.commands   = list()
		self.extensions = set()
		self.failures   = set(['strange.command'])
		self.replies    = dict()
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
				if hasattr(func, 'replies'):
					for x in func.replies:
						try:
							self.replies[name].append(x)
						except KeyError:
							self.replies[name] = [x]

	def fail(self, name):
		try:
			return FAILS[name]
		except KeyError:
			return "undocumented failure: %s" % name

	def reply(self, name):
		try:
			replies = self.replies[name]
			return [ "  ".join(x) for x in replies ]
		except KeyError:
			return []

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

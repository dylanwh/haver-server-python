import inspect

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

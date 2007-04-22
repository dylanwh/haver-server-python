from haver.server.errors import Fail, Bork
import re, inspect
namepattern = re.compile("^&?[A-Za-z][A-Za-z0-9_.'\@-]+$")
cmdpattern  = re.compile('^[A-Z][A-Z:]*$')

def assert_name(n):
	if not namepattern.match(n):
		raise Fail('invalid.name', n)

def assert_name_unreserved(n):
	if n[0] == '&' or '@' in n:
		raise Fail('reserved.name')

def assert_ns(n):
	if n not in ['soul', 'user', 'room']:
		raise Fail('unknown.namespace', n)

def assert_cmd(cmd):
	if not cmdpattern.match(cmd):
		raise Fail('invalid.command')
	
def assert_arity(f, args):
	arity_max = f.func_code.co_argcount - 1

	if f.func_defaults is None:
		arity_min = arity_max
		arity_text = str(arity_min)
	else:
		arity_min = arity_max - len(f.func_defaults)
		arity_text = "%d-%d" % (arity_min, arity_max)

	catchall = lambda x: inspect.getargspec(x)[2] is None

	if (len(args) > arity_max and catchall(f)) or len(args) < arity_min:
		raise Fail('arity', arity_text, str(len(args)))

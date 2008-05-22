import re


escmap = {
	"\t": "t",
	"\x1b": "e",
	"\n": "n",
	"\0": "z",
}
escpat = re.compile('([\t\x1b\n\0])')

unescmap = {
	"t": "\t",
	"e": "\x1b",
	"n": "\n",
	"z": "\0",
}
unescpat = re.compile('\x1b([tenz])')

def parse(s):
	msg = map(unescape, s.split("\t"))
	return (msg[0], msg[1:])

def deparse(cmd, args):
	msg = [cmd] + list(args)
	return "\t".join(map(escape, msg))

def escape(s):
	return re.sub(escpat, lambda m: escmap[m.group(1)], s)

def unescape(s):
	return re.sub(unescpat, lambda m: unescmap[m.group(1)], s)


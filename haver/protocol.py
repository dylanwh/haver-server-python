import re

escmap = {
	"\r": "r",
	"\x1b": "e",
	"\n": "n",
	"\t": "t",
}
escpat = re.compile('([\x1b\r\n\t])')

unescmap = {
	"r": "\r",
	"e": "\x1b",
	"n": "\n",
	"t": "\t",
}
unescpat = re.compile('\x1b([rent])')

def parse(s):
	return map(unescape, s.split("\t"))

def deparse(msg):
	return "\t".join(map(escape, msg))

def escape(s):
	return re.sub(escpat, lambda m: escmap[m.group(1)], s)

def unescape(s):
	return re.sub(unescpat, lambda m: unescmap[m.group(1)], s)


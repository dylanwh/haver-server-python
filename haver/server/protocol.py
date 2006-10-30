import re

map_escape = {
	"\r": "r",
	"\x1b": "e",
	"\n": "n",
	"\t": "t",
	"\x00": "z"
}

map_unescape = {
	"r": "\r",
	"e": "\x1b",
	"n": "\n",
	"t": "\t",
	"z": "\x00"
}
pat_escape   = re.compile('([\r\x1b\n\t\0])')
pat_unescape = re.compile('\x1b([rentz])')

def escape(s):
	return re.sub(pat_escape, lambda m: "\x1b" + map_escape[m.group(1)], s)

def unescape(s):
	return re.sub(pat_unescape, lambda m: map_unescape[m.group(1)], s)



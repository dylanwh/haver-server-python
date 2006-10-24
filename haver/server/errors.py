
class Fail(Exception):
	def __init__(self, name, *args):
		self.name = name
		self.args = args
		
class Bork(Exception):
	def __init__(self, msg):
		self.msg = msg



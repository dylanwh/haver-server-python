#!/usr/bin/python
import unittest
import protocol

class TestProtocol(unittest.TestCase):
	def testParseCmd(self):
		testString = "er"
		results = protocol.parse(testString)
		self.assertEqual(results,("er",[]))
	def testParseCmdArg(self):
		testString = "er\trt"
		results = protocol.parse(testString)
		self.assertEqual(results,("er",["rt"]))
	def testParseCmdManyArg(self):
		testString = "er\trt\twere"
		results = protocol.parse(testString)
		self.assertEqual(results,("er",["rt","were"]))


if __name__ == '__main__':
    unittest.main()

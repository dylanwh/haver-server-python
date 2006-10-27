#!/usr/bin/python2.4
from haver.server.talker import HaverFactory, HaverTalker
from haver.server.entity import House, Room, Echo, Lobby, Root
from twisted.application import service, internet
from twisted.persisted   import sob
from OpenSSL import SSL

class ServerContextFactory:
	def getContext(self):
		"""Create an SSL context.

		This is a sample implementation that loads a certificate from a file
		called 'server.pem'."""
		ctx = SSL.Context(SSL.SSLv23_METHOD)
		ctx.use_certificate_file('server.pem')
		ctx.use_privatekey_file('server.pem')
		return ctx

application  = service.Application("haverd")
service      = service.IService(application)
#sc = service.IServiceCollection(application)
#proc = service.IProcess(application)
applicationper = sob.IPersistable(application)


house = House('hardison.net')
ents  = [ Lobby(house), Room('main'), Room('lobby'), Echo(house), Root() ]
for e in ents:
	house.add(e)


servers = [
	internet.TCPServer(7575, HaverFactory(house)),
	internet.SSLServer(7474, HaverFactory(house, ssl = True), ServerContextFactory())
]
# Tie the service to the application
for server in servers:
	server.setServiceParent(service)

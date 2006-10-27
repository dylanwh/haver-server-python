#!/usr/bin/python2.4
from haver.server.talker import HaverFactory
from haver.server.entity import House, Room, Echo, Lobby, Root
from haver.server.ssl    import SSLContextFactory

from twisted.application import service, internet
from twisted.persisted   import sob

application  = service.Application("haverd")
service      = service.IService(application)
#sc = service.IServiceCollection(application)
#proc = service.IProcess(application)
applicationper = sob.IPersistable(application)

house = House('odin.hardison.net')
ents  = [ Lobby(house), Room('main'), Room('lobby'), Echo(house), Root() ]
for e in ents:
	house.add(e)

servers = [
	internet.TCPServer(7575, HaverFactory(house)),
	internet.SSLServer(7474, HaverFactory(house, ssl = True), SSLContextFactory())
]
# Tie the service to the application
for server in servers:
	server.setServiceParent(service)

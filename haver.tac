#!/usr/bin/python2.4
from haver.server.talker     import HaverFactory
from haver.server.irctalker import IRCFactory
from haver.server.thing  import Room #, Echo, Lobby, Root
from haver.server.house  import House
from haver.server.ssl    import SSLContextFactory

from twisted.application import service, internet
from twisted.persisted   import sob

application  = service.Application("haverd")
service      = service.IService(application)
#sc = service.IServiceCollection(application)
#proc = service.IProcess(application)
applicationper = sob.IPersistable(application)

house = House('odin.hardison.net')
#ents  = [ Lobby(house), Room('main'), Room('lobby'), Echo(house), Root() ]
ents  = [ Room('main'), Room('lobby') ]
for e in ents:
	house.add(e)


servers = [
	internet.TCPServer(7575, HaverFactory(house)),
	internet.TCPServer(7666, IRCFactory(house)),
	internet.SSLServer(7474, HaverFactory(house, ssl = True), SSLContextFactory())
]
# Tie the service to the application
for server in servers:
	server.setServiceParent(service)

#!/usr/bin/python2.4
from haver.server.talker import HaverFactory, HaverTalker
from haver.server.entity import Lobby, Group
from twisted.application import service, internet
from twisted.persisted   import sob

application  = service.Application("haverd")
service      = service.IService(application)
#sc = service.IServiceCollection(application)
#proc = service.IProcess(application)
applicationper = sob.IPersistable(application)


lobby   = Lobby()
main    = Group('main')
lobby.add(main)
factory = HaverFactory(lobby)
factory.hostname = 'localhost'
factory.version  = 'HaverServer 1.0'
factory.protocol = HaverTalker

# Create the (sole) client
# Normally, the echo protocol lives on port 7, but since that
# is a privileged port, for this example we'll use port 7001

servers = [
	internet.TCPServer(7575, factory)
]

# Tie the service to the application
for server in servers:
	server.setServiceParent(service)

#!/usr/bin/python2.4
from haver.server.talker import HaverFactory, HaverTalker
from haver.server.entity import House, Room, Echo
from twisted.application import service, internet
from twisted.persisted   import sob

application  = service.Application("haverd")
service      = service.IService(application)
#sc = service.IServiceCollection(application)
#proc = service.IProcess(application)
applicationper = sob.IPersistable(application)


house   = House('hardison.net')
main    = Room('main')
lobby    = Room('lobby')
house.add(main)
house.add(lobby)
house.add( Echo(house) )
factory = HaverFactory(house)
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

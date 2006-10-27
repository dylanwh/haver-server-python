from OpenSSL import SSL

class SSLContextFactory:
	def getContext(self):
		"""Create an SSL context.

		This is a sample implementation that loads a certificate from a file
		called 'server.pem'."""
		ctx = SSL.Context(SSL.SSLv23_METHOD)
		ctx.use_certificate_file('server.pem')
		ctx.use_privatekey_file('server.pem')
		return ctx

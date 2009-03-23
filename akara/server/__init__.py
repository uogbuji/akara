#akara.server

import os
import sys
import httplib
import SocketServer
from wsgiref import simple_server


DEFAULT_MODULE_DIRECTORY = '~/.local/lib/akara'

# Default error message
DEFAULT_ERROR_MESSAGE = """\
<head>
  <title>Error response</title>
</head>
<body>
  <h1>Error response</h1>
  <p>Error code %(code)d.
  <p>Message: %(message)s.
  <p>Error code explanation: %(code)s = %(explain)s.
</body>
"""

class wsgi_server(simple_server.WSGIServer, SocketServer.ForkingMixIn):
    pass


class wsgi_handler(simple_server.WSGIRequestHandler):
    pass


class wsgi_application:

    module_directory = DEFAULT_MODULE_DIRECTORY
    verbosity = 0
    services = frozenset()

    def __init__(self, module_directory=DEFAULT_MODULE_DIRECTORY,
                 verbosity=0):
        self.module_directory = module_directory
        self.verbosity = verbosity
        self.services = {}
        self._load_modules()
        return

    def _register_service(self, func, ident, path, **kwds):
        self.services[path] = func
        return func

    def _load_modules(self):
        if not os.path.exists(self.module_directory):
            # Nothing to do
            return
        for pathname in os.listdir(self.module_directory):
            if pathname.endswith('.py'):
                filename = os.path.join(self.module_directory, pathname)
                if os.path.isfile(filename): #and not os.path.islink(filename):
                    # Start with a clean slate each time to prevent
                    # namespace corruption.
                    global_dict = {
                        '__builtins__': __builtins__,
                        '__AKARA_REGISTER_SERVICE__': self._register_service,
                        }
                    execfile(filename, global_dict, {})
        return

    def __call__(self, environ, start_response):
        name = shift_path_info(environ)
        try:
            service = self.services[name]
        except KeyError:
            start_response('404 Not Found', [('content-type', 'text/html')])
            url = util.request_uri(environ)
            params = {
                'code': 404,
                'message': 'Not Found',
                'explain': 'The requested URL %s was not found' % url,
                }
            response = [DEFAULT_ERROR_MESSAGE % params]
        else:
            response = service(environ, start_response)
        return response


def serve_forever(host, port, app):
    print >> sys.stderr, "Starting server on port %d..." % port
    server = wsgi_server((host, port), wsgi_handler)
    server.set_app(app)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print >> sys.stderr, "Ctrl-C caught, exiting..."
    return


# COMMAND-LINE --------------------------------------------------------

def main(argv=None):
    if argv is None:
        argv = sys.argv
    from optparse import OptionParser
    parser = OptionParser(prog=os.path.basename(argv[0]))
    parser.add_option('-X', '--debug', action='store_true', default=False)
    parser.add_option('-v', '--verbose', action='store_true', default=False)
    parser.add_option('-H', '--host', type=str, default='')
    parser.add_option('-P', '--port', type=int, default=8880)
    parser.add_option('-D', '--module-directory',
                      default=DEFAULT_MODULE_DIRECTORY)

    # Parse the command-line
    try:
        options, args = parser.parse_args(argv[1:])
    except SystemExit, e:
        return e.code

    # Process/validate mandatory arguments
    #try:
    #    arg = args[0]
    #except IndexError:
    #    parser.error("Missing required argument")

    application = wsgi_application(options.module_directory,
                                   int(options.verbose))

    if options.debug:
        import akara.resource.web
        pdb.runcall(serve_forever, options.host, options.port, application)
    else:
        serve_forever(options.host, options.port, application)
    return 0


if __name__ == "__main__":
    sys.exit(main())

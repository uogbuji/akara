#akara.server

import os
import sys
import signal
import httplib
import SocketServer
from wsgiref import simple_server
from wsgiref.util import shift_path_info, request_uri

DEFAULT_MODULE_DIRECTORY = os.path.expanduser('~/.local/lib/akara')

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

    debug = True
    restart_pending = False
    shutdown_pending = False

    def set_signals(self):
        if self.debug:
            signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGHUP, self.restart)
        return

    def shutdown(self, *ignored):
        self.shutdown_pending = True

    def restart(self, *ignored):
        self.restart_pending = True

    def run(self):
        # Setup hooks for controlling within the OS
        self.set_signals()

        # Force once through the loop
        self.restart_pending = True

        while self.restart_pending:
            host, port = self.server_address
            if not host: host = '*'
            print >> sys.stderr, "listening on %s:%d" % (host, port)

            self.application.read_config()

            self.restart_pending = self.shutdown_pending = False

            while not self.restart_pending and not self.shutdown_pending:
                self.handle_request()

            if self.shutdown_pending:
                print >> sys.stderr, "shutting down"
                break

            print >> sys.stderr, "graceful restart..."
            continue

        print >> sys.stderr, "exiting"
        return 0


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
        return

    def _log(self, level, message, *args):
        if args:
            message %= args
        if level <= self.verbosity:
            print >> sys.stderr, message

    def _register_service(self, func, ident, path):
        self._log(1, 'registering %s as %s', path, func)
        self.services[path] = func
        return

    def _load_modules(self):
        if not os.path.exists(self.module_directory):
            self._log(1, 'skipping module directory %r', self.module_directory)
            # Nothing to do
            return
        self._log(1, 'loading modules from %r', self.module_directory)
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
                    self._log(1, 'loading %r', filename)
                    execfile(filename, global_dict)
        return

    def read_config(self):
        for service in self.services:
            self._log(1, 'unregistering %s', service)
        self.services = {}
        self._load_modules()

    def __call__(self, environ, start_response):
        name = shift_path_info(environ)
        try:
            service = self.services[name]
        except KeyError:
            start_response('404 Not Found', [('content-type', 'text/html')])
            url = request_uri(environ)
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
    server = wsgi_server((host, port), wsgi_handler)
    server.set_app(app)
    server.run()
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

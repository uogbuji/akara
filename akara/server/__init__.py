#akara.server

import sys
import SocketServer
from wsgiref import simple_server


class wsgi_server(simple_server.WSGIServer, SocketServer.ForkingMixIn):
    pass


class wsgi_handler(simple_server.WSGIRequestHandler):
    pass


def make_server(host, port, app):
    """Create a new WSGI server listening on `host` and `port` for `app`"""
    server = wsgi_server((host, port), wsgi_handler)
    server.set_app(app)
    return server


def serve_forever(host, port, app):
    server = make_server(host, port, app)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print >> sys.stderr, "Ctrl-C caught, exiting..."
    return
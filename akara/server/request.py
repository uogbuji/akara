########################################################################
# akara/server/request.py

import sys
import select
import urllib
from wsgiref.handlers import BaseHandler
from wsgiref.simple_server import WSGIRequestHandler, ServerHandler

class wsgi_handler(ServerHandler):

    wsgi_multithread = False
    wsgi_multiprocess = True

    def __init__(self, request, stdin, stdout, stderr):
        self.request = request
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

    def add_cgi_vars(self):
        env, request = self.environ, self.request
        env.update(request.environ)
        env['SERVER_PROTOCOL'] = request.request_version
        env['REQUEST_METHOD'] = request.command
        if '?' in request.path:
            path, query = request.path.split('?', 1)
        else:
            path, query = request.path, ''

        env['PATH_INFO'] = urllib.unquote(path)
        env['QUERY_STRING'] = query

        host = request.address_string()
        remote_addr, remote_port = request.client_address
        env['REMOTE_HOST'] = host if host != remote_addr else ''
        env['REMOTE_ADDR'] = remote_addr

        headers = request.headers
        content_type = headers.typeheader
        if content_type is None:
            content_type = headers.type
        env['CONTENT_TYPE'] = content_type
        env['CONTENT_LENGTH'] = headers.getheader('content-length') or ''

        for h in headers.headers:
            k, v = h.split(':', 1)
            k = k.replace('-', '_').upper()
            if k not in env:
                k = 'HTTP_' + k
                v = v.strip()
                if k in env:
                    # comma-separate multiple headers
                    env[k] += ',' + v
                else:
                    env[k] = v
        return

    def close(self):
        code, status = self.status.split(' ', 1)
        try:
            self.request.log_request(code, self.bytes_sent)
        finally:
            BaseHandler.close(self)


class wsgi_request(WSGIRequestHandler):

    def __init__(self, connection, client_address, server):
        self.connection = self.request = connection
        self.rfile = rfile = connection.makefile('rb', self.rbufsize)
        self.wfile = wfile = connection.makefile('wb', self.wbufsize)
        self.client_address = client_address
        self.server = server
        self.environ = server.environ

        handler = wsgi_handler(self, rfile, wfile, sys.stderr)
        try:
            # Handle multiple HTTP requests, if necessary
            self.close_connection = aborted = 0
            while not self.close_connection:
                self.close_connection = 1
                self.raw_requestline = rfile.readline()
                if not self.raw_requestline:
                    break
                if not self.parse_request():
                    # An error code has been sent, just exit
                    continue
                try:
                    handler.run(server.application)
                except:
                    aborted = 1
                    raise
        finally:
            # Close the connection, being careful to send out whatever is still
            # in our buffers.  If possible, try to avoid a hard close until the
            # client has ACKed our FIN and/or has stopped sending us data.

            # Send any leftover data to the client, but never try again
            if not wfile.closed:
                try:
                    wfile.flush()
                except:
                    pass

            # Lingering close
            if not aborted:
                try:
                    # Close our half of the connection -- send the client a FIN
                    connection.shutdown(1)

                    # Setup to wait for readable data on the socket...

                    # Wait for readable data or error condition on socket;
                    # slurp up any data that arrives... We exit when we go for
                    # an interval of 2 seconds without getting any more data,
                    # get an error, get an EOF on a read, or the timer expires.
                    while 1:
                        readable = select.select([connection], (), (), 2)[0]
                        if not readable:
                            break
                        if not connection.recv(512):
                            break
                except:
                    pass

            # Close all the descriptors
            try:
                wfile.close()
            except:
                pass

            try:
                rfile.close()
            except:
                pass
        return


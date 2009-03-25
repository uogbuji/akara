########################################################################
# akara/server/request.py

import select
from wsgiref.simple_server import WSGIRequestHandler

class wsgi_request(WSGIRequestHandler):

    def __init__(self, connection, client_address, server):
        self.connection = self.request = connection
        self.rfile = connection.makefile('rb', self.rbufsize)
        self.wfile = connection.makefile('wb', self.wbufsize)
        self.client_address = client_address
        self.server = server
        try:
            self.handle()
        finally:
            # Close the connection, being careful to send out whatever is still
            # in our buffers.  If possible, try to avoid a hard close until the
            # client has ACKed our FIN and/or has stopped sending us data.

            # Send any leftover data to the client, but never try again
            if not self.wfile.closed:
                try:
                    self.wfile.flush()
                except:
                    pass

            # Lingering close
            try:
                # Close our half of the connection -- send the client a FIN
                self.connection.shutdown(1)

                # Setup to wait for readable data on the socket...

                # Wait for readable data or error condition on socket;
                # slurp up any data that arrives... We exit when we go for
                # an interval of 2 seconds without getting and more data,
                # get an error, get an EOF on a read, or the timer expires.
                while 1:
                    readable = select.select([connection], (), (), 2)[0]
                    if not readable:
                        break
                    self.rfile.read(512)
            except:
                pass

            # Close all the descriptors
            try:
                self.wfile.close()
            except:
                pass

            try:
                self.rfile.close()
            except:
                pass
        return

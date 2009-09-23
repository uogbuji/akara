"""Interface to flup and paste.httpserver"""

from cStringIO import StringIO
import functools
from wsgiref.util import shift_path_info
from wsgiref.simple_server import WSGIRequestHandler

from amara import tree, xml_print

from akara import logger
from akara.thirdparty import httpserver
from akara import module_loader as loader
from akara import registry

# Why was this lower case?
class Response(object):
    # Why did the original have __slots__ here?
    #__slots__ = ("body", "content_type", "headers", "status")
    def __init__(self, body="", content_type="", status=None, headers=None):
        self.body = body
        self.content_type = content_type
        self.status = status
        if headers is None:
            headers = []
        self.headers = headers


ERROR_DOCUMENT_TEMPLATE = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<hmtl xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
  <title>%(reason)s</title>
</head>
<body>
  <h1>%(reason)s</h1>
  <p>
  %(message)s
  </p>
  <h2>Error %(status)s</h2>
</body>
</html>
"""


class wsgi_exception(Exception):
    def get_response(self):
        raise NotImplementedError

class wsgi_error(Exception):
    def __init__(self, status):
        self.status = status
        self.reason, self.message = WSGIRequestHandler.responses[status]
        Exception.__init__(self, status, self.reason, self.message)

    def get_response(self):
        body = ERROR_DOCUMENT_TEMPLATE % dict(status=self.status,
                                              reason=self.reason,
                                              message=self.message)
        return Response(body, "text/xml", "%s %s" % (self.status, self.reason))



def _send_response_headers(result, start_response, content_type):
    headers = result.headers[:]
    for k,v in headers:
        # See if the Content-Type is already present
        if k.lower() == "content-type":
            break
    else:
        # What should the default content-type be?
        content_type = result.content_type or content_type or "text/plain"
        headers.append( ("Content-Type", content_type) )

    start_response(result.status, headers)


def _convert_body(body):
    # Simple string
    if isinstance(body, str):
        return [body]

    # Amara XML tree
    if isinstance(body, tree.entity):
        io = StringIO()
        xml_print(body, io, indent=True)
        io.seek(0)
        return io

    # Akara response
    if isinstance(body, Response):
        return _convert_body(result.body)

    # If Unicode, you'll need to specify the encoding!
    if isinstance(body, unicode):
        raise TypeError("Unencoded Unicode response")

    # Probably one of the normal WSGI responses
    return body


#####


# This is the adapter between paste.httpserver and Akara

class ServerConfig(object):
    def __init__(self, settings, config):
        self.server_address = settings["server_address"]
    def wsgi_application(self, environ, start_response):
        name = shift_path_info(environ)
        try:
            try:
                func = registry.get_service(name)
            except KeyError:
                raise wsgi_error(404)
            result = func(environ, start_response)
            # The result should meet the WSGI spec.
            # XXX It's so tempting to do
            return _convert_body(result)
            # here and allow other return types
            #return result

        except wsgi_exception, err:
            # An exception must not set the headers.
            # Do it here then return the response as the body
            response = err.get_response()
            _send_response_headers(response, start_response)
            # XXX Again, should I do this here?
            return _convert_body(response.body)



# Store a bit of information needed the respond to the HTTP request.
# This was made a bit more complicated because the compiled extension
# modules aren't actually compiled until the HTTP children are spawned
# off. There's no hook for that (XXX verify that) in flup, so I
# actually defer until the first request is done (XXX fix that so exec
# is done earlier? No. This lets us have clean restarts.)

class AkaraManager(object):
    def __init__(self, settings, conf, modules):
        self.settings = settings
        self.conf = conf
        self.modules = modules
        self._inited_modules = False

    def _init_modules(self):
        # The master node parsed the modules but did not exec them.
        # Do that now, but only once. This will register the functions.
        if not self._inited_modules:
            for code, global_dict in self.modules:
                name = global_dict["__name__"]
                # XXX I don't like this. It means that each spawned
                # listener will re-exec the already parsed code.
                # If there are warnings/errors, they will generated
                # once per process.
                try:
                    exec code in global_dict, global_dict
                except:
                    logger.error("Unable to initialize module %r" % (name,),
                                 exc_info = True)
                    
            self._inited_modules = True

    def __call__(self, sock, addr):
        self._init_modules()
        return AkaraJob(sock, addr, self.settings, self.conf, )


# This is called by ... XXX
class AkaraJob(object):
    def __init__(self, sock, addr, settings, config):
        self._sock = sock
        self._addr = addr
        self.settings = settings  # parsed settings as a dict
        self.config = config      # a ConfigParser
    def run(self):
        print "Starting"
        self._sock.setblocking(1)
        c = ServerConfig(self.settings, self.config)
        self.handler = httpserver.WSGIHandler(self._sock, self._addr, c)
        print "Ending"
        self._sock.close()


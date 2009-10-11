"""Interface to flup and paste.httpserver"""

from cStringIO import StringIO
import functools
from wsgiref.util import shift_path_info
from wsgiref.simple_server import WSGIRequestHandler

from amara import tree, xml_print

from akara import logger
from akara.thirdparty import httpserver, preforkserver
from akara import module_loader as loader
from akara import registry

from akara.thirdparty.preforkserver import PreforkServer

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

class wsgi_error(wsgi_exception):
    def __init__(self, status):
        self.status = status
        self.reason, self.message = WSGIRequestHandler.responses[status]
        Exception.__init__(self, status, self.reason, self.message)

    def get_response(self):
        body = ERROR_DOCUMENT_TEMPLATE % dict(status=self.status,
                                              reason=self.reason,
                                              message=self.message)
        return Response(body, "text/xml", "%s %s" % (self.status, self.reason))


def _convert_body(body):
    # Simple string. Convert to chunked form.
    # (Code inspection suggests that returning a simple string
    # incurs a character-by-character iterator overhead.)
    if isinstance(body, str):
        return [body]

    # Amara XML tree
    if isinstance(body, tree.entity):
        io = StringIO()
        xml_print(body, io, indent=True)
        io.seek(0)
        return io

    # Don't return a Unicode string directly. You need
    # to specify the encoding in the HTTP header, and
    # encode the string correctly.
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
            service = registry.get_service(name)
        except KeyError:
            # Not found. Report something semi-nice to the user
            start_response("404 Not Found", [("Content-Type", "text/xml")])
            reason, message = WSGIRequestHandler.responses[404]
            return ERROR_DOCUMENT_TEMPLATE % dict(status = "404",
                                                  reason = reason,
                                                  message = message)
        handler = service.handler
        # The handler is in charge of doing its own error catching.
        # There is one higher-level handler which will catch errors.
        # If/when that happens it creates a new Akara job handler.
        result = handler(environ, start_response)
        # XXX The result should meet the WSGI spec. ???
        return _convert_body(result)

# Akara byte-compiles the extension modules during server startup as a
# sanity check that they make sense. However, Akara does NOT exec the
# byte code. That is done by each child. Why? It means extension
# modules cannot affect anything in the main process (other than
# knowing that the child is responding or not). 

# I want the modules to be exec'ed once in the child. PreforkServer
# has no defined hook for doing that. The jobClass is init'ed once for
# each request. By inspection I found that 'self._child()' is an
# internal method that I can use to sneak in my exec.


class AkaraPreforkServer(preforkserver.PreforkServer):
    def __init__(self, settings, config, modules,
                 minSpare=1, maxSpare=5, maxChildren=50,
                 maxRequests=0, ):
        preforkserver.PreforkServer.__init__(self,
                                             minSpare=minSpare, maxSpare=maxSpare,
                                             maxChildren=maxChildren, maxRequests=maxRequests,
                                             jobClass=AkaraJob,
                                             jobArgs=(settings, config))
        self.modules = modules

    def _child(self, sock, parent):
        _init_modules(self.modules)
        preforkserver.PreforkServer._child(self, sock, parent)

def _init_modules(modules):
    # The master node parsed the modules but did not exec them.
    # Do that now, but only once. This will register the functions.
    for code, module_globals in modules:
        name = module_globals["__name__"]
        # NOTE: each child execs this code, so any warning and
        # errors will be repeated for each newly spawned process,
        # including child restarts.
        try:
            exec code in module_globals, module_globals
        except:
            logger.error("Unable to initialize module %r" % (name,),
                         exc_info = True)

# Override a few of the default settings
class AkaraWSGIHandler(httpserver.WSGIHandler):
    sys_version = None  # Disable including the Python version number
    server_version = "Akara/2.0"  # Declare that we are an Akara server
    protocol_version = "HTTP/1.1" # Support (for the most part) HTTP/1.1 semantics

# This is called by the flup PreforkServer
class AkaraJob(object):
    def __init__(self, sock, addr, settings, config):
        self._sock = sock
        self._addr = addr
        self.settings = settings  # parsed settings as a dict
        self.config = config      # a ConfigParser
    def run(self):
        self._sock.setblocking(1)
        logger.debug("Start request from address %r, local socket %r" %
                     (self._addr, self._sock.getsockname()))
        c = ServerConfig(self.settings, self.config)
        self.handler = AkaraWSGIHandler(self._sock, self._addr, c)
        logger.debug("End request from address %r, local socket %r" %
                     (self._addr, self._sock.getsockname()))
        self._sock.close()


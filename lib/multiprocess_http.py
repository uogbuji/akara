"""Interface to flup and paste.httpserver

This module ties together the multi-process socket listening
capabilities of flup (see akara.thirdparty.preforkserver) with the
HTTP-to-WSGI capabilities of paste (see akara.thirdparty.httpserver).

Flup implements the Apache multi-processing module algorithm, which is
a non-threaded, pre-forking web server. The master process starts up
and kicks off a number of subprocesses, each listening to the same
socket. One of the subprocesses handles an incoming HTTP connection.

The master node keeps track of the status of each of these
subprocesses. If the load is too high it starts additional
subprocesses, up to a max. If the load is too low, it lowers the
number of processes down to a min. See the flup code for details.

When an HTTP request comes in, the flup-based AkaraPreforkServer in
the subprocess passes that off to and AkaraJob to handle the HTTP
connection. AkaraJob is a small adapter to ask paste to handle the
HTTP request. Paste knows how to convert the request into a WSGI
request, and then call AkaraWSGIDispatcher.wsgi_application.

AkaraWSGIDispatcher uses the registry to look up a WSGI handler for
the requested mount-point (the /first/word/in/the/path) and call it,
or report an error.

"""

from wsgiref.util import shift_path_info
from wsgiref.simple_server import WSGIRequestHandler

# for xml_print
from cStringIO import StringIO
from amara import tree, xml_print

from akara import logger
from akara import registry
from akara import module_loader

from akara.thirdparty import preforkserver, httpserver


# AkaraPreforkServer creates and manages the subprocesses which are
# listening for HTTP requests. When a new connection request comes in
# it instanciates jobClass(sock, addr, *jobArgs) to process the
# connection.

# There is a minor complication here because the master node (which
# manages the subprocesses which are listening for HTTP requests) is
# the one which byte-compiles the extension modules during server
# start-up, as a sanity check that they make sense. The master process
# does not exec the extension modules. That is done in the child.

# Why wait? For one, it makes it hard for the extension modules to
# affect the master node. Core dumps from C extensions can't crash an
# Akara instance, slow memory leaks won't be a problem since flup
# automatically respawns a node after a number of requests, and so on.
# It's even possible to upgrade the extension modules and the modules
# it depends on then send a SIGHUP to the master to restart
# everything.

# The difficulty is that PreforkServer has no defined hook I can grab
# as a signal to exec the extension module bytecode. The jobClass is
# init'ed once for each request. I tried using a global variable to do
# the exec only when the first request comes in, but that slows down
# the first request (once for each number of spawned
# subprocesses).

# Instead, by inspection I found that self._child() is an internal
# method that I can use to sneak in my exec before letting flup's
# child mainloop run.

class AkaraPreforkServer(preforkserver.PreforkServer):
    def __init__(self, settings, config, modules,
                 minSpare=1, maxSpare=5, maxChildren=50,
                 maxRequests=0):
        preforkserver.PreforkServer.__init__(self,
                                             minSpare=minSpare, maxSpare=maxSpare,
                                             maxChildren=maxChildren, maxRequests=maxRequests,
                                             jobClass=AkaraJob,
                                             jobArgs=(settings, config))
        self.modules = modules

    def _child(self, sock, parent):
        module_loader._init_modules(self.modules)
        preforkserver.PreforkServer._child(self, sock, parent)


# Once the flup PreforkServer has a request, it starts up an AkaraJob.
# I'll let paste's WSGIHandler do the work of converting the HTTP
# request to a WSGI request. I actually use my own AkaraWSGIHandler
# because I want to change a few settings.

# AkaraWSGIHandler's third parameter, which is an 

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
        handler = AkaraWSGIDispatcher(self.settings, self.config)
        self.handler = AkaraWSGIHandler(self._sock, self._addr, handler)
        logger.debug("End request from address %r, local socket %r" %
                     (self._addr, self._sock.getsockname()))
        self._sock.close()


# Override a few of the default settings
class AkaraWSGIHandler(httpserver.WSGIHandler):
    sys_version = None  # Disable including the Python version number
    server_version = "Akara/2.0"  # Declare that we are an Akara server
    protocol_version = "HTTP/1.1" # Support (for the most part) HTTP/1.1 semantics


# This is the the top-level WSGI dispatcher between paste.httpserver
# and Akara proper. It only understand how to get the first part of
# the path (called the "mount_point") and get the associated handler
# from the registry.

class AkaraWSGIDispatcher(object):
    def __init__(self, settings, config):
        self.server_address = settings["server_address"]

    def wsgi_application(self, environ, start_response):
        mount_point = shift_path_info(environ)

        try:
            service = registry.get_service(mount_point)
        except KeyError:
            # Not found. Report something semi-nice to the user
            start_response("404 Not Found", [("Content-Type", "text/xml")])
            reason, message = WSGIRequestHandler.responses[404]
            return ERROR_DOCUMENT_TEMPLATE % dict(status = "404",
                                                  reason = reason,
                                                  message = message)
        # The handler is in charge of doing its own error catching.
        # There is one higher-level handler which will catch errors.
        # If/when that happens it creates a new Akara job handler.
        return service.handler(environ, start_response)

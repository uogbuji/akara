"""Interface to flup and paste.httpserver

This module ties together the multi-process socket listening
capabilities of flup (see akara.thirdparty.preforkserver) with the
HTTP-to-WSGI capabilities of paste (see akara.thirdparty.httpserver).
It also handles the Akara extension modules.

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

This module also contains code to read a set of Akara extension
modules. Each module is read and byte-compiled with an environment
which includes the special module variable "AKARA" which contains
configuration information for the module. The byte-code is exec'ed in
each HTTP listener subprocesses, which is also when module resource
registration occurs.

"""
import datetime
import os
import string
import sys
import time
import traceback
import urllib
from cStringIO import StringIO
import logging

from wsgiref.util import shift_path_info
from wsgiref.simple_server import WSGIRequestHandler

from akara import logger
from akara import registry

from akara.thirdparty import preforkserver, httpserver

access_logger = logging.getLogger("akara.access")

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
        _init_modules(self.modules)
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

    # Suppress access log reporting from BaseHTTPServer.py
    def log_request(self, code='-', size='-'):
        pass

# This is the the top-level WSGI dispatcher between paste.httpserver
# and Akara proper. It only understand how to get the first part of
# the path (called the "mount_point") and get the associated handler
# from the registry.

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
  <h2>Error %(code)s</h2>
</body>
</html>
"""

def _send_error(start_response, code, exc_info=None):
    reason, message = WSGIRequestHandler.responses[code]
    start_response("%d %s" % (code, reason), [("Content-Type", "application/xml")],
                   exc_info=exc_info)
    return ERROR_DOCUMENT_TEMPLATE % dict(code = code,
                                          reason = reason,
                                          message = message)

# Output will look like Apache's "combined log format".
#    Here's an example based on the Apache documentation (it should be on a single line)
# 127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0"
# 200 2326 "http://www.example.com/start.html" "Mozilla/4.08 [en] (Win98; I ;Nav)"

# This definition comes from paste.translogger. For certainty's sake:
# (c) 2005 Ian Bicking and contributors; written for Paste (http://pythonpaste.org)
# Licensed under the MIT license: http://www.opensource.org/licenses/mit-license.php
ACCESS_LOG_MESSAGE = (
    '%(REMOTE_ADDR)s - %(REMOTE_USER)s [%(start_time)s] '
    '"%(REQUEST_METHOD)s %(REQUEST_URI)s %(HTTP_VERSION)s" '
    '%(status)s %(bytes)s "%(HTTP_REFERER)s" "%(HTTP_USER_AGENT)s"')

# This proved a lot more difficult than I thought it would be.
# I looked at the translogger solution, but I don't think it works
# across the change of timezones and I didn't want to use the '%b'
# time formatter because it is locale dependant.

def timetuple_to_datetime(t):
    return datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)

_months = "XXX Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
def _get_time():
    now = time.localtime()
    utc_time = time.gmtime()

    tz_seconds = (timetuple_to_datetime(now) - timetuple_to_datetime(utc_time)).seconds
    # Round to the nearest minute
    tz_minutes = (tz_seconds + 30)//60
    tz_hour, tz_minute = divmod(tz_minutes, 60)

    # I've got the timezone component. The rest is easy
    return "%02d/%s/%d:%02d:%02d:%02d %+03d%02d" % (
        now.tm_year, _months[now.tm_mon], now.tm_mday,
        now.tm_hour, now.tm_min, now.tm_sec,
        tz_hour, tz_minute)

# Filter out empty fields, control characters, and space characters
_illegal = ("".join(chr(i) for i in range(33)) +   # control characters up to space (=ASCII 32)
            "".join(chr(i) for i in range(127, 256)) ) # high ASCII
_clean_table = string.maketrans(_illegal, "?" * len(_illegal))
def _clean(s):
    # Check for empty fields
    if not s:
        return "-"
    # Filter control characters. These can be used for
    # escape character attacks against the terminal.
    # Plus, spaces can mess up access log parsers.
    return s.translate(_clean_table)
    

class AkaraWSGIDispatcher(object):
    def __init__(self, settings, config):
        self.server_address = settings["server_address"]

    def wsgi_application(self, environ, start_response):
        # Get information used for access logging
        request_uri = urllib.quote(environ.get("SCRIPT_NAME", "") +
                                   environ.get("PATH_INFO", ""))
        if environ.get("QUERY_STRING"):
            request_uri += "?" + environ["QUERY_STRING"]

        access_data = dict(start_time = _get_time(),
                           request_uri = request_uri,
                           # Will get the following two from start_response_
                           status=None, content_length="-")

        # Set up some middleware so I can capture the status and header
        # information used for access logging.
        def start_response_(status, headers, exc_info=None):
            access_data["status"] = status.split(" ", 1)[0]
            access_data["content_length"] = "-"
            content_length = None
            for k, v in headers:
                if k.lower() == "content-length":
                    access_data["content_length"] = v
            # Forward things to the real start_response
            return start_response(status, headers, exc_info)

        # Get the handler for this mount point
        mount_point = shift_path_info(environ)
        try:
            service = registry.get_service(mount_point)
        except KeyError:
            # Not found. Report something semi-nice to the user
            return _send_error(start_response, 404)

        # Call the handler, deal with any errors, do access logging
        try:
            try:
                return service.handler(environ, start_response_)
            except Exception, err:
                exc_info = sys.exc_info()
                try:
                    f = StringIO()
                    traceback.print_exc(file=f)
                    logger.error("Uncaught exception from %r (%r)\n%s" %
                                 (mount_point, service.ident, f.getvalue()))
                    return _send_error(start_response, 500, exc_info=exc_info)
                finally:
                    del exc_info
        finally:
            self.save_to_access_log(environ, access_data)


            
    def save_to_access_log(self, environ, access_data):
        fields = dict(REMOTE_ADDR = _clean(environ.get("REMOTE_ADDR")),
                      REMOTE_USER = _clean(environ.get("REMOTE_USER")),
                      start_time = access_data["start_time"],
                      REQUEST_METHOD = _clean(environ.get("REQUEST_METHOD")),
                      REQUEST_URI = _clean(access_data["request_uri"]),
                      HTTP_VERSION = environ.get("SERVER_PROTOCOL"),
                      status = access_data["status"],
                      bytes = access_data["content_length"],
                      HTTP_REFERER = _clean(environ.get("HTTP_REFERER")),
                      HTTP_USER_AGENT = _clean(environ.get("HTTP_USER_AGENT")),
                      )
        access_logger.debug(ACCESS_LOG_MESSAGE % fields)


###### Support extension modules

# This used to be in its own module but that module was so small and
# almost pointless so I moved it into here. It doesn't feel quite
# right to be part of multiprocess_http, but it's close enough.

# The master HTTP process uses this module to import the modules and
# convert them into byte code with the correct globals(). It does not
# exec the byte code. That's the job for the spawned-off HTTP listener
# classes.


# Instances are used as module global variable so extension modules
# can get configuration information.
class AKARA(object):
    def __init__(self, config, module_name, module_config):
        self.config = config
        self.module_name = module_name
        self.module_config = module_config

def load_modules(module_dir, server_root, config):
    "Read and prepare all extension modules (*.py) from the module directory"
    modules = []
    for filename in os.listdir(module_dir):
        name, ext = os.path.splitext(filename)
        if ext != ".py":
            continue
        full_path = os.path.join(module_dir, filename)
        module_config = {}
        if config.has_section(name):
            module_config.update(config.items(name))

        module_globals = {
            "__name__": name,
            "__file__": full_path,
            "AKARA": AKARA(config, name, module_config)
            }
        f = open(full_path, "rU")
        try:
            try:
                module_code = compile(f.read(), full_path, 'exec')
            except:
                logger.exception(
                    "Unable to byte-compile %r - skipping module" % (full_path,))
        finally:
            f.close()
        modules.append( (name, module_code, module_globals) )
    return modules

def _init_modules(modules):
    # The master node parsed the modules but did not exec them.
    # Do that now, but only once. This will register the functions.
    for name, code, module_globals in modules:
        # NOTE: each child execs this code, so any warning and
        # errors will be repeated for each newly spawned process,
        # including child restarts.
        try:
            exec code in module_globals, module_globals
        except:
            logger.error(
"Unable to initialize module %r - skipping rest of module" % (name,),
                         exc_info = True)
    

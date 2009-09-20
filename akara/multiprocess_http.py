"""Interface to flup and paste.httpserver"""

from cStringIO import StringIO
import functools
from wsgiref.util import shift_path_info
import cgi

from amara import tree, xml_print

from akara.thirdparty import httpserver
from akara import module_loader as loader
from akara import logger

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



####

def simple_service(method, service_id, mount_point=None, content_type=None,
                   **kwds):
    if method in ("get", "post"):
        warnings.warn('Lowercase HTTP methods deprecated',
                      DeprecationWarning, 2)
        method = method.upper()
        raise NotImplementedError, XXX
    elif method not in ("GET", "POST"):
        raise ValueError(
            "simple_service only supports GET and POST methods, not %s" %
            (method,))

    service_content_type = content_type
    service_kwargs = kwds

    def service_wrapper(func):
        # The registry function was inserted into the functions globals.
        #register_service = func.func_globals["__AKARA_REGISTER_SERVICE__"]
        # Uss the one in this module, which is also available from globals

        @functools.wraps(func)
        def wrapper(environ, start_response):
            request_method = environ.get("REQUEST_METHOD")
            if request_method not in ("GET", "POST", "HEAD"):
                http_response = environ["akara.http_response"]  # XXX where is this set?
                raise http_response(httplib.METHOD_NOT_ALLOWED)

            if method == "POST":
                try:
                    request_length = int(environ["CONTENT_LENGTH"])
                except (KeyError, ValueError):
                    http_response = environ["akara.http_response"]
                    raise http_response(httplib.LENGTH_REQUIRED)
                request_bytes = environ["wsgi.input"].read(request_length)
                try:
                    request_content_type = environ["CONTENT_TYPE"]
                except KeyError:
                    request_content_type = "application/unknown"
                args = (request_bytes, request_content_type)
            else:
                args = ()

            # Build up the keyword parameters from the query string
            query_string = environ["QUERY_STRING"]
            if query_string:
                # Is this order correct? 
                kwargs = cgi.parse_qs(query_string)
                kwargs.update(service_kwargs)
            else:
                kwargs = service_kwargs

            # For when you really need access to the environ.
            # XXX I don't like this, btw, because it goes
            # through a global namespace and because it reduces
            # the ability to componentize.
            
            loader._set_environ(environ)
            try:
                result = func(*args, **kwargs)
            finally:
                loader._set_environ(None)

            if isinstance(result, Response):
                _send_response_headers(results, start_response)
                #return _convert_body(result.body)
                return result.body
            else:
                # XXX What should the default content-type be?
                start_response("200 OK", [("Content-Type", service_content_type or "text/plain")])
                #return _convert_body(result)
                return result

        m_point = mount_point  # Get from the outer scope
        if m_point is None:
            m_point = func.__name__
        loader.register_service(wrapper, service_id, m_point) 
        return wrapper
    return service_wrapper

@simple_service("GET", "http://dalkescientific.com/hello", "dalke.hello")
def hello():
    return "Hello!"

@simple_service("GET", "http://dalkescientific.com/sleep", "dalke.sleep")
def sleep():
    import time
    time.sleep(5)
    return str(os.getpid())

@simple_service("GET", "http://dalkescientific.com/name", "dalke.name")
def hello_name(name="Andrew"):
    yield "Hello "
    yield name
    yield "!\n"

#####


# This is the adapter between paste.httpserver and Akara

class ServerConfig(object):
    def __init__(self, settings, config):
        self.server_address = settings["server_address"]
    def wsgi_application(self, environ, start_response):
        name = shift_path_info(environ)
        try:
            try:
                func = loader.get_service(name)
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


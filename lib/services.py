"""akara.services - adapters to simplify using Python functions as WSGI/HTTP handlers


"""
import httplib
import warnings
import functools
import cgi
import inspect

from wsgiref.simple_server import WSGIRequestHandler

from akara import logger
from akara import registry, module_loader, multiprocess_http

# XXX This is backwards-compatible code. Remove it?
class SimpleResponse(object):
    def __init__(self, body, content_type):
        self.body = body
        self.content_type = content_type

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

# XXX The thought here is to have a way for the simple* services to
# signal a specific error. For example:
#  @simple_service("http://example.com/whatever", "whatever")
#  def whatever():
#      raise amara.services.SimpleError(402, "You don't have enough money!")

# XXX Handle "I am a teapot", which is not in WSGIRequestHandler
class SimpleError(Exception):
    def __init__(self, status, body=None, content_type="text/xml"):
        assert isinstance(status, int)
        self.status = status
        self.body = body
        self.content_type = content_type
    def respond(self, environ, start_response):
        reason, message = WSGIRequestHandler.responses.get(status, ("Unknown", "Unknown"))
        start_response("%s %s" % (self.code, reason),
                       [("Content-Type", self.content_type)])
        if self.body is not None:
            return self.body
        message = ERROR_DOCUMENT_TEMPLATE % dict(status=status,
                                                 reason=reason,
                                                 message=message)
        return message




# Backwards compatibility (older modules expect 'response')
# XXX update those modules
response = SimpleResponse

# Pull out any query arguments and set up input from any POST request
def _get_function_args(environ, default_kwargs = {}):
    request_method = environ.get("REQUEST_METHOD")
    if request_method not in ("GET", "POST", "HEAD"):
        http_response = environ["akara.http_response"]  # XXX where is this set?
        raise http_response(httplib.METHOD_NOT_ALLOWED)

    if request_method == "POST":
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
    kwargs = default_kwargs.copy()
    if query_string:
        # Is this order correct? 
        kwargs.update(cgi.parse_qs(query_string))
    return args, kwargs

# XXX Hack to get the moin modules to run without complaints.
# XXX Fix to use the method
def service(*args, **kwargs):
    def do_nothing(func):
        return func
    return do_nothing
method_handler = service

def simple_service(method, service_id, mount_point=None, content_type=None,
                   **kwds):
    if method in ("get", "post"):
        logger.warn('Lowercase HTTP methods deprecated')
        method = method.upper()
        raise NotImplementedError, "don't use that method" # XXX fixme
    elif method not in ("GET", "POST"):
        raise ValueError(
            "simple_service only supports GET and POST methods, not %s" %
            (method,))

    service_content_type = content_type
    service_kwargs = kwds

    def service_wrapper(func):
        # The registry function was inserted into the functions globals.
        #register_service = func.func_globals["__AKARA_REGISTER_SERVICE__"]
        # Use the one in this module, which is also available from globals

        @functools.wraps(func)
        def wrapper(environ, start_response):
            args, kwargs = _get_function_args(environ, service_kwargs)

            # For when you really need access to the environ.
            # XXX I don't like this, btw, because it goes
            # through a global namespace and because it reduces
            # the ability to componentize.
            
            module_loader._set_environ(environ)
            try:
                # XXX make this be a context?
                try:
                    result = func(*args, **kwargs)
                except SimpleError, error:
                    return error.respond(environ, start_response)
            finally:
                module_loader._set_environ(None)

            if isinstance(result, SimpleResponse):
                start_response("200 OK", [("Content-Type", result.content_type)])
                result = result.body
            else:
                # XXX What should the default content-type be?
                # XXX If the handler returns an Amara tree, can I just say it's text/xml?
                start_response("200 OK", [("Content-Type", service_content_type or "text/plain")])
            #return _convert_body(result)  # XXX support this?
            return result

        m_point = mount_point  # Get from the outer scope
        if m_point is None:
            m_point = func.__name__
        registry.register_service(wrapper, service_id, m_point) 
        return wrapper
    return service_wrapper

# XXX idea for the majority of services which deal with XML
# @xml_service("http://example.com/cool_xml", "cool")
# def cool(xml_tree, param1):
#   ...
#   return xml_tree

#def xml_service()


## Use for services which dispatch based in HTTP method type (GET, POST, ...)

# Nomenclature: the service is identified by its service id.
# All handlers for a given service id implement a given protocol.
# Use a method_dispatcher when a service does different things
# based on the HTTP method (GET, POST, ...) and you want a
# different Python function to handle each method.

# # Example of use:
# @method_dispatcher(SERVICE_ID, DEFAULT_MOUNT)
# def something():
#   "docstring for the service"
# 
# @something.simple_method(method="GET", content_type="text/http")
# def something_get(names=[]):
#   return "Hi " + ", ".join(names) + "!\n"
# 
# @something.method("POST")
# def something_post(environ, start_response):
#   start_response("200 OK", [("Content-Type", "image/gif")])
#   return okay_image

class service_method_dispatcher(object):
    "WSGI dispatcher based on request HTTP method"
    def __init__(self):
        self.method_table = {}
    def add_handler(self, method, handler):
        if method in self.method_table:
            logger.warn("Replaced method") # XXX improve
        else:
            logger.info("New method") # XXX improve
        self.method_table[method] = handler
    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        handler = self.method_table.get(method, None)
        if handler is not None:
            return handler(environ, start_response)
        # XXX generate correct HTTP error here
        raise NotImplementedError

def method_dispatcher(service_id, mount_point):
    def method_dispatcher_wrapper(func):
        doc = inspect.getdoc(func)
        dispatcher = service_method_dispatcher()
        registry.register_service(dispatcher, self.service_id, self.mount_point, doc)
        return service_dispatcher_decorator(dispatcher)
    return method_dispatcher_wrapper


class service_dispatcher_decorator(object):
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def method(self, method):
        if method != method.upper():
            raise AssertionError, "Method name must be upper case" # XXX
        def service_dispatch_decorator_method_wrapper(func):
            @functools.wraps(func)
            def method_wrapper(environ, start_response):
                module_loader._set_environ(environ)
                try:
                    result = func(environ, start_response)
                finally:
                    module_loader._set_environ(None)
                return multiprocess_http._convert_body(result)

            self.dispatcher.add_handler(method, method_wrapper)
            return method_wrapper
        return service_dispatch_decorator_method_wrapper

    def simple_method(self, method, content_type=None):
        if method != method.upper():
            raise AssertionError, "Method name must be upper case" # XXX
        if method not in ("GET", "POST"):
            raise ValueError(
                "simple_method only supports GET and POST methods, not %s" %
                (method,))
        
        def service_dispatch_decorator_simple_method_wrapper(func):
            @functools.wraps(func)
            def simple_method_wrapper(environ, start_response):
                args, kwargs = _get_function_args(environ)
                module_loader._set_environ(environ)
                try:
                    result = func(*args, **kwargs)
                finally:
                    module_loader._set_environ(None)
                start_response("200 OK", [("Content-Type", content_type or "text/plain")])
                #return _convert_body(result)
                return result

            self.dispatcher.add_handler(method, simple_method_wrapper)
            return simple_method_wrapper
        return service_dispatch_decorator_simple_method_wrapper

    # XXX Idea
    #def xml_method(self, method="POST", content_type="text/xml"):
    # ...

# Install some built-in services
@simple_service("GET", "http://purl.org/xml3k/akara/services/builtin/registry",
                "", "text/xml")
def list_services(service=None):
    if service is not None:
        service = service[0]  # XXX check for multiple parameters
    return registry.list_services(ident=service) # XXX 'ident' or 'service' ?


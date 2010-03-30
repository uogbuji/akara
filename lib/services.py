"""akara.services - adapters to use Python functions as WSGI handlers

This module is meant to be used by functions in an Akara extension
module.

"""

import httplib
import warnings
import functools
import cgi
import inspect
from cStringIO import StringIO
from xml.sax.saxutils import escape as xml_escape

from BaseHTTPServer import BaseHTTPRequestHandler
http_responses = BaseHTTPRequestHandler.responses
del BaseHTTPRequestHandler

from amara import tree, writers

from akara import logger, registry

__all__ = ("service", "simple_service", "method_dispatcher")

ERROR_DOCUMENT_TEMPLATE = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
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

class _HTTPError(Exception):
    "Internal class."
    # I don't think the API is quite right.
    # Should code be a number or include the reason in a string, like "200 OK"?
    def __init__(self, code, message=None):
        assert isinstance(code, int) # Being a bit paranoid about the API
        self.code = code
        self.reason, self.message = http_responses[code]
        if message is not None:
            self.message = message
        self.text = ERROR_DOCUMENT_TEMPLATE % dict(code=self.code,
                                                   reason=xml_escape(self.reason),
                                                   message=xml_escape(self.message))
        self.headers = [("Content-Type", "text/html")]
    def make_wsgi_response(self, environ, start_response):
        start_response("%s %s" % (self.code, self.reason), self.headers)
        return [self.text]

class _HTTP405(_HTTPError):
    def __init__(self, methods):
        _HTTPError.__init__(self, 405)
        self.headers.append( ("Allow", ", ".join(methods)) )


# Pull out any query arguments and set up input from any POST request
def _get_function_args(environ, allow_repeated_args):
    request_method = environ.get("REQUEST_METHOD")
    if request_method == "POST":
        try:
            request_length = int(environ["CONTENT_LENGTH"])
        except (KeyError, ValueError):
            raise _HTTPError(httplib.LENGTH_REQUIRED)
        if request_length < 0:
            raise _HTTPError(httplib.BAD_REQUEST)
        request_bytes = environ["wsgi.input"].read(request_length)
        request_content_type = environ.get("CONTENT_TYPE", None)
        args = (request_bytes, request_content_type)
    else:
        args = ()

    # Build up the keyword parameters from the query string
    query_string = environ["QUERY_STRING"]
    kwargs = {}
    if query_string:
        qs_dict = cgi.parse_qs(query_string)
        if allow_repeated_args:
            kwargs = qs_dict
        else:
            for k, v in qs_dict.iteritems():
                if len(v) == 1:
                    kwargs[k] = v[0]
                else:
                    raise _HTTPError(400, 
   message="Using the %r query parameter multiple times is not supported" % (k,))
            
    return args, kwargs

######

def new_request(environ):
    "prepare the akara.request and akara.response environment for a new request"
    from akara import request, response
    request.environ = environ
    response.code = "200 OK"
    response.headers = []

def send_headers(start_response, default_content_type, content_length):
    "Send the WSGI headers, using values from akara.request.*"
    from akara import response
    code = response.code
    if isinstance(code, int):
        reason = http_responses[code][0]
        code = "%d %s" % (code, reason)
    has_content_type = False
    has_content_length = False
    for k, v in response.headers:
        k = k.lower()
        if k == "content-type":
            has_content_type = True
        elif k == "content-length":
            has_content_length = True

    if not has_content_type:
        response.headers.append( ("Content-Type", default_content_type) )
    if not has_content_length and content_length is not None:
        response.headers.append( ("Content-Length", content_length) )

    start_response(code, response.headers)


def convert_body(body, content_type, encoding, writer):
    if isinstance(body, str):
        if content_type is None:
            content_type = "text/plain"
        return [body], content_type, len(body)

    if isinstance(body, tree.entity):
        # XXX have Amara tell me the content type (with encoding)
        # This is trac #29
        if content_type is None:
            if "html" in writer.lower():
                content_type = "text/html"
            else:
                content_type = "application/xml"
        w = writers.lookup(writer)
        body = body.xml_encode(w, encoding)
        return [body], content_type, len(body)

    if isinstance(body, unicode):
        body = body.encode(encoding)
        if content_type is None:
            content_type = "text/plain; charset=%s" % (encoding,)
        return [body], content_type, len(body)

    # Probably one of the normal WSGI responses
    if content_type is None:
        content_type = "text/plain"
    return body, content_type, None


# The HTTP spec says a method can be and 1*CHAR, where CHAR is a
# US-ASCII character excepting control characters and "punctuation".
# (like '(){}' and even ' '). We're a bit more strict than that
# because we haven't seen people use words like "get".
def _check_is_valid_method(method):
    min_c = min(method)
    max_c = max(method)
    if min_c < 'A' or max_c > 'Z':
        raise ValueError("HTTP method %r value is not valid. "
                         "It must contain only uppercase ASCII letters" % (method,))

def _no_slashes(path):
    if path is not None and "/" in path:
        # Really these are more like mount points
        raise ValueError("service paths may not contain a '/'")

def ignore_start_response(status, response_headers, exc_info=None):
    pass

def _make_query_template(func):
    argspec = inspect.getargspec(func)
    if not argspec.args:
        return ""
    num_required = len(argspec.args) - len(argspec.defaults or ())
    arg_info = [(arg, i < num_required) for (i, arg) in enumerate(argspec.args)]
    # I present these in alphabetical order to reduce template changes
    # should the parameter list change.
    arg_info.sort()
    terms = []
    for arg, is_optional in arg_info:
        if is_optional:
            fmt = "%s={%s?}"
        else:
            fmt = "%s={%s}"
        terms.append( fmt % (arg, arg) )
    return "?" + "".join(terms)


def _handle_notify(environ, f, service_list):
    for service_id in service_list:
        service = registry.get_a_service_by_id(service_id)
        service_environ = environ.copy()
        service_environ["PATH_INFO"] = service.path
        f.seek(0)
        new_request(service_environ)
        try:
            service.handler(service_environ, ignore_start_response)
        except Exception:
            raise
            # XXX
            pass

FROM_ENVIRON = object()
def _handle_notify_before(environ, body, service_list):
    if not service_list:
        return
    if body is FROM_ENVIRON:
        body = environ["wsgi.input"].read()
    f = StringIO(body)
    environ["wsgi.input"] = f
    _handle_notify(environ, f, service_list)
    f.seek(0)

def _handle_notify_after(environ, result, service_list):
    if not service_list:
        return result
    f = StringIO()
    for block in result:
        f.write(block)
    # XXX ALso need to set the CONTENT_TYPE (and others?)
    environ["CONTENT_LENGTH"] = f.tell()
    environ["wsgi.input"] = f
    _handle_notify(environ, f, service_list)
    f.seek(0)
    return f

###### public decorators

## Guide to help in understanding
# @service(*args) -> returns a service_wrapper
#
# @service(*args)  
# def func(): pass  -> returns a wrapper() which calls func


def service(service_id, path=None,
            encoding="utf-8", writer="xml",
            pipelines = None,
            query_template = None,
            wsgi_wrapper=None,
            notify_before = None,
            notify_after = None):
    _no_slashes(path)
    def service_wrapper(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            _handle_notify_before(environ, FROM_ENVIRON, notify_before)
            # 'service' passes the WSGI request straight through
            # to the handler so there's almost no point in
            # setting up the environment. However, I can conceive
            # of tools which might access 'environ' directly, and
            # I want to be consistent with the simple* interfaces.
            new_request(environ)
            result = func(environ, start_response)

            # You need to make sure you sent the correct content-type!
            result, ctype, length = convert_body(result, None, encoding, writer)
            result = _handle_notify_after(environ, result, notify_after)
            return result

        pth = path
        if pth is None:
            pth = func.__name__

        # If an outer WSGI wrapper was specified, place it around the service wrapper being created
        if wsgi_wrapper:
            wrapper = wsgi_wrapper(wrapper)

        registry.register_service(service_id, pth, wrapper, query_template=query_template)
        return wrapper
    return service_wrapper


## Guide to help in understanding
# @simple_service(*args) -> returns a service_wrapper
#
# @simple_service(*args)  
# def func(): pass  -> returns a wrapper() which calls func

def simple_service(method, service_id, path=None,
                   content_type=None, encoding="utf-8", writer="xml",
                   allow_repeated_args=False,
                   query_template=None,
                   wsgi_wrapper=None,
                   notify_before=None, notify_after=None):
    _no_slashes(path)
    """Add the function as an Akara resource

    These affect how the resource is registered in Akara
      method - the supported HTTP method (either "GET" or "POST")
      service_id - a string which identifies this service; should be a URL
      path - the local URL path to the resource (must not at present
           contain a '/') If None, use the function's name as the path.

    These control how to turn the return value into an HTTP response
      content_type - the response content-type. If not specified, and if
          "Content-Type" is not listed in akara.response.headers then infer
          the content-type based on what the decorated function returns.
          (See akara.services.convert_body for details)
      encoding - Used to convert a returned Unicode string or an Amara tree
          to the bytes used in the HTTP response
      writer - Used to serialize the Amara tree for the HTTP response.
          This must be a name which can be used as an Amara.writer.lookup.

    This affects how to convert the QUERY_STRING into function call parameters
      allow_repeated_args - The query string may have multiple items with the
          same name, as in "?a=x&a=y&a=z&b=w". If True, this is converted into
          a function call parameter like "f(a=['x','y','z'], b=['w'])". If
          False then this is treated as an error. Suppose the query string
          contains no repeated arguments, as in "?a=x&b=w". If
          allow_repeated_args is True then the function is called as
          as "f(a=['x'], b=['w'])" and if False, like "f(a='x', b='w')".
    
    A simple_service decorated function can get request information from
    akara.request and use akara.response to set the HTTP reponse code
    and the HTTP response headers.

    Here is an example of use:

      @simple_service("GET", "http://example.com/get_date")
      def date(format="%Y-%m-%d %H:%M:%S"):
          '''get the current date'''
          import datetime
          return datetime.datetime.now().strftime(format)

    which can be called with URLs like:

      http://localhost:8880/date
      http://localhost:8880/date?format=%25m-%25d-%25Y

    Integration with other WSGI components:

    The @simple_service decorator creates and returns a low-level handler 
    function that conforms to the WSGI calling conventions. However,
    it is not safe to directly use the resulting handler with arbitrary
    third-party WSGI components (e.g., to wrap the Akara handler with
    an WSGI middleware component).   This is because Akara handlers return
    values other than sequences of byte-strings.  For example, they might
    return XML trees, Unicode, or other data types that would not be 
    correctly interpreted by other WSGI components.

    To integrate other WSGI components with Akara, use the wsgi_wrapper
    argument to @simple_service.  For example:

    def wrapper(app):
        # Create an WSGI wrapper around WSGI application app
        ...
        return wrapped_app

    @simple_service("GET", "http://example.com/get_date", wsgi_wrapper=wrapper)
    def date(format):
        ...
    When specified, Akara will do the following:

         - Arrange to have the wsgi_wrapper placed at the outermost layer 
           of Akara's processing.   That is, control will pass into 
           the WSGI wrapper before any Akara-specific processing related
           to the @simple_service handler takes place.

         - Ensure that all output returned back to the WSGI wrapper
           strictly conforms to the WSGI standard (is a sequence of bytes)

    The wrapper function given with wsgi_wrapper should accept a function
    as input and return an WSGI application as output.  This application
    should be a callable that accepts (environ, start_response).

    See implementation notes in the code below.

"""
    _no_slashes(path)
    _check_is_valid_method(method)
    if method not in ("GET", "POST"):
        raise ValueError(
            "simple_service only supports GET and POST methods, not %s" % (method,))

    def service_wrapper(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            try:
                if environ.get("REQUEST_METHOD") != method:
                    if method == "GET":
                        raise _HTTP405(["GET"])
                    else:
                        raise _HTTP405(["POST"])
                args, kwargs = _get_function_args(environ, allow_repeated_args)
            except _HTTPError, err:
                return err.make_wsgi_response(environ, start_response)
            if args:
                body = args[0]
            else:
                body = ""
            _handle_notify_before(environ, body, notify_before)

            new_request(environ)
            result = func(*args, **kwargs)

            result, ctype, clength = convert_body(result, content_type, encoding, writer)
            send_headers(start_response, ctype, clength)
            result = _handle_notify_after(environ, result, notify_after)
            return result

        pth = path
        if pth is None:
            pth = func.__name__

        # Construct the default query template, if needed and possible.
        qt = query_template
        if qt is None and method == "GET" and not allow_repeated_args:
            qt = _make_query_template(func)
        if qt is not None:
            qt = pth + qt

        # If an wsgi_wrapper was given, wrapper the service wrapper with it
        if wsgi_wrapper:
           wrapper = wsgi_wrapper(wrapper)

        registry.register_service(service_id, pth, wrapper, query_template=qt) 
        return wrapper
    return service_wrapper

# XXX idea for the majority of services which deal with XML
# @xml_service("http://example.com/cool_xml", "cool")
# def cool(xml_tree, param1):
#   ...
#   return xml_tree

#def xml_service()


## Use for services which dispatch based on HTTP method type (GET, POST, ...)

# Nomenclature: the service is identified by its service id.
# All handlers for a given service id implement a given protocol.
# Use a method_dispatcher when a service does different things
# based on the HTTP method (GET, POST, ...) and you want a
# different Python function to handle each method.

class service_method_dispatcher(object):
    """WSGI dispatcher based on request HTTP method

    This is an internal class. You should not need to use it.
    """
    def __init__(self, path, wsgi_wrapper=None):
        self.path = path
        self.method_table = {}
        self.wsgi_wrapper = wsgi_wrapper
    def add_handler(self, method, handler):
        if method in self.method_table:
            logger.warn("Replacing %r method handler for %r"  %
                        (method, self.path))
        else:
            logger.info("Created %r method handler for %r" %
                        (method, self.path))
        # If an outer WSGI wrapper was specified, wrap it around the handler method
        if self.wsgi_wrapper:
            handler = self.wsgi_wrapper(handler)

        self.method_table[method] = handler
    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        handler = self.method_table.get(method, None)
        if handler is not None:
            return handler(environ, start_response)
        err = _HTTP405(sorted(self.method_table.keys()))
        return err.make_wsgi_response(environ, start_response)
    
    def head_method(self, environ, start_response):
        handler = self.method_table.get("GET",None)
        if handler is not None:
            handler(environ, start_response)
            return ['']
        err = _HTTP405(sorted(self.method_table.keys()))
        return err.make_wsgi_response(environ, start_response)

## Guide to help in understanding
# @method_dispatcher(*args) -> returns a method_dispatcher_wrapper
#
# @method_dispatcher(*args)
# def func(): pass  -> returns a service_dispatcher_decorator

# service_dispatcher_decorator.method(*args) -> returns 
#    a service_dispatch_decorator_method_wrapper
#
# service_dispatcher_decorator.method(*args)
# def method_func(): pass --> returns a method_wrapper which calls method_func
#
# service_dispatcher_decorator.simple_method(*args)
# def method_func(): pass --> returns a method_wrapper which calls method_func

# This is the top-level decorator
def method_dispatcher(service_id, path=None, wsgi_wrapper=None):
    """Add an Akara resource which dispatches to other functions based on the HTTP method
    
    Used for resources which handle, say, both GET and POST requests.

      service_id - a string which identifies this service; should be a URL
      path - the local URL path to the resource (must not at present
           contain a '/') If None, use the function's name as the path.
      wsgi_wrapper - An outer WSGI component to be wrapped around the methods

    Example of use:

      @method_dispatcher("http://example.com/example_service")
      def something():
          '''docstring used for the service'''

      @something.simple_method(method="GET", content_type="text/plain",
                               allow_repeated_args=True)
      def something_get(names=[]):
          return "Hi " + ", ".join(names) + "!\n"

      @something.method("POST")
      def something_post(environ, start_response):
          start_response("200 OK", [("Content-Type", "image/gif")])
          return image_bytes

    If you have curl installed then you could access the GET option as:
        curl http://localhost:8880/something?name=Andrew&name=Sara+Marie
    and access the POST option as:
        curl --data "" http://localhost:8880/something

    """
    _no_slashes(path)
    def method_dispatcher_wrapper(func):
        # Have to handle a missing docstring here as otherwise
        # the registry will try to get it from the dispatcher.
        doc = inspect.getdoc(func) or ""
        pth = path
        if pth is None:
            pth = func.__name__
        dispatcher = service_method_dispatcher(pth, wsgi_wrapper)
        registry.register_service(service_id, pth, dispatcher, doc)
        return service_dispatcher_decorator(dispatcher)
    return method_dispatcher_wrapper


class service_dispatcher_decorator(object):
    """Helper class used by method_dispatcher to add new handlers to the given resource

    You should not need to create this directly. Instead, use 'method_dispatcher'
    """
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def method(self, method, encoding="utf-8", writer="xml"):
        """Register a function as a resource handler for a given HTTP method

          method - the relevant HTTP method
          encoding - Used to convert a returned Unicode string or an Amara tree
              to the bytes used in the HTTP response
          writer - Used to serialize the Amara tree for the HTTP response.
              This must be a name which can be used as an Amara.writer.lookup.

        The decorated function must take the normal WSGI parameters
        (environ, start_response) and it must call start_response with
        all the needed headers, including Content-Type.  The function
        may return an Akara tree or a Unicode string, in which case it
        it serialized and converted to bytes based in the 'writer' and
        'encoding' options.
        """
        _check_is_valid_method(method)
        def service_dispatch_decorator_method_wrapper(func):
            @functools.wraps(func)
            def method_wrapper(environ, start_response):
                # 'method' passes the WSGI request straight through
                # to the handler so there's almost no point in
                # setting up the environment. However, I can conceive
                # of tools which might access 'environ' directly, and
                # I want to be consistent with the simple* interfaces.
                new_request(environ)
                result = func(environ, start_response)
                
                # You need to make sure you sent the correct content-type!
                result, ctype, clength = convert_body(result, None, encoding, writer)
                return result

            self.dispatcher.add_handler(method, method_wrapper)
            return method_wrapper
        return service_dispatch_decorator_method_wrapper

    def simple_method(self, method, content_type=None,
                      encoding="utf-8", writer="xml", allow_repeated_args=False):
        _check_is_valid_method(method)
        if method not in ("GET", "POST"):
            raise ValueError(
                "simple_method only supports GET and POST methods, not %s" %
                (method,))
        
        def service_dispatch_decorator_simple_method_wrapper(func):
            @functools.wraps(func)
            def simple_method_wrapper(environ, start_response):
                try:
                    args, kwargs = _get_function_args(environ, allow_repeated_args)
                except _HTTPError, err:
                    return err.make_wsgi_response(environ, start_response)
                new_request(environ)
                result = func(*args, **kwargs)

                result, ctype, clength = convert_body(result, content_type, encoding, writer)
                send_headers(start_response, ctype, clength)
                return result

            self.dispatcher.add_handler(method, simple_method_wrapper)
            return simple_method_wrapper
        return service_dispatch_decorator_simple_method_wrapper

    # XXX Idea
    #def xml_method(self, method="POST", content_type="text/xml"):
    # ...

# Install some built-in services
@simple_service("GET", "http://purl.org/xml3k/akara/services/registry", "",
                allow_repeated_args=False)
def list_services(service=None):
    return registry.list_services(ident=service) # XXX 'ident' or 'service' ?


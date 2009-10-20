"""akara.services - adapters to simplify using Python functions as WSGI/HTTP handlers


"""

import httplib
import warnings
import functools
import cgi
import inspect
from xml.sax.saxutils import escape as xml_escape

from BaseHTTPServer import BaseHTTPRequestHandler
http_responses = BaseHTTPRequestHandler.responses
del BaseHTTPRequestHandler

from amara import tree, writers

from akara import logger, registry


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
        self.headers = [("Content-Type", "text/xml")]
    def make_wsgi_response(self, environ, start_response):
        start_response("%s %s" % (self.code, self.reason), self.headers)
        return [self.text]

class _HTTP405(_HTTPError):
    def __init__(self, methods):
        _HTTPError.__init__(self, 405)
        self.headers.append( ("Allow", ", ".join(methods)) )


# Pull out any query arguments and set up input from any POST request
_allowed_simple_methods = ("GET", "POST", "HEAD")
def _get_function_args(environ, default_kwargs, allow_repeated_args):
    request_method = environ.get("REQUEST_METHOD")
    if request_method not in _allowed_simple_methods:
        raise _HTTP405(_allowed_simple_methods)

    if request_method == "POST":
        try:
            request_length = int(environ["CONTENT_LENGTH"])
        except (KeyError, ValueError):
            raise _HTTPError(httplib.LENGTH_REQUIRED)
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
        qs_dict = cgi.parse_qs(query_string)
        if allow_repeated_args:
            kwargs.update(qs_dict)
        else:
            for k, v in qs_dict.iteritems():
                if len(v) != 1:
                    raise _HTTPError(400, 
   message="Using the %r query parameter multiple times is not supported" % (k,))
                else:
                    kwargs[k] = v[0]
            
    return args, kwargs

def new_request(environ):
    from akara import request, response
    request.environ = environ
    response.code = "200 OK"
    response.headers = []

def clear_request():
    from akara import request, response
    request.environ = None
    response.code = None
    response.headers = None

def send_headers(start_response, default_content_type):
    from akara import response
    code = response.code
    if isinstance(code, int):
        reason = http_responses[code][0]
        code = "%d %s" % (code, reason)
    for k, v in response.headers:
        if k.lower() == "content-type":
            break
    else:
        response.headers.append( ("Content-Type", default_content_type) )

    start_response(code, response.headers)


def convert_body(body, content_type, encoding, writer):
    if isinstance(body, str):
        body = [body]
        if content_type is None:
            content_type = "text/plain"
        return body, content_type

    if isinstance(body, tree.entity):
        if "html" in writer.lower():
            w = writers.lookup(writer)
            body = body.xml_encode(w, encoding)
            if content_type is None:
                content_type = "text/html" # XXX include the encoding here?
            return body, content_type

        w = writers.lookup(writer)
        body = body.xml_encode(w, encoding)
        if content_type is None:
            content_type = "text/xml" # XXX include the encoding here?
        return body, content_type

    if isinstance(body, unicode):
        body = body.encode(encoding)
        if content_type is None:
            # XXX Check if this is valid.
            content_type = "text/plain; charset=%s" % (encoding,)
        return body, content_type

    # Probably one of the normal WSGI responses
    if content_type is None:
        content_type = "text/plain"
    return body, content_type


######

def service(service_id, mount_point=None,
            encoding="utf-8", writer="xml"):
    def service_wrapper(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            # 'service' passes the WSGI request straight through
            # to the handler so there's almost no point in
            # setting up the environment. However, I can conceive
            # of tools which might access 'environ' directly, and
            # I want to be consistent with the simple* interfaces.
            new_request(environ)
            try:
                result = func(environ, start_response)
            finally:
                clear_request()

            # You need to make sure you sent the correct content-type!
            result, ctype = convert_body(result, None, encoding, writer)
            return result

        m_point = mount_pount
        if m_point is None:
            m_point = func.__name__
        registry.register_service(wrapper, service_id, m_point)
        return wrapper
    return service_wrapper


def check_is_valid_method(method):
    min_c = min(method)
    max_c = max(method)
    if min_c < 'A' or max_c > 'Z':
        raise ValueError("Method %r may only contain uppercase ASCII letters" % (method,))

def simple_service(method, service_id, mount_point=None,
                   content_type=None, encoding="utf-8", writer="xml",
                   allow_repeated_args=True,
                   **service_kwargs):
    check_is_valid_method(method)
    if method not in ("GET", "POST"):
        raise ValueError(
            "simple_service only supports GET and POST methods, not %s" % (method,))

    def service_wrapper(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            try:
                args, kwargs = _get_function_args(environ, service_kwargs, allow_repeated_args)
            except _HTTPError, err:
                return err.make_wsgi_response(environ, start_response)
            new_request(environ)
            try:
                result = func(*args, **kwargs)
            except:
                clear_request()
                raise

            result, ctype = convert_body(result, content_type, encoding, writer)
            send_headers(start_response, ctype)
            clear_request()
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
        err = _HTTP405(sorted(self.method_table.keys()))
        return err.make_wsgi_response(environ, start_response)

# This is the top-level decorator
def method_dispatcher(service_id, mount_point):
    def method_dispatcher_wrapper(func):
        doc = inspect.getdoc(func)
        dispatcher = service_method_dispatcher()
        registry.register_service(dispatcher, service_id, mount_point, doc)
        return service_dispatcher_decorator(dispatcher)
    return method_dispatcher_wrapper


class service_dispatcher_decorator(object):
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def method(self, method, encoding="utf-8", writer="xml"):
        check_is_valid_method(method)
        def service_dispatch_decorator_method_wrapper(func):
            @functools.wraps(func)
            def method_wrapper(environ, start_response):
                # 'method' passes the WSGI request straight through
                # to the handler so there's almost no point in
                # setting up the environment. However, I can conceive
                # of tools which might access 'environ' directly, and
                # I want to be consistent with the simple* interfaces.
                new_request(environ)
                try:
                    result = func(environ, start_response)
                finally:
                    clear_request()
                
                # You need to make sure you sent the correct content-type!
                result, ctype = convert_body(result, None, encoding, writer)
                return result

            self.dispatcher.add_handler(method, method_wrapper)
            return method_wrapper
        return service_dispatch_decorator_method_wrapper

    def simple_method(self, method, content_type=None,
                      encoding="utf-8", writer="xml", allow_repeated_args=True,
                      **service_kwargs):
        check_is_valid_method(method)
        if method not in ("GET", "POST"):
            raise ValueError(
                "simple_method only supports GET and POST methods, not %s" %
                (method,))
        
        def service_dispatch_decorator_simple_method_wrapper(func):
            @functools.wraps(func)
            def simple_method_wrapper(environ, start_response):
                try:
                    args, kwargs = _get_function_args(environ, service_kwargs, allow_repeated_args)
                except _HTTPError, err:
                    return err.make_wsgi_response(environ, start_response)
                new_request(environ)
                try:
                    result = func(*args, **kwargs)
                except:
                    clear_request()
                    raise
                result, ctype = convert_body(result, content_type, encoding, writer)
                send_headers(start_response, ctype)
                clear_request()
                return result

            self.dispatcher.add_handler(method, simple_method_wrapper)
            return simple_method_wrapper
        return service_dispatch_decorator_simple_method_wrapper

    # XXX Idea
    #def xml_method(self, method="POST", content_type="text/xml"):
    # ...

# Install some built-in services
@simple_service("GET", "http://purl.org/xml3k/akara/services/builtin/registry", "",
                allow_repeated_args=False)
def list_services(service=None):
    if service is not None:
        service = service[0]  # XXX check for multiple parameters
    return registry.list_services(ident=service) # XXX 'ident' or 'service' ?


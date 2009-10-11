#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

import httplib
import warnings
import functools
import cgi

#__all__ = ['simple_service', 'service', 'response', 'rest_dispatch',
#    'method_handler'
#]


from akara import logger
from akara import registry, module_loader

# 
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




# Backwards compatibility
response = SimpleResponse

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
                start_response("200 OK", [("Content-Type", service_content_type or "text/plain")])
            #return _convert_body(result)  # XXX support this?
            return result

        m_point = mount_point  # Get from the outer scope
        if m_point is None:
            m_point = func.__name__
        registry.register_service(wrapper, service_id, m_point) 
        return wrapper
    return service_wrapper

# This is a conversion of the old code. I don't like it though.
# XXX Who is in charge of 'content_type'? Old code didn't support it at all.
# XXX Why is akara.service_id added to the environ? Ahh, because of moin.
#      I posted an alternative to the list, so commenting this out for now.
"""
def service(methods, service_id, mount_point=None, content_type=None):
    if isinstance(methods, basestring):
        methods = (methods,)
    for method in methods:
        if method != method.upper():
            raise TypeError("AKARA HTTP method name for %r must be in uppercase, not %r" %
                            (service_id, method))
    
    def service_wrapper(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            ## This was in the old code
            # environ["akara.service_id"] = service_id
            request_method = environ.get("REQUEST_METHOD")
            if request_method not in methods:
                return error_response("METHOD_NOT_ALLOWED", environ, start_response)
"""
# @dispatcher(SERVICE_ID, DEFAULT_MOUNT)
# def something():
#   "docstring for the service"
# 
# @something.simple_method("GET", "text/plain")
# def something_get(names=[]):
#   return "Hi " + ", ".join(names) + "!\n"
# 
# @something.method("POST")
# def something_post(environ, start_response):
#   start_response("200 OK", [("Content-Type", "image/gif")])
#   return okay_image
"""
class dispatcher(object):
    def __init__(self, service_id, mount_point):
        self.service_id = service_id
        self.mount_point = mount_point
    def __call__(self, func):
        return method_dispatcher(service_id, mount_point, func.__doc__)


class method_dispatcher(object):
    def __init__(self, service_id, mount_point, doc):
        self.service_id = service_id
        self.mount_point = mount_point
        self.doc = doc

    def method(self, method):
        if method != method.upper():
            raise AssertionError, "Method name must be upper case" # XXX
        @functools.wraps(func)
        def method_wrapper(environ, start_response):
            _set_environ(environ)
            try:
                result = func(environ, start_response)
            finally:
                _set_environ(None)
            if isinstance(result, tree):
                raise AssertionError, "not implemented"
            return result
        register(method_wrapper, self.service_id, self.mount_point, self.doc)
        return method_wrapper

    def simple_method(self, method, content_type=None):
        if method != method.upper():
            raise AssertionError, "Method name must be upper case" # XXX
        if method not in ("GET", "POST"):
            raise ValueError(
                "simple_method only supports GET and POST methods, not %s" %
                (method,))
        
        @functools.wraps(func)
        def simple_method_wrapper(environ, start_response):
            args, kwargs = _get_function_args(environ)
            module_loader._set_environ(environ)
            try:
                result = func(*args, **kwargs)
            finally:
                module_loader._set_environ(None)
            start_response("200 OK", [("Content-Type", content_type or "text/plain")])
            return _convert_body(result)

        register_service(simple_method_wrapper, service_id, mount_point, doc)
        return simple_method_wrapper


@dispatcher("spam", "eggs")
def vikings():
    "Sing the Viking song"

@vikings.simple_method("GET", "text/plain")
def vikings_get(word):
    word = words[0]
    yield "%s, %s, %s, %s" % (word, word, word, word)
    yield "%s, %s, %s, %s" % (word, word, word, word)
    yield "%s-itty %s!" % (word, word)

@vikings.method("POST")
def vikings_post(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return "That was interesting."
"""

# Old code         
"""
class service(object):
    '''
    A generic REST wrapper
    '''
    def __init__(self, methods, service_id, mount_point=None, content_type=None):
        if isinstance(methods, basestring):
            methods = (methods,)
        self.methods = methods
        self.service_id = service_id
        self.mount_point = mount_point
        self.content_type = content_type

    def __call__(self, func):
        try:
            register = func.func_globals['__AKARA_REGISTER_SERVICE__']
        except KeyError:
            return func

        @functools.wraps(func)
        def wrapper(environ, start_response, service=self):
            environ['akara.service_id'] = self.service_id
            request_method = environ.get('REQUEST_METHOD')
            if request_method not in self.methods:
                http_response = environ['akara.http_response']
                raise http_response(httplib.METHOD_NOT_ALLOWED)
            response_obj = func(environ, start_response)
            if not isinstance(response_obj, response):
                content_type = service.content_type
                if content_type is None:
                    raise RuntimeError(
                        'service %r must provide content_type' % service)
                response_obj = response(response_obj, content_type, status=httplib.OK)
            if response_obj.headers is None:
                response_obj.headers = [
                    ('Content-Type', content_type),
                    ('Content-Length', str(len(body))),
                    ]
            #FIXME: Breaks if func also calls start_response.  Should we allow that?
            start_response(status_response(response_obj.status), response_obj.headers)
            return [response_obj.body]

        mount_point = self.mount_point
        if mount_point is None:
            mount_point = func.__name__
        register(wrapper, self.service_id, mount_point)
        return wrapper


def status_response(code):
    return '%i %s'%(code, httplib.responses[code])


class response(object):
    __slots__ = ('body', 'content_type', 'headers', 'status')
    #Considered compat with webob.Response, but a bit too much baggage in those waters
    #Also consider forwards-compat support for OrderedDict: http://www.python.org/dev/peps/pep-0372/
    def __init__(self, body='', content_type=None, status=None, headers=None):
        self.body = body
        self.content_type = content_type
        self.headers = headers
        self.status = status


def rest_dispatch(environ, start_response, service_id, search_space):
    #search_space - usually
    request_method = environ.get('REQUEST_METHOD')
    if 'REST_DISPATCH' not in search_space:
        rest_dispatch = {}
        for objname in search_space:
            obj = search_space[objname]
            if hasattr(obj, 'service_id') and obj.service_id == service_id:
                rest_dispatch[obj.service_id, obj.request_method] = obj
        search_space['REST_DISPATCH'] = rest_dispatch
        #import sys; print >> sys.stderr, rest_dispatch
    func = search_space['REST_DISPATCH'][service_id, request_method]
    return func(environ, start_response)


def method_handler(request_method, service_id):
    def deco(func):
        @functools.wraps(func)
        def wrapper(environ, start_response):
            return func(environ, start_response)
        wrapper.request_method = request_method
        wrapper.service_id = service_id
        return wrapper
    return deco
"""
# Install some built-in services
@simple_service("GET", "http://purl.org/xml3k/akara/services/builtin/registry",
                "", "text/xml")
def list_services(service=None):
    if service is not None:
        service = service[0]  # XXX check for multiple parameters
    return registry.list_services(ident=service) # XXX 'ident' or 'service' ?


#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

import httplib
import warnings
import functools
from cgi import parse_qs
from wsgiref.simple_server import WSGIRequestHandler

__all__ = ['simple_service', 'service', 'response', 'rest_dispatch', 'method_handler']

class simple_service(object):
    '''
    A REST wrapper that turns the keyword parameters of a function from GET
    params
    '''
    def __init__(self, method, service_id, mount_point=None, content_type=None,
                 **kwds):
        if method in ('get', 'post'):
            warnings.warn('Lowercase HTTP methods deprecated',
                          DeprecationWarning, 2)
            method = method.upper()
        elif method not in ('GET', 'POST'):
            raise ValueError('Unsupported HTTP method (%s) for this decorator'
                             % (method,))
        self.service_id = service_id
        self.mount_point = mount_point
        self.content_type = content_type
        self.parameters = kwds
        self.use_request_content = method == 'POST'

    def __call__(self, func):
        try:
            register = func.func_globals['__AKARA_REGISTER_SERVICE__']
        except KeyError:
            return func

        @functools.wraps(func)
        def wrapper(environ, start_response, service=self):
            request_method = environ.get('REQUEST_METHOD')
            if request_method not in ('GET', 'POST', 'HEAD'):
                http_response = environ['akara.http_response']
                raise http_response(httplib.METHOD_NOT_ALLOWED)
            if service.use_request_content:
                try:
                    request_length = int(environ['CONTENT_LENGTH'])
                except (KeyError, ValueError):
                    http_response = environ['akara.http_response']
                    raise http_response(httplib.LENGTH_REQUIRED)
                request_bytes = environ['wsgi.input'].read(request_length)
                try:
                    request_type = environ['CONTENT_TYPE']
                except KeyError:
                    request_type = 'application/unknown'
                args = (request_bytes, request_type)
            else:
                args = ()
            # build up the keyword parameters from the query string
            parameters = environ['QUERY_STRING']
            if parameters:
                parameters = parse_qs(parameters)
                parameters.update(service.parameters)
            else:
                parameters = service.parameters
            # run the service
            #import sys; print >> sys.stderr, 10
            func.func_globals['WSGI_ENVIRON'] = environ
            try:
                response_obj = func(*args, **parameters)
            finally:
                del func.func_globals['WSGI_ENVIRON']
            if isinstance(response_obj, response):
                body = response_obj.body
                content_type = response_obj.content_type
            else:
                body = response_obj
                content_type = service.content_type
                if content_type is None:
                    raise RuntimeError(
                        'service %r must provide content_type' % service)
            headers = [
                ('Content-Type', content_type),
                ('Content-Length', str(len(body))),
                ]
            start_response('200 OK', headers)
            return [body]

        mount_point = self.mount_point
        if mount_point is None:
            mount_point = func.__name__
        register(wrapper, self.service_id, mount_point)
        return wrapper


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


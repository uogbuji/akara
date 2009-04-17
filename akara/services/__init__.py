#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

import httplib
import warnings
import functools
from cgi import parse_qs
from wsgiref.simple_server import WSGIRequestHandler

__all__ = ['manager', 'service', 'response']

class manager(object):
    '''
    Analogue of a Web service.  Acts to dispatch service requests and events.

    The default version doesn't do any prioritization of services.  It just
    tries them in the order registered
    '''
    def __init__(self):
        self._services = {} #From URI to Python object

    def register(self, new_service):
        #new_service is a stub for the service
        self._services.append(new_service)
        return

    def __call__(self, uri, orchestration_tag, params):
        #new_service is a stub for the service
        for service in self._services:
            if service.wants(uri, orchestration_tag, params):
                service(self, uri, orchestration_tag, params)
        return


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
            response_obj = func(*args, **parameters)
            if isinstance(response_obj, response):
                content = response_obj.content
                content_type = response_obj.content_type
            else:
                content = response_obj
                content_type = service.content_type
                if content_type is None:
                    raise RuntimeError(
                        'service %r must provide content_type' % service)
            headers = [
                ('Content-Type', content_type),
                ('Content-Length', str(len(content))),
                ]
            start_response('200 OK', headers)
            return [content]

        mount_point = self.mount_point
        if mount_point is None:
            mount_point = func.__name__
        register(wrapper, self.service_id, mount_point)
        return wrapper


class response(object):
    __slots__ = ('content', 'content_type')
    def __init__(self, content, content_type):
        self.content = content
        self.content_type = content_type


#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

import httplib
from cgi import parse_qs
import functools

__all__ = ['manager', 'service', 'response']

def get_status(code):
    response = httplib.responses[code]
    return '%d %s' % (code, response)

class manager(object):
    '''
    Analogue of a Web service.  Acts to dispatch service requests and events.
    
    The default version doesn't do any prioritization of services.  It just tries them in the order registered
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
    A REST wrapper that turns the keyword parameters of a function from GET params 
    '''
    def __init__(self, method, service_id, service_tag=None, content_type=None,
                 **kwds):
        if method not in ('get', 'post'):
            raise ValueError('Unsupported HTTP method for this decorator')
        self.service_id = service_id
        self.expects_body = method == 'get'
        #test if type(test) in (list, tuple) else [test]
        self.service_tag = service_tag
        self.content_type = content_type
        self.params = kwds

    def __call__(self, func):
        try:
            register = func.func_globals['__AKARA_REGISTER_SERVICE__']
        except KeyError:
            return func
        tag = self.service_tag
        if tag is None:
            tag = func.__name__
        @functools.wraps(func)
        def wrapper(environ, start_response, service=self):
            parameters = parse_qs(environ.get('QUERY_STRING', ''))
            #request_method = environ.get('METHOD').lower()
            parameters.update(service.params)
            #print parameters
            if self.expects_body:
                content = func(**parameters)
            else:
                ctype = environ.get('CONTENT_TYPE', 'application/unknown')
                clen = int(environ.get('CONTENT_LENGTH', None))
                if not clen:
                    self.start_response(get_status(httplib.LENGTH_REQUIRED), [('Content-Type','text/plain')])
                    return httplib.LENGTH_REQUIRED #"Content length Required"
                request_content_bytes = environ['wsgi.input'].read(clen)
                response_obj = func(request_content_bytes, ctype, **parameters)
            if isinstance(response_obj, response):
                content = response_obj.content
                content_type = response_obj.content_type
            else:
                content = response_obj
                content_type = service.content_type
                if content_type is None:
                    raise RuntimeError(
                        'service %r must provide content-type' % tag)
            headers = [
                ('Content-Type', content_type),
                ('Content-Length', str(len(content))),
                ]
            start_response(get_status(httplib.OK), headers)
            return [content]
        register(wrapper, self.service_id, tag)
        return wrapper


class response(object):
    __slots__ = ('content', 'content_type')
    def __init__(self, content, content_type):
        self.content = content
        self.content_type = content_type


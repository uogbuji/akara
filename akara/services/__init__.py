#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

__all__ = ['manager']

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


class service(object):
    def __init__(self, service_id, service_tag=None, **kwargs):
        self.service_id = service_id
        #test if type(test) in (list, tuple) else [test]
        self.service_tag = service_tag
        self.kwargs = kwargs

    def __call__(self, func):
        callback = func.func_globals()['__REGISTER_AKARA_SERVICE__']
        func = callback(func, self.service_id, self.service_tag)
        return func
        def rest_wrapper(environ, start_response):
            response_body = func(**kwargs)
            #response = Response()
            #response.content_type = 'application/json'
            #response.body = simplejson.dumps({'items': entries}, indent=4)
            return response(environ, start_response)
        return func


'''
A REST wrapper that turns the keyword parameters of a function from GET params 
'''


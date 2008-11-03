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



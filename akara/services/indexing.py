#akara.services
"""


"""
#self.policy - instance of L{akara.policy.manager}

__all__ = ['simple_xml_indexing']

import amara
from amara.lib.util import *
from amara.namespaces import AKARA_NAMESPACE


class simple_xml_indexing(object):
    '''
    Service to index content
    '''
    URI = AKARA_NAMESPACE + 'services/simple-xml-indexing'
    def __init__(self, patterns):
        self._patterns = patterns
        return

    def wants(self, uri, orchestration_tag, params):
        return uri == self.URI

    def __call__(self, manager, uri, orchestration_tag, params):
        #new_service is a stub for the service
        source = params['source']
        response_params = {}
        doc = amara.parse(source)
        for pname, xpath in self._patterns.iteritems():
            result = doc.xml_select(pattern)
            response_params[pname] = simplify(result)
        manager(service_id, orchestration_tag, response_params)
        return



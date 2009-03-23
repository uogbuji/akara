#akara.services
"""
Akara stock services (the built-ins)

"""
#self.policy - instance of L{akara.policy.manager}

__all__ = ['simple_xml_indexing']

import amara
from amara.lib.util import *
from amara.namespaces import AKARA_NAMESPACE
from amara.xslt import transform as transform_

from akara.restwrap import *
from akara.services import *

#@akara.service_definition(
#    uri=AKARA_NAMESPACE + 'services/transform',
#    inputs={
#        'source': akara.optional_qparam(u'source'),
#        'transform': akara.optional_qparam(u'transform'),
#        'params': akara.unclaimed_qparams(),
#    },
#    ouputs = []
#)
#def transform(source, transforms, params=None, output=None):

@service(AKARA_NAMESPACE + 'services/transform', 'xslt')
def xslt(source=None, transforms=None, params=None):
    result = transform_(source, transforms[0], params=None)
    yield result


def prep_simile(items, schema=None, strict=False):
    remove_list = []
    for item in items:
        #print item
        if not u'id' in item:
            raise ValueError('Missing ID')
        if schema:
            match = schema.get(first_item(item.get(u'type')))
            if strict and match is None:
                remove_list.append(item)
                continue
            schema_for_item = match or {}
            #print schema_for_item
            for key in schema_for_item:
                if key in item:
                    #result = pipeline_stage(schema_for_item[key], item[key]).next()
                    item[key] = pipeline_stage(schema_for_item[key], item[key])
    for item in remove_list:
        items.remove(item)
    return items




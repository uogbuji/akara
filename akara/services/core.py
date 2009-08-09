#akara.services.core
"""
Akara core services (the built-ins)

Akara is a data pipeline framework.  This module includes several of the built-in pipeline components
"""
#self.policy - instance of L{akara.policy.manager}

#__all__ = ['simple_xml_indexing']

import amara
from amara.lib.util import *
from amara.namespaces import AKARA_NAMESPACE
from amara.xslt import transform as transform_

"""
For security, support:

- Validating the size of data in pipeline
- Validating data in pipeline against regex or other patterns
- Specific tests such as for  SQL Injection and XPath injection (worth checking, even if to log potential attack--honeypots FTW)
"""



#
#OBSOLETE stuff
#from akara.restwrap import *
#from akara.services import *

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




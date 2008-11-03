#akara.resource.index
"""


"""
#self.policy - instance of L{akara.policy.manager}

__all__ = ['simple_xpath_index']

import amara
from amara.tree import node
from amara.lib.util import *
from amara.namespaces import AKARA_NAMESPACE

def simple_xpath_index(self, content, patterns):
    results = {}
    doc = content if isinstance(content, node) else amara.parse(source)
    for pname, xpath in patterns.iteritems():
        result = doc.xml_select(pattern)
        results[pname] = simplify(result)
    return results



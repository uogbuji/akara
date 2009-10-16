"Service registry"

import inspect

from amara import tree

from akara import logger


#### Simple registry of services
# This completely ignores the HTTP method (GET, PUT, POST, etc.)
# during dispatch.


class Service(object):
    def __init__(self, handler, path, ident, doc):
        self.handler = handler # most important - the function to call
        self.path = path  # location on the local service
        self.ident = ident  # URN which identifies this uniquely
        self.doc = doc  # description to use when listing the service


class Registry(object):
    def __init__(self):
        self._registered_services = {}
        self.register_service(self.list_services,
                              "http://purl.org/xml3k/akara/services/builtin/registry", "")
    def register_service(self, handler, ident, path, doc=None):
        if doc is None:
            doc = inspect.getdoc(handler) or ""
        if ident in self._registered_services:
            logger.warn("Replacing mount point %r (%r)" % (path, ident))
        else:
            logger.debug("Created new mount point %r (%r)" % (path, ident))
        self._registered_services[path] = Service(handler, path, ident, doc)

    def get_service(self, path):
        return self._registered_services[path]

    def list_services(self, ident = None):
        document = tree.entity()
        services = document.xml_append(tree.element(None, 'services'))
        for path, service in sorted(self._registered_services.iteritems()):
            if ident is not None and service.ident != ident:
                continue
            service_node = services.xml_append(tree.element(None, 'service'))
            service_node.xml_attributes['ident'] = service.ident
            E = service_node.xml_append(tree.element(None, 'path'))
            E.xml_append(tree.text(path))
            E = service_node.xml_append(tree.element(None, 'description'))
            E.xml_append(tree.text(service.doc))
        return document

_current_registry = Registry()

def register_service(function, ident, path, doc=None):
    _current_registry.register_service(function, ident, path, doc)

def get_service(path):
    return _current_registry.get_service(path)

def list_services(ident=None):
    return _current_registry.list_services(ident)


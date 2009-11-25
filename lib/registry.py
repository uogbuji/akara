"""Service registry

Add WSGI handlers to the Akara HTTP dispatch registry.

"""

import inspect

from amara import tree

from akara import logger

__all__ = ("register_service", "get_service")

#### Simple registry of services


# We had some discussion about using the term 'path' or 'mount_point'?
# Right now we don't really have '/' paths so there's no real difference
# Therefore, you register mount_points, which must not have a "/" in them.
# Incoming requests have a path, and the first segment (before the "/")
# is used to find the mount point.

# We're calling it a 'path' for future compatibility.  For more
# complex paths we might want to use Routes or similar system, in
# which case we'll also have pattern matching on the path segments.
# You'll likely register a path pattern, still with the name 'path'.

class Service(object):
    "Internal class to store information about a given service resource"
    def __init__(self, handler, path, ident, doc):
        self.handler = handler # most important - the function to call
        self.path = path  # where to find the service
        self.ident = ident  # URN which identifies this uniquely
        self.doc = doc  # description to use when listing the service

class Registry(object):
    "Internal class to handle resource registration information"
    def __init__(self):
        self._registered_services = {}

    def register_service(self, ident, path, handler, doc=None):
        if "/" in path:
            raise ValueError("Registered path %r may not contain a '/'" % (path,))
        if doc is None:
            doc = inspect.getdoc(handler) or ""
        if ident in self._registered_services:
            logger.warn("Replacing mount point %r (%r)" % (path, ident))
        else:
            logger.debug("Created new mount point %r (%r)" % (path, ident))
        self._registered_services[path] = Service(handler, path, ident, doc)

    def get_service(self, path):
        return self._registered_services[path]

    def list_services(self, ident=None):
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


def register_service(ident, path, function, doc=None):
    _current_registry.register_service(ident, path, function, doc)

def get_service(mount_point):
    return _current_registry.get_service(mount_point)

def list_services(ident=None):
    return _current_registry.list_services(ident)

def get_a_service_by_id(ident):
    for path, service in _current_registry._registered_services.items():
        if service.ident == ident:
            return service
    return None

"""Service registry

Add WSGI handlers to the Akara HTTP dispatch registry.

"""

import inspect

from amara import tree

from akara import logger

# Take care! This is only initalized when the server starts up and
# after it reads the config file. It's used to generate the full
# template name in list_services().
from akara import global_config

from akara import opensearch

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
    def __init__(self, handler, path, ident, doc, query_template):
        self.handler = handler # most important - the function to call
        # XXX is it okay for the path to be None? I think so ...
        self.path = path  # where to find the service
        self.ident = ident  # URN which identifies this uniquely
        self.doc = doc  # description to use when listing the service
        self.query_template = query_template # OpenSearch template fragment
        self._template = None # The OpenSearch Template
        self._internal_template = None # The OpenSearch template used internally

    @property
    def template(self):
        if self._template is False:
            # No template is possible
            return None
        if self._template is not None:
            # Cached version
            return self._template
        # Compute the template
        if self.query_template is None:
            # No template available
            self._template = False
            return None
        template = global_config.server_path + self.query_template
        self._template = opensearch.make_template(template)
        return self._template

    @property
    def internal_template(self):
        if self._internal_template is False:
            # No template is possible
            return None
        if self._internal_template is not None:
            # Cached version
            return self._internal_template
        # Compute the template
        if self.query_template is None:
            # No template available
            self._internal_template = False
            return None
        internal_template = global_config.internal_server_path + self.query_template
        self._internal_template = opensearch.make_template(internal_template)
        return self._internal_template
    

class Registry(object):
    "Internal class to handle resource registration information"
    def __init__(self):
        self._registered_services = {}

    def register_service(self, ident, path, handler, doc=None, query_template=None):
        if "/" in path:
            raise ValueError("Registered path %r may not contain a '/'" % (path,))
        if doc is None:
            doc = inspect.getdoc(handler) or ""
        if ident in self._registered_services:
            logger.warn("Replacing mount point %r (%r)" % (path, ident))
        else:
            logger.debug("Created new mount point %r (%r)" % (path, ident))
        serv = Service(handler, path, ident, doc, query_template)
        self._registered_services[path] = serv

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
            template = service.template
            if template is not None:
                E.xml_attributes["template"] = service.template.template
            E.xml_append(tree.text(path))
            E = service_node.xml_append(tree.element(None, 'description'))
            E.xml_append(tree.text(service.doc))
        return document

_current_registry = Registry()


def register_service(ident, path, function, doc=None, query_template=None):
    _current_registry.register_service(ident, path, function, doc, query_template)

def get_service(mount_point):
    return _current_registry.get_service(mount_point)

def list_services(ident=None):
    return _current_registry.list_services(ident)

def get_a_service_by_id(ident):
    for path, service in _current_registry._registered_services.items():
        if service.ident == ident:
            return service
    return None

def get_service_url(ident, **kwargs):
    service = get_a_service_by_id(ident)
    template = service.template
    if template is None:
        # What's a good default? Just put them as kwargs at the end?
        raise NotImplementedError
    return template.substitute(**kwargs)

def get_internal_service_url(ident, **kwargs):
    service = get_a_service_by_id(ident)
    template = service.internal_template
    if template is None:
        # What's a good default? Just put them as kwargs at the end?
        raise NotImplementedError
    return template.substitute(**kwargs)

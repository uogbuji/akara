"Service registry"

from amara import tree


#### Simple registry of services

class Registry(object):
    def __init__(self):
        self._registered_services = {}
        self.register_service(self.list_services,
                              "http://purl.org/xml3k/akara/services/builtin/registry", "")
    def register_service(self, function, ident, path):
        assert ident is not None, "even though it is not used yet"
        self._registered_services[path] = function

    def get_service(self, path):
        return self._registered_services[path]

    def list_services(self, environ, start_response):
        document = tree.entity()
        services = document.xml_append(tree.element(None, 'services'))
        for path, func in sorted(self._registered_services.iteritems()):
            service = services.xml_append(tree.element(None, 'service'))
            service.xml_attributes['name'] = func.__name__
            E = service.xml_append(tree.element(None, 'path'))
            E.xml_append(tree.text(path))
            E = service.xml_append(tree.element(None, 'description'))
            E.xml_append(tree.text(func.__doc__ or ''))
        # XXX This does not make clear sense to me.
        #last_modified = formatdate(self.last_modified, usegmt=True)
        #expires = formatdate(self.expires, usegmt=True)
        start_response('200 OK', [('Content-Type', 'text/xml'),
        #                          ('Last-Modified', last_modified),
        #                          ('Expires', expires),
                                  ])
        return document

_current_registry = Registry()

def register_service(function, ident, path):
    _current_registry.register_service(function, ident, path)

def get_service(path):
    return _current_registry.get_service(path)


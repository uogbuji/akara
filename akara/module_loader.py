import os

# This variable is used as a way to get the current WSGI environ into
# simple_service and related functions.
#
# XXX Why isn't this "import akara.request" to get the proper values?
#  Similar to what's done with TurboGears?
#  This means that library functions can't easily access the request info.

# Remember, this is a multi-process server.
# Each process handles one and only one request at a time so
# there is no worry that this variable will be clobbered

_the_environ = None

def _set_environ(environ):
    global _the_environ
    _the_environ = environ

# Information published to each module under the name "AKARA"
class AKARA(object):
    def __init__(self, server_root, register_service, module_config):
        self._server_root = server_root
        self.register_service = register_service
        self.module_config = module_config
    def server_root_relative(self, path):
        return os.path.join(self._server_root, path)

    @property
    def wsgi_environ(self):
        return _the_environ



def load_modules(module_dir, server_root, config):
    modules = []
    for filename in os.listdir(module_dir):
        name, ext = os.path.splitext(filename)
        if ext != ".py":
            continue
        full_path = os.path.join(module_dir, filename)

        module_config = {}
        if config.has_section(name):
            module_config.update(config.items(name))
        akara = AKARA(server_root, register_service, module_config)

        module_globals = {
            "__name__": name,
            "__file__": full_path,
            "AKARA": akara,

            # Backwards compatibility
            "AKARA_MODULE_CONFIG": module_config,
            }
        f = open(full_path, "rU")
        # XXX Put some logging here about modules which cannot be parsed
        try:
            module_code = compile(f.read(), full_path, 'exec')
        finally:
            f.close()
        modules.append( (module_code, module_globals) )
    return modules

#### Simple registry

class Registry(object):
    def __init__(self):
        self._registered_services = {}
        self.register_service(self.list_services,
                              "http://purl.org/xml3k/akara/services/builtin/registry", "")
    def register_service(self, function, ident, path):
        print "Added", ident, path, function
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


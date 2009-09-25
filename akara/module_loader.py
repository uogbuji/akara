import os

 
from akara.registry import register_service

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
            "__AKARA_REGISTER_SERVICE__": akara.register_service,
            }
        f = open(full_path, "rU")
        # XXX Put some logging here about modules which cannot be parsed
        try:
            module_code = compile(f.read(), full_path, 'exec')
        finally:
            f.close()
        modules.append( (module_code, module_globals) )
    return modules



"""akara.module_loader - load and prepare Akara extension modules for later use

This reads each Akara extension module and compiles in an environment
which includes the special module variable "AKARA", which can be used
to get more information about the current request.
"""

# The master HTTP process uses this module to import the modules and
# convert them into byte code with the correct globals(). It does not
# exec the byte code. That's the job for the spawned-off HTTP listener
# classes.

import os

from akara.registry import register_service

# services.py sets this to the current WSGI environ before
# calling the handler. This lets the extension module,
# including the 'simple' ones, get access to the environ
# through the module variable 'AKARA'.
# Yes, '_the_environ' is a singleton but remember, this
# is a multi-process server and each process handles one
# and only one request at a time. By design there is no
# worry that this variable will be clobbered.

_the_environ = None

def _set_environ(environ):
    global _the_environ
    _the_environ = environ


# This variable is used as a way to get the current WSGI environ into
# simple_service and related functions.
#
# XXX TurboGears uses a different solution. All the information is
# places into a well-known location which is accessible via imports.
# For example,
#   from akara import request
# The advantages to this are:
#   - no special playing around with compile and globals
#   - all modules have equal access to the info
#     (Ie, consider an Akara library module which wants access to
#      one of the HTTP environ variables.)

class AKARA(object):
    'Information published to each module under the name "AKARA"'

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
    "Read and prepare all extension modules (*.py) from the module directory"
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



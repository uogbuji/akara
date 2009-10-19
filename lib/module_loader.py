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

from akara import logger
from akara.registry import register_service


# Add a global variable so extension modules can get configuration information
class AKARA(object):
    def __init__(self, config, module_name, module_config):
        self.config = config
        self.module_name = module_name
        self.module_config = module_config

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
            for k,v in config.items(name):
                module_config[k] = v

        module_globals = {
            "__name__": name,
            "__file__": full_path,
            "AKARA": AKARA(config, name, module_config)
            }
        f = open(full_path, "rU")
        # XXX Put some logging here about modules which cannot be parsed
        try:
            module_code = compile(f.read(), full_path, 'exec')
        finally:
            f.close()
        modules.append( (name, module_code, module_globals) )
    return modules

def _init_modules(modules):
    # The master node parsed the modules but did not exec them.
    # Do that now, but only once. This will register the functions.
    for name, code, module_globals in modules:
        # NOTE: each child execs this code, so any warning and
        # errors will be repeated for each newly spawned process,
        # including child restarts.
        try:
            exec code in module_globals, module_globals
        except:
            logger.error("Unable to initialize module %r" % (name,),
                         exc_info = True)
    

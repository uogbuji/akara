# -*- coding: iso-8859-1 -*-
# 
# akara
# © 2008-2010 by Uche Ogbuji and Zepheira LLC
#
"""
akara - top-level module for an Akara installation

Copyright 2009-2010 Uche Ogbuji and Zepheira LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Public submodules are:
  registry - direct interface to the resource handler registry
  services - decorators to simplify common ways of writing
       and registring resource handlers

     These modules contain data which change for each HTTP request.
     They are used by some of the services decorators.
  request - information about an incoming HTTP query
  response - data for the outgoing HTTP response

"""

import sys

# Initializes logging and makes the logger public
from akara.logger_config import _logger as logger

# The contents of the "akara.conf" module, as a global namespace dict
raw_config = None

# Access to the per-module configuration. Used like:
#  akara.module_config("akara.demo.xslt")  -- full path name
#  akara.module_config("xslt")   -- in most cases, the last term works fine
#  akara.module_config(__name__)    -- easy way for extension modules to know its own name
#  akara.module_config()    -- get the __name__ automatically

def module_config(path = None):
    if path is None:
        # Let people call this without specifying a name
        path = sys._getframe(1).f_globals["__name__"]

    # The path can either be a full path, like "akara.demo.xslt"
    # or a short name like "xslt". Look for the full name first.
    # We use classes for the config information, which means
    # it isn't so simple, as the class doesn't have a full name.
    # Here's how to specify the full name, to match the path exactly:
    # 
    #    class xslt:
    #        akara_name = "akara.demo.xslt"
    #
    for name, obj in raw_config.items():
        if name[:1] == "_":
            continue
        if hasattr(obj, "akara_name") and obj.akara_name == path:
            return ModuleConfig(path, obj)

    # There's also a shorthand notation, which is useful for
    # the (expected to be) common case where there's no conflict;
    # use the last term of the path as the name of the class.
    class_name = path.rsplit(".", 1)[-1]
    try:
        klass = raw_config[class_name]
    except KeyError:
        # An extension should not require a configuration.
        # Testing for configuration adds if (or try/except) tests, which complicates code.
        # The purpose of returning a NoModuleConfig is to let people write code like:
        #   arg = module_config().get("order", "spam and eggs")
        # and have code work as expected.
        return NoModuleConfig(path)
    else:
        if hasattr(klass, "akara_name"):
            path = klass.akara_name
        return ModuleConfig(path, klass)


# Wrap the configuration object so the class attributes can be
# accessed as dictionaries via [] and get. Why? I think it simplifies
# parameter processing to use config.get("name", default) rather than
# getattr(config, "name", default) and because I think this will grow
# terms like "get_string()" to help with type validation.

class ModuleConfig(object):
    def __init__(self, path, config_class):
        self.path = path
        self.config_class = config_class
        
    def __getitem__(self, name):
        try:
            return getattr(self.config_class, name)
        except AttributeError:
            raise KeyError(name)
        
    def get(self, name, default=None):
        return getattr(self.config_class, name, default)

    def require(self, name, what=None):
        try:
            return getattr(self.config_class, name)
        except AttributeError:
            pass

        msg = (
            "Akara configuration section %(path)r is missing the required parameter %(name)r"
            % dict(path=self.path, name=name) )
        
        if what is not None:
            msg += ": " + what
        raise AttributeError(msg)

    def warn(self, name, default, what=None):
        try:
            return getattr(self.config_class, name)
        except AttributeError:
            pass
        
        msg = "Akara configuration section %(path)r should have the parameter %(name)r"
        if what is not None:
            msg += " (%(what)s)"
        msg += ". Using %(default)r instead."
        msg = msg % dict(path=self.path, name=name, default=default, what=what)
        logger.warn(msg)

        return default


# Used when there is no configuration section for the module.

class NoModuleConfig(object):
    def __init__(self, path):
        self.path = path
        
    def __getitem__(self, name):
        raise KeyError(name)
    
    def get(self, name, default=None):
        return default
    
    def __nonzero__(self):
        # Can be used to test if there was a configuration section, as in
        #    if not module_config("Akara"): print "Something is wrong!"
        return False
    
    def require(self, name, what=None):
        msg = ("Akara configuration section %(path)r is missing. It must have the "
               "parameter %(name)r") % dict(path=self.path, name=name)
        if what is not None:
            msg += ": " + what
        raise AttributeError(msg)

    def warn(self, name, default, what=None):
        msg = ("Akara configuration section %(path)r is missing. "
               "It should have the parameter %(name)r")
        if what is not None:
            msg += " (%(what)s)"
        msg += ". Using %(default)r instead."
        msg = msg % dict(path=self.path, name=name, default=default, what=what)
        logger.warn(msg)

        return default

from version import __version__

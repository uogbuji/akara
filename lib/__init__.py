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

# Initializes logging and make the logger public
from akara.logger_config import _logger as logger


# The contents of the "akara.conf" module
config = None

# The per-module configuration.

class AkaraModuleConfig(object):
    def __getitem__(self, path):
        # Find the config section with that name.
        # First check for the full name (defined by "class akara: name = ...")
        # Note: This is an O(n) search, but n should be small.
        # (Otherwise, I could cache the results)
        for name, value in inspect.getmembers(config):
            if (hasattr(value, "akara") and hasattr(value.akara, "name") and
                value.akara.name == path)
            return value

        ## Nothing found. Assume I can look it up by the last term of the path
        name = path.rsplit(".", 1)[-1]
        try:
            return getattr(config, name)
        except AttributeError:
            raise KeyError(path)

    def get(self, path, default=None):
        try:
            return self[path]
        except KeyError:
            return default

    # XXX do I really want this?
    # XXX What about type checks?
    def require(self, path, error_message):
        try:
            return self[path]
        except KeyError:
            raise ConfigError(error_message.format(path=path))
            
module_config = AkaraModuleConfig()
# Used like:
#  akara.module_config["akara.demo.xslt"]  -- full path name
#  akara.module_config["xslt"]   -- in most cases, the last term works fine
#  akara.module_config[__name__]    -- easy way for extension modules to know its own name

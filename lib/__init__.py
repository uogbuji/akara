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


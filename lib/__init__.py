# -*- coding: iso-8859-1 -*-
# 
# akara
# © 2008, 2009 by Uche Ogbuji and Zepheira LLC
#
"""
akara - top-level module for an Akara installation

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


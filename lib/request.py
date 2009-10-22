"""Information about the incoming request

The available functions and data elements are:

  environ - the corresponding WSGI 'environ' variable
  akara_config - a ConfigParser containing the data from the Akara configuration file

The following are defined if the Akara handler comes from an extension module
  module_name - the name of the extension module
  module_config - the ConfigParser section for the current extension module

These should all be treated as read-only constants.

"""
import os as _os

environ = None
akara_config = None

module_name = None


from UserDict import DictMixin as _DictMixin
class _ModuleConfig(_DictMixin):
#    # Implement an interface like ConfigParser but only for this section
#    def get(self, option):
#        return akara_config.get(module_name, option)
#    def getint(self, option):
#        return akara_config.getint(module_name, option)
#    def getfloat(self, option):
#        return akara_config.getfloat(module_name, option)
#    def getboolean(self, option):
#        return akara_config.getboolean(module_name, option)
#
#    def items(self):
#        return akara_config.items(module_name)
#
#    def set(self, option, value):
#        return akara_config.set(module_name, option, value)
#    def remove_option(option):
#        return akara_config.remove_option(module_name, option)
    
    # Implement a dictionary-like interface
    def __getitem__(self, key):
        return akara_config.get(module_name, key)
    def __setitem__(self, key, value):
        return akara_config.set(module_name, key, value)
    def __delitem__(self, key):
        return akara_config.remove_option(module_name, key)
    def keys(self):
        return akara_config.options(module_name)

module_config = _ModuleConfig()


# Eventually add cookie support?

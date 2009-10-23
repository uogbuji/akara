"""Make sure the akara.conf template agrees with the data in read_config.py

This is a development tool used before doing a distribution.
"""
import ConfigParser

# Only for use in the development environment!
# (That's why I call it 'lib' instead of 'akara')
from lib import read_config

config = ConfigParser.ConfigParser()
files = config.read("akara.conf")
assert files == ["akara.conf"]

DEFAULTS = read_config.SERVER_CONFIG_DEFAULTS

for section, defaults in DEFAULTS.items():
    if not config.has_section(section):
        raise AssertionError("missing section %r" % section)
    for name, value in defaults.iteritems():
        if not config.has_option(section, name):
            raise AssertionError("missing [%r] %r" % (section, name))
        config_value = config.get(section, name)
        if value != config_value:
            raise AssertionError("[%r] %r is %r should be %r" %
                                 (section, name, config_value, value))


# Also check for extra names in the config file
for section in config.sections():
    if section not in DEFAULTS:
        raise AssertionError("Extra section %r" % (section,))
    lowercase_options = [s.lower() for s in DEFAULTS[section]]
    for option in config.options(section):
        if option not in lowercase_options:
            raise AssertionError("Extra option [%s] %r" % (section, option))

print "akara.conf is valid"

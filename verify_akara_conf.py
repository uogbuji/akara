"""Make sure the akara.conf template agrees with the data in read_config.py

This is a development tool used before doing a distribution.
"""
import re

# Only for use in the development environment!
from lib import read_config

_definition_pattern = re.compile("^#(\S+)\s+=\s+(\S+)\s*$")

DEFAULTS = read_config.SERVER_CONFIG_DEFAULTS["global"].copy()
DEFAULTS.update(read_config.SERVER_CONFIG_DEFAULTS["akara.cache"])

expected_names = set(DEFAULTS)

for line in open("akara.conf"):
    m = _definition_pattern.match(line)
    if m is not None:
        name = m.group(1)
        value = m.group(2)
        if name not in DEFAULTS:
            raise AssertionError("Unknown configuration directive: %r" % line)
        if name not in expected_names:
            raise AssertionError("Duplicate configuration directive: %r" % name)

        reference_value = DEFAULTS[name]
        if value != reference_value:
            raise AssertionError("Directive %r says %r but should be %r" %
                                 (name, value, reference_value))

        expected_names.remove(name)

if expected_names:
    raise AssertionError("Template is missing: %r" % expected_names)
print "Template is valid"

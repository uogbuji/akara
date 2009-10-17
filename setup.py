#!/usr/bin/env python

import os
import sys

# Check for the --user option.  This was first added in Python 2.6. 
# For older versions, we'll print out some advice.

if '--user' in sys.argv and sys.version_info[:3] < (2,6,0):
    print """\
************************************************************
The --user option is not supported by this version of Python
(you might consider upgrading to Python 2.6 or newer).  To
install Akara into a user-directory, use the --prefix option to 
setup.py such as this:

    python setup.py install --prefix=$HOME/.local/lib/site-packages

Be sure to change the directory name in the above command to the
actual location where you want the software installed.

To use Akara from a custom install directory, make sure the 
PYTHONPATH environment variable includes the directory before
launching Python. For example:

    env PYTHONPATH=$HOME/.local/lib/site-packages python ...

************************************************************
"""

try:

    # ----------------------------------------------------------------------
    # setuptools configuration
    # ----------------------------------------------------------------------
    from setuptools import setup, find_packages
    setuptools_extras = dict(
        packages=find_packages(),
        zip_safe=False,
        #install_requires='Amara>=2.0a0',
        #tests_require='Paste>=1.0',
        )

except ImportError:

    # ----------------------------------------------------------------------
    # distutils configuration
    # ----------------------------------------------------------------------

    from distutils.core import setup
    
    # The following functions implement a basic version of the find_packages() 
    # functionality that is missing in distutils.

    # Take a directory name such as '/foo/bar/spam' and split it into all components such as
    # as ('foo','bar','spam').    This is slightly different than os.path.split() which only
    # performs a single split()

    def splitalldirs(dirname):
        base, name = os.path.split(dirname)
        if not base:
            # No more base components to split. Done
            return ()
        else:
            # Recursively split the base directory down to get all of the parts
            return splitalldirs(base) + (name,)

    # Find all packages and return them as a list
    def find_packages():
        packages = []
        for path, dirs, files in os.walk("."):
            packagedirs = []
            for dirname in dirs:
                if os.path.exists(os.path.join(path,dirname,"__init__.py")):
                    components = splitalldirs(path) + (dirname,)
                    packagedirs.append(dirname)
                    packagename = ".".join(components)
                    packages.append(packagename)

            # Only continue with package subdirectories
            dirs[:] = packagedirs

        return packages
    setuptools_extras = {'packages' : find_packages() }

setup(name = "akara",
      version = "2.0a0",
      description='Web components for Amara 2.x',
      author='Uche Ogbuji and others',
      author_email='amara-dev@googlegroups.com',
      url='http://wiki.xml3k.org/Akara',
      **setuptools_extras)


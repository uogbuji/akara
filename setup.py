#!/usr/bin/env python

try:
    # Installation goes better with setuptools
    from setuptools import setup, find_packages

    setuptools_extras = dict(
        zip_safe=False,
        #packages = packages,
        #install_requires='Amara>=2.0a0',
        #tests_require='Paste>=1.0',
        )

except ImportError:
    # Workaround for standard distutils
    import os
    from distutils.core import setup

    setuptools_extras = {}
    def find_packages():
        found = []
        for root, dirs, files in os.walk("lib"):
            if "__init__.py" in files:
                found.append(root.replace("/", ".").replace("\\", "."))
        found.sort()
        return found

# The module files are under "lib/". I want them under "akara/"
def renamed_packages():
    names = []
    for package in find_packages():
        if package.startswith("lib"):
            names.append(package.replace("lib", "akara"))
        else:
            raise AssertionError("Unknown package %r" % (package,))
    return names

setuptools_extras["packages"] = renamed_packages()

setup(name = "akara",
      version = "2.0a0",
      description='Web components for Amara 2.x',
      author='Uche Ogbuji and others',
      author_email='amara-dev@googlegroups.com',
      url='http://wiki.xml3k.org/Akara',
      package_dir={'akara':'lib'},
      scripts =['akara'],
      **setuptools_extras)


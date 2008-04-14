#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
    setuptools_extras = dict(
        packages=find_packages(),
        #install_requires='Amara>=1.5',
        #tests_require='Paste>=1.0',
        )

except ImportError:
    from distutils.core import setup
    setuptools_extras = {}

setup(name = "akara",
      version = "2.0prealpha1",
      description='Web components for Amara 2.x',
      author='Uche Ogbuji and others',
      author_email='amara-dev@googlegroups.com',
      url='http://wiki.xml3k.org/Akara',
      **setuptools_extras)


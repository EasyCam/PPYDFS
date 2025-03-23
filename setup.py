#!/usr/bin/env python

version="1.0"
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

here = os.path.abspath(os.path.dirname(__file__))

README = open(os.path.join(here, 'README.md')).read()

setup(name='pydfs',
      version=version,
      description='Python Distributed File System (PYDFS)',
      author='cycleuser',
      author_email='cycleuser@cycleuser.org',
      url='http://blog.cycleuser.org',
      packages=['pydfs'],
      install_requires=[ 
                        "pywebio",
                         ],
     )

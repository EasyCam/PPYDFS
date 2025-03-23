#!/usr/bin/env python

from setuptools import setup, find_packages
import os

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    README = f.read()

setup(
    name='ppydfs',
    version='1.1',
    description='Python Parallel Distributed File System (PPYDFS)',
    long_description=README,
    long_description_content_type='text/markdown',
    author='cycleuser',
    author_email='cycleuser@cycleuser.org',
    url='http://blog.cycleuser.org',
    packages=find_packages(),
    install_requires=["pywebio"],
    python_requires='>=3.9',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    entry_points={
        'console_scripts': [
            'ppydfs=ppydfs.__main__:main',
        ],
    },
)
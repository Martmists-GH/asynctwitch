from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

with open('README.rst') as f:
    long_description = f.read()

setup(
    name='asynctwitch',

    version='4.2.1',

    description='Asynchonous wrapper for twitch IRC3',
    long_description=long_description,

    url='https://github.com/martmists/asynctwitch',

    author='martmists',
    author_email='martmists@gmail.com',

    license='BSD-3-Clause',

    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Topic :: Communications :: Chat',

        'License :: OSI Approved :: BSD License',

        'Programming Language :: Python :: 3.4',
    ],
    install_requires=[
        'aiohttp',
        'isodate'
    ],
    packages=find_packages(),
    keywords='asyncio twitch irc',
)

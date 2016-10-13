from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

with open('README.rst') as f:
    long_description = f.read()

setup(
    name='asynctwitch',

    version='3.1.4',

    description='Asynchonous wrapper for twitch IRC3',
    long_description=long_description,

    url='https://github.com/martmists/asynctwitch',

    author='martmists',
    author_email='martmists@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 5 - Stable',

        'Intended Audience :: Developers',
        'Topic :: Software Development :: Twitch Bot',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.4+',
    ],
    install_requires=[
        'aiohttp',
        'isodate'
    ],
	
    keywords='asyncio twitch irc',
    py_modules=["asynctwitch"]
)
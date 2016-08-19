from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='asynctwitch',

    version='1.0.0',

    description='Asynchonously work with twitch chat',
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

        'Programming Language :: Python :: 3.5',
    ],
    keywords='asynchronous twitch bot library with builtin (optional) commands system',
    py_modules=["asynctwitch"]
)
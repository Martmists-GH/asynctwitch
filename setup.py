# External Libraries
from setuptools import setup, find_packages

with open('README.rst') as f:
    LONG_DESCRIPTION = f.read()

with open("requirements.txt") as f:
    REQUIREMENTS = f.readlines()

setup(
    name='asynctwitch',
    version='5.0.0',
    description='Asynchonous wrapper for twitch IRC3',
    long_description=LONG_DESCRIPTION,
    url='https://github.com/martmists/asynctwitch',
    author='martmists',
    author_email='martmists@gmail.com',
    license='BSD-3-Clause',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers', 'Topic :: Communications :: Chat',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9'
    ],
    install_requires=[REQUIREMENTS],
    extras_require={
        "mysql": ["pymysql"],
        "postgres": ["psycopg2"]
    },
    packages=find_packages(),
    keywords='asyncio twitch irc',
)

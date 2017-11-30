# Copyright © 2016  Lars Peter Søndergaard <lps@chireiden.net>
# Copyright © 2016  FichteFoll <fichtefoll2@googlemail.com>
#
# This file is part of Shanghai, an asynchronous multi-server IRC bot.
#
# Shanghai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shanghai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Shanghai.  If not, see <http://www.gnu.org/licenses/>.

from setuptools import setup

lic = 'GNU General Public License v3 (GPLv3)'
classifiers = [
    'Programming Language :: Python',
    'Natural Language :: English',
    'Development Status :: 3 - Alpha',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: ' + lic,
    'Programming Language :: Python :: 3.6',
]

with open("requirements.in") as f:
    requirements = f.read().split()


setup(
    # Package information
    name='Shanghai',
    version='0.1.0',
    description='Shanghai IRC Bot',
    long_description='Shanghai IRC Bot',
    url='https://github.com/chireiden/shanghai',
    license=lic,
    author='Lars Peter Søndergaard',
    author_email='lps@chireiden.net',

    classifiers=classifiers,
    zip_safe=True,

    # Requirements
    setup_requires=['pip'],
    install_requires=requirements,
    tests_require=['tox'],

    # Scripts and execution
    packages=['shanghai'],
    entry_points={
        'console_scripts': [
            'shanghai=shanghai.main:main'
        ]
    },
)

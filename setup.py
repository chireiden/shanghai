
from setuptools import setup

lic = 'MIT'
classifiers = [
    'Programming Language :: Python',
    'Natural Language :: English',
    'Development Status :: 3 - Alpha',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: ' + lic,
    'Programming Language :: Python :: 3.5',
]


setup(
    # Package information
    name='Shanghai',
    version='0.1.0',
    description='Shanghai IRC Bot',
    long_description='Shanghai IRC Bot',
    url='',
    license=lic,
    author='Lars Peter Søndergaard',
    author_email='lps@chireiden.net',

    classifiers=classifiers,
    zip_safe=False,

    # Requirements
    setup_requires=['pip'],
    install_requires=[
        'ruamel.yaml',
    ],
    tests_require=['pytest', 'flake8'],

    # Scripts and execution
    entry_points={
        'console_scripts': [
            'shanghai=shanghai.main:main'
        ]
    },
)

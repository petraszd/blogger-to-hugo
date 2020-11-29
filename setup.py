import codecs
import os.path
from setuptools import setup


def process_requirements_line(line):
    line = line.strip()
    if '#' in line:
        line = line[:line.index('#')]
    return line


here = os.path.abspath(os.path.dirname(__file__))
with codecs.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


requirements_path = os.path.join(here, 'requirements.txt')
requirements = []
with codecs.open(requirements_path, encoding='utf-8') as f:
    for line in [process_requirements_line(x) for x in f.readlines()]:
        if line:
            requirements.append(line)


setup(
    name='blogger-to-hugo',
    version='1.0.1',
    description='Command line tool to convert Blogger posts to Hugo',
    long_description=long_description,
    url='https://bitbucket.org/petraszd/blogger-to-hugo',
    author='Petras Zdanavicius',
    author_email='petraszd@gmail.com',

    keywords='blogger hugo command line utility',
    py_modules=['blogger_to_hugo'],
    install_requires=requirements,
    extras_require={
        'dev': [],
        'test': [],
    },

    entry_points={
        'console_scripts': ['blogger-to-hugo=blogger_to_hugo:main'],
    },

    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: MIT License',
        'Topic :: Utilities',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)

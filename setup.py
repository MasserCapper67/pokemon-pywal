from setuptools import setup, find_packages

setup(
    name='pokemon-pywal',
    version='0.2',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'pokemon-pywal=pokemon_pywal:main',
        ],
    },
)

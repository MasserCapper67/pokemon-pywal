from setuptools import setup, find_packages

setup(
    name='pokemon-pywal',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'colormath',
    ],
    entry_points={
        'console_scripts': [
            'pokemon-pywal=pokemon_pywal:main',
        ],
    },
)

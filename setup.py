# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import json
from pathlib import Path

import setuptools


def read_version():
    version_path = Path(__file__).resolve().parent / "version.json"
    data = json.loads(version_path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not version:
        raise RuntimeError("version.json enthält keinen gültigen 'version'-Wert")
    return version

try:
    with open('README_PYPI.md', encoding='utf-8') as f:
        long_description = f.read()
except:
    import io
    if Path('README_PYPI.md').exists():
        long_description = io.open('README_PYPI.md', encoding='utf-8').read()
    else:
        long_description = "Kuasarr connects JDownloader with Radarr, Sonarr and LazyLibrarian."

def read_requirements():
    requirements_path = Path(__file__).resolve().parent / "requirements.txt"
    if requirements_path.exists():
        return requirements_path.read_text(encoding="utf-8").splitlines()
    return []


setuptools.setup(
    name="kuasarr",
    version=read_version(),
    author="Ritedt",
    author_email="weedo0780@protonmail.com",
    description="kuasarr connects JDownloader with Radarr, Sonarr and LazyLibrarian. It also decrypts links protected by CAPTCHAs, using an additional CaptchaSolverr.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rix1337/Kuasarr",
    license="MIT",
    packages=setuptools.find_packages(),
    include_package_data=True,
    package_data={
        "kuasarr": [
            "static/*.png",
            "static/*.js",
            "static/*.html",
            "static/*.webmanifest",
            "version.json",
        ]
    },
    install_requires=read_requirements(),
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'kuasarr = kuasarr:run',
        ],
    },
)



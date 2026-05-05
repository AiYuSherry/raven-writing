"""Setup script for Personal Writing."""

from setuptools import setup, find_packages

setup(
    name="personal-writing",
    version="0.1.0",
    description="个人写作工作平台 — 丢素材选风格，同时出多版本",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "flask>=3.0",
        "openpyxl>=3.1",
        "xlrd>=2.0",
    ],
    entry_points={
        "console_scripts": [
            "personal-writing=personal_writing.cli.main:main",
            "pw=personal_writing.cli.main:main",
        ],
    },
)

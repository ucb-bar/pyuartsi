from setuptools import setup, find_namespace_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pyuartsi",
    version="2024.08.14",
    author="-T.K.-",
    author_email="t_k_233@outlook.email",
    description="A standalone implementation of the Tethered Serial Interface (TSI) in Python.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ucb-bar/pyuartsi",
    project_urls={
        
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "pyserial",
    ],
    package_dir={"": "src/"},
    packages=find_namespace_packages(where="src/", include=["pyuartsi"]),
    python_requires=">=3.10",
)

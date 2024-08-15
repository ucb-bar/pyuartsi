import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
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
        "pyglet",
    ],
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.10",
)
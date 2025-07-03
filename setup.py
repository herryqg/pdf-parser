from setuptools import setup, find_packages

setup(
    name="pdf-parser",
    version="0.1.0",
    description="A tool for parsing and modifying PDF text content with font-aware character handling",
    long_description=open("README.md", "r").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "pikepdf>=2.0.0",
        "fonttools>=4.0.0",
        "PyMuPDF>=1.18.0",
    ],
    entry_points={
        'console_scripts': [
            'pdf-replace=pdf_parser.example:main',
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
) 
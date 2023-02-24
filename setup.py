import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="hass_splunk",
    version="0.1.2",
    author="Brett Adams",
    author_email="brett@ba.id.au",
    description="Async single threaded connector to Splunk HEC using an asyncio session",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Bre77/hass_splunk",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

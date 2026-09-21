"""Sanity checks for the Python test environment."""
import sys


def test_python_version():
    assert sys.version_info >= (3, 9)


def test_pipeline_deps_importable():
    import numpy  # noqa: F401
    import pandas  # noqa: F401

import pytest

from tests.util import load_fixture


@pytest.fixture(scope="session")
def js_hittest():
    return load_fixture("js_hittest.json")


@pytest.fixture(scope="session")
def js_roundtrip():
    return load_fixture("js_roundtrip.json")

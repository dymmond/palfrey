import pytest


@pytest.fixture(scope="module", params=["asyncio", "trio"])
def anyio_backend():
    return ("asyncio", {"debug": True})

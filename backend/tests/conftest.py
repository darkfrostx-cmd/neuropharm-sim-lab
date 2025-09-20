import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Restrict anyio-powered tests to asyncio."""

    return "asyncio"

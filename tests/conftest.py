from types import SimpleNamespace
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def make_context():
    def _make_context(route=None, headers=None, method="GET"):
        route = route or {
            "prefix": "/test",
            "target_base": "http://upstream",
            "plugins": [],
        }
        headers = headers or []
        scope = {"method": method, "headers": headers}
        return SimpleNamespace(route=route, scope=scope, extra={})

    return _make_context


@pytest.fixture
def make_response():
    def _make_response(status=200, headers=None, body=b"ok"):
        return SimpleNamespace(status=status, headers=headers or [], body=body)

    return _make_response

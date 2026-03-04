from types import SimpleNamespace

import jwt
import pytest

from app.plugins.errors import (
    JWTMissingAuthHeaderError,
    JWTMissingTenantError,
)
from app.plugins.jwt_auth import ALGORITHM, SECRET, JWTAuthPlugin


@pytest.mark.asyncio
async def test_jwt_auth_sets_tenant_from_valid_token():
    plugin = JWTAuthPlugin()
    token = jwt.encode({"tenant_id": "tenant-a"}, SECRET, algorithm=ALGORITHM)
    context = SimpleNamespace(
        scope={"headers": [(b"authorization", f"Bearer {token}".encode())]},
        tenant="unknown",
    )

    await plugin.before_request(context)

    assert context.tenant == "tenant-a"


@pytest.mark.asyncio
async def test_jwt_auth_raises_when_header_missing():
    plugin = JWTAuthPlugin()
    context = SimpleNamespace(scope={"headers": []}, tenant="unknown")

    with pytest.raises(JWTMissingAuthHeaderError):
        await plugin.before_request(context)


@pytest.mark.asyncio
async def test_jwt_auth_raises_when_tenant_missing():
    plugin = JWTAuthPlugin()
    token = jwt.encode({"sub": "user-1"}, SECRET, algorithm=ALGORITHM)
    context = SimpleNamespace(
        scope={"headers": [(b"authorization", f"Bearer {token}".encode())]},
        tenant="unknown",
    )

    with pytest.raises(JWTMissingTenantError):
        await plugin.before_request(context)

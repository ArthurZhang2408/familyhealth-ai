import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.api.deps import get_memory_service
from app.main import app

BASE = "/api/v1"


async def _create_profile(client: AsyncClient, **overrides: object) -> dict:
    payload = {"name": "Test User", "relationship": "self", **overrides}
    resp = await client.post(f"{BASE}/profiles", json=payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_delete_account_success(client: AsyncClient) -> None:
    """Create a profile, delete the account, verify all data is gone."""
    mock_mem = AsyncMock()
    app.dependency_overrides[get_memory_service] = lambda: mock_mem

    profile = await _create_profile(client, name="Alice", relationship="self")

    with patch("app.api.auth.httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx = AsyncMock()
        mock_httpx.__aenter__ = AsyncMock(return_value=mock_httpx)
        mock_httpx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.delete = AsyncMock(return_value=AsyncMock(status_code=200, is_error=False))
        mock_httpx_cls.return_value = mock_httpx

        resp = await client.delete(f"{BASE}/auth/account")

    assert resp.status_code == 204
    mock_mem.delete_all.assert_called_once_with(uuid.UUID(profile["id"]))

    # Verify profiles are gone
    resp = await client.get(f"{BASE}/profiles")
    assert resp.json()["items"] == []

    app.dependency_overrides.pop(get_memory_service, None)


@pytest.mark.asyncio
async def test_delete_account_unauthenticated(client: AsyncClient) -> None:
    """Request without auth should return 401."""
    from app.core.security import get_current_account

    # Temporarily remove the auth override to test unauthenticated access
    original = app.dependency_overrides.pop(get_current_account, None)
    try:
        async with AsyncClient(
            transport=client._transport, base_url="http://test"
        ) as unauth_client:
            resp = await unauth_client.delete(f"{BASE}/auth/account")
        assert resp.status_code == 401
    finally:
        if original:
            app.dependency_overrides[get_current_account] = original


@pytest.mark.asyncio
async def test_delete_account_no_profiles(client: AsyncClient) -> None:
    """Account with zero profiles should still return 204."""
    mock_mem = AsyncMock()
    app.dependency_overrides[get_memory_service] = lambda: mock_mem

    with patch("app.api.auth.httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx = AsyncMock()
        mock_httpx.__aenter__ = AsyncMock(return_value=mock_httpx)
        mock_httpx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.delete = AsyncMock(return_value=AsyncMock(status_code=200, is_error=False))
        mock_httpx_cls.return_value = mock_httpx

        resp = await client.delete(f"{BASE}/auth/account")

    assert resp.status_code == 204
    mock_mem.delete_all.assert_not_called()

    app.dependency_overrides.pop(get_memory_service, None)


@pytest.mark.asyncio
async def test_delete_account_mem0_failure(client: AsyncClient) -> None:
    """Mem0 failure should not prevent account deletion."""
    mock_mem = AsyncMock()
    mock_mem.delete_all = AsyncMock(side_effect=RuntimeError("Mem0 down"))
    app.dependency_overrides[get_memory_service] = lambda: mock_mem

    await _create_profile(client, name="Bob", relationship="parent")

    with patch("app.api.auth.httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx = AsyncMock()
        mock_httpx.__aenter__ = AsyncMock(return_value=mock_httpx)
        mock_httpx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.delete = AsyncMock(return_value=AsyncMock(status_code=200, is_error=False))
        mock_httpx_cls.return_value = mock_httpx

        resp = await client.delete(f"{BASE}/auth/account")

    assert resp.status_code == 204

    # Verify profiles are still deleted despite Mem0 failure
    resp = await client.get(f"{BASE}/profiles")
    assert resp.json()["items"] == []

    app.dependency_overrides.pop(get_memory_service, None)


@pytest.mark.asyncio
async def test_delete_account_supabase_failure(client: AsyncClient) -> None:
    """Supabase admin API failure should not prevent 204 response."""
    mock_mem = AsyncMock()
    app.dependency_overrides[get_memory_service] = lambda: mock_mem

    await _create_profile(client, name="Carol", relationship="child")

    with patch("app.api.auth.httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx = AsyncMock()
        mock_httpx.__aenter__ = AsyncMock(return_value=mock_httpx)
        mock_httpx.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.delete = AsyncMock(side_effect=RuntimeError("Supabase down"))
        mock_httpx_cls.return_value = mock_httpx

        resp = await client.delete(f"{BASE}/auth/account")

    assert resp.status_code == 204

    # Verify profiles are still deleted despite Supabase failure
    resp = await client.get(f"{BASE}/profiles")
    assert resp.json()["items"] == []

    app.dependency_overrides.pop(get_memory_service, None)

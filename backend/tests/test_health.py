import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] is True


@pytest.mark.asyncio
async def test_health_check_db_failure(client: AsyncClient) -> None:
    """Health endpoint returns degraded status when DB is unreachable."""
    from unittest.mock import AsyncMock, patch

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    with patch("app.core.database.async_session_factory", return_value=mock_session):
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["db"] is False
    assert "error" in data

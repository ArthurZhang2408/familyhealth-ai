import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_profile(client: AsyncClient) -> None:
    response = await client.post(
        "/profiles",
        json={"name": "Test User", "relationship": "self"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["relationship"] == "self"
    assert data["allergies"] == []


@pytest.mark.asyncio
async def test_list_profiles(client: AsyncClient) -> None:
    await client.post("/profiles", json={"name": "User 1", "relationship": "self"})
    await client.post("/profiles", json={"name": "User 2", "relationship": "parent"})

    response = await client.get("/profiles")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient) -> None:
    create_resp = await client.post("/profiles", json={"name": "Mom", "relationship": "parent"})
    pid = create_resp.json()["id"]

    response = await client.get(f"/profiles/{pid}")
    assert response.status_code == 200
    assert response.json()["name"] == "Mom"


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient) -> None:
    create_resp = await client.post("/profiles", json={"name": "Old Name", "relationship": "self"})
    pid = create_resp.json()["id"]

    response = await client.patch(f"/profiles/{pid}", json={"name": "New Name"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_profile(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/profiles", json={"name": "To Delete", "relationship": "other"}
    )
    pid = create_resp.json()["id"]

    response = await client.delete(f"/profiles/{pid}")
    assert response.status_code == 204

    # Profile should no longer be listed
    list_resp = await client.get("/profiles")
    assert list_resp.json()["total"] == 0

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import OTHER_ACCOUNT_ID, TEST_ACCOUNT_ID, use_account

BASE = "/api/v1/profiles"


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create(client: AsyncClient, **overrides: object) -> dict:
    payload = {"name": "Test User", "relationship": "self", **overrides}
    resp = await client.post(BASE, json=payload)
    assert resp.status_code == 201
    return resp.json()


# ── POST /profiles ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_profile(client: AsyncClient) -> None:
    data = await _create(client, name="Alice", relationship="self", sex="female")
    assert data["name"] == "Alice"
    assert data["relationship"] == "self"
    assert data["sex"] == "female"
    assert data["account_id"] == str(TEST_ACCOUNT_ID)
    assert data["allergies"] == []
    assert data["id"]  # UUID present


@pytest.mark.asyncio
async def test_create_profile_full_fields(client: AsyncClient) -> None:
    data = await _create(
        client,
        name="Dad",
        relationship="parent",
        sex="male",
        date_of_birth="1965-03-15",
        blood_type="A+",
        allergies=[{"allergen": "Peanuts", "severity": "severe", "reaction": "anaphylaxis"}],
        current_medications=[{"name": "Lisinopril", "dosage": "10mg", "frequency": "1x daily"}],
        medical_conditions=[
            {"condition": "Hypertension", "diagnosed": "2015", "status": "managed"}
        ],
        family_medical_history={"father": ["heart disease"]},
        emergency_contacts=[{"name": "Mom", "phone": "+1234567890", "relationship": "spouse"}],
    )
    assert data["date_of_birth"] == "1965-03-15"
    assert data["blood_type"] == "A+"
    assert len(data["allergies"]) == 1
    assert data["allergies"][0]["severity"] == "severe"
    assert len(data["current_medications"]) == 1
    assert data["family_medical_history"]["father"] == ["heart disease"]


@pytest.mark.asyncio
async def test_create_duplicate_self_returns_409(client: AsyncClient) -> None:
    await _create(client, relationship="self")
    resp = await client.post(BASE, json={"name": "Second Self", "relationship": "self"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CONFLICT"
    assert isinstance(body["detail"], str)


@pytest.mark.asyncio
async def test_create_multiple_non_self_allowed(client: AsyncClient) -> None:
    await _create(client, name="Parent 1", relationship="parent")
    resp = await client.post(BASE, json={"name": "Parent 2", "relationship": "parent"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_invalid_relationship(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"name": "X", "relationship": "cousin"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_missing_name(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"relationship": "self"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_name_too_long(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"name": "A" * 101, "relationship": "self"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_blood_type(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"name": "X", "relationship": "self", "blood_type": "X+"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_sex(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"name": "X", "relationship": "self", "sex": "unknown"})
    assert resp.status_code == 422


# ── GET /profiles ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_profiles(client: AsyncClient) -> None:
    await _create(client, name="A", relationship="self")
    await _create(client, name="B", relationship="parent")

    resp = await client.get(BASE)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 20


@pytest.mark.asyncio
async def test_list_profiles_empty(client: AsyncClient) -> None:
    resp = await client.get(BASE)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_profiles_pagination(client: AsyncClient) -> None:
    for i in range(3):
        await _create(client, name=f"User {i}", relationship="other")
    resp = await client.get(BASE, params={"page": 2, "per_page": 2})
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["page"] == 2


# ── GET /profiles/{pid} ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient) -> None:
    created = await _create(client, name="Mom", relationship="parent")
    resp = await client.get(f"{BASE}/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mom"


@pytest.mark.asyncio
async def test_get_nonexistent_profile(client: AsyncClient) -> None:
    resp = await client.get(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert isinstance(body["detail"], str)


@pytest.mark.asyncio
async def test_get_other_users_profile(client: AsyncClient) -> None:
    """A user cannot access profiles owned by another account."""
    created = await _create(client, name="My Profile", relationship="self")
    use_account(OTHER_ACCOUNT_ID)
    resp = await client.get(f"{BASE}/{created['id']}")
    assert resp.status_code == 404


# ── PATCH /profiles/{pid} ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient) -> None:
    created = await _create(client, name="Old", relationship="self")
    resp = await client.patch(f"{BASE}/{created['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_update_profile_medical_fields(client: AsyncClient) -> None:
    created = await _create(client, relationship="parent")
    resp = await client.patch(
        f"{BASE}/{created['id']}",
        json={
            "allergies": [{"allergen": "Dust", "severity": "mild"}],
            "blood_type": "O-",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blood_type"] == "O-"
    assert len(data["allergies"]) == 1


@pytest.mark.asyncio
async def test_update_empty_body(client: AsyncClient) -> None:
    created = await _create(client, relationship="self")
    resp = await client.patch(f"{BASE}/{created['id']}", json={})
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_update_relationship_to_self_conflict(client: AsyncClient) -> None:
    await _create(client, name="Me", relationship="self")
    other = await _create(client, name="Other", relationship="other")
    resp = await client.patch(f"{BASE}/{other['id']}", json={"relationship": "self"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_update_other_users_profile(client: AsyncClient) -> None:
    created = await _create(client, name="Mine", relationship="self")
    use_account(OTHER_ACCOUNT_ID)
    resp = await client.patch(f"{BASE}/{created['id']}", json={"name": "Hacked"})
    assert resp.status_code == 404


# ── DELETE /profiles/{pid} ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_profile(client: AsyncClient) -> None:
    created = await _create(client, name="To Delete", relationship="other")
    resp = await client.delete(f"{BASE}/{created['id']}")
    assert resp.status_code == 204

    # No longer visible in list
    list_resp = await client.get(BASE)
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_then_get_returns_404(client: AsyncClient) -> None:
    created = await _create(client, name="Gone", relationship="other")
    await client.delete(f"{BASE}/{created['id']}")
    resp = await client.get(f"{BASE}/{created['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_profile(client: AsyncClient) -> None:
    resp = await client.delete(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_other_users_profile(client: AsyncClient) -> None:
    created = await _create(client, name="Mine", relationship="self")
    use_account(OTHER_ACCOUNT_ID)
    resp = await client.delete(f"{BASE}/{created['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_self_then_recreate(client: AsyncClient) -> None:
    """After soft-deleting a 'self' profile, creating a new one should succeed."""
    created = await _create(client, relationship="self")
    await client.delete(f"{BASE}/{created['id']}")
    resp = await client.post(BASE, json={"name": "New Self", "relationship": "self"})
    assert resp.status_code == 201

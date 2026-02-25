import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_log import ActionLog
from tests.conftest import OTHER_ACCOUNT_ID, TEST_ACCOUNT_ID, use_account

PROFILES = "/api/v1/profiles"


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _create_profile(client: AsyncClient, **overrides: object) -> dict:
    payload = {"name": "Test User", "relationship": "self", **overrides}
    resp = await client.post(PROFILES, json=payload)
    assert resp.status_code == 201
    return resp.json()


def _activity_url(profile_id: str) -> str:
    return f"{PROFILES}/{profile_id}/activity"


# ── Auto-logging on profile create ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_create_logs_entry(client: AsyncClient) -> None:
    profile = await _create_profile(client, name="Mom", relationship="parent")
    resp = await client.get(_activity_url(profile["id"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    entry = data["items"][0]
    assert entry["action_type"] == "profile_created"
    assert entry["payload"]["name"] == "Mom"
    assert entry["payload"]["relationship"] == "parent"
    assert entry["account_id"] == str(TEST_ACCOUNT_ID)


# ── Auto-logging on profile update ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_update_logs_entry(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    await client.patch(f"{PROFILES}/{profile['id']}", json={"name": "Updated Name"})
    resp = await client.get(_activity_url(profile["id"]))
    data = resp.json()
    assert data["total"] == 2  # create + update
    # Newest first — update should be first
    update_entry = data["items"][0]
    assert update_entry["action_type"] == "profile_updated"
    assert update_entry["payload"]["fields_changed"] == ["name"]
    assert update_entry["payload"]["old"]["name"] == "Test User"
    assert update_entry["payload"]["new"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_profile_update_multiple_fields(client: AsyncClient) -> None:
    profile = await _create_profile(client, name="Alice", relationship="parent")
    pid = profile["id"]
    await client.patch(
        f"{PROFILES}/{pid}",
        json={"name": "Bob", "sex": "male", "blood_type": "A+"},
    )
    resp = await client.get(_activity_url(pid))
    entry = resp.json()["items"][0]
    assert set(entry["payload"]["fields_changed"]) == {"name", "sex", "blood_type"}
    assert entry["payload"]["old"]["name"] == "Alice"
    assert entry["payload"]["new"]["name"] == "Bob"
    assert entry["payload"]["old"]["sex"] is None
    assert entry["payload"]["new"]["sex"] == "male"


# ── Auto-logging on profile delete ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_delete_logs_entry(client: AsyncClient, db_session: AsyncSession) -> None:
    profile = await _create_profile(client, name="Doomed", relationship="parent")
    pid = profile["id"]
    delete_resp = await client.delete(f"{PROFILES}/{pid}")
    assert delete_resp.status_code == 204
    # Activity endpoint returns 404 after soft-delete (correct — profile is gone)
    resp = await client.get(_activity_url(pid))
    assert resp.status_code == 404
    # But the log entry exists in the DB — verify via direct query
    result = await db_session.execute(
        select(ActionLog)
        .where(ActionLog.profile_id == uuid.UUID(pid))
        .order_by(ActionLog.id.desc())
    )
    entries = list(result.scalars().all())
    assert len(entries) == 2  # create + delete
    assert entries[0].action_type == "profile_deleted"
    assert entries[0].payload["name"] == "Doomed"
    assert entries[1].action_type == "profile_created"


# ── Activity feed pagination ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_pagination(client: AsyncClient) -> None:
    profile = await _create_profile(client, name="A", relationship="parent")
    pid = profile["id"]
    # Create additional log entries by updating the profile multiple times
    for i in range(4):
        await client.patch(f"{PROFILES}/{pid}", json={"name": f"Name{i}"})
    # 1 create + 4 updates = 5 entries
    resp = await client.get(_activity_url(pid), params={"per_page": 2})
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2

    # Page 2
    resp = await client.get(_activity_url(pid), params={"per_page": 2, "page": 2})
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["page"] == 2

    # Page 3
    resp = await client.get(_activity_url(pid), params={"per_page": 2, "page": 3})
    data = resp.json()
    assert len(data["items"]) == 1


# ── Activity feed ordering ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_newest_first(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    pid = profile["id"]
    await client.patch(f"{PROFILES}/{pid}", json={"name": "Updated"})
    resp = await client.get(_activity_url(pid))
    items = resp.json()["items"]
    assert items[0]["action_type"] == "profile_updated"
    assert items[1]["action_type"] == "profile_created"
    # Timestamps should be descending
    assert items[0]["created_at"] >= items[1]["created_at"]


# ── Activity feed type filter ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_filter_by_type(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    pid = profile["id"]
    await client.patch(f"{PROFILES}/{pid}", json={"name": "Updated"})

    resp = await client.get(_activity_url(pid), params={"action_type": "profile_created"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["action_type"] == "profile_created"

    resp = await client.get(_activity_url(pid), params={"action_type": "profile_updated"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["action_type"] == "profile_updated"


@pytest.mark.asyncio
async def test_activity_filter_invalid_type_returns_422(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    resp = await client.get(
        _activity_url(profile["id"]), params={"action_type": "not_a_real_type"}
    )
    assert resp.status_code == 422


# ── Empty activity feed ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_filter_no_matches(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    pid = profile["id"]
    resp = await client.get(_activity_url(pid), params={"action_type": "diagnosis_started"})
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


# ── Multi-profile isolation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_isolated_between_profiles(client: AsyncClient) -> None:
    """Two profiles under the same account have independent activity feeds."""
    profile_a = await _create_profile(client, name="Alice", relationship="parent")
    profile_b = await _create_profile(client, name="Bob", relationship="child")
    # Update only profile A
    await client.patch(f"{PROFILES}/{profile_a['id']}", json={"name": "Alice2"})

    resp_a = await client.get(_activity_url(profile_a["id"]))
    resp_b = await client.get(_activity_url(profile_b["id"]))
    assert resp_a.json()["total"] == 2  # create + update
    assert resp_b.json()["total"] == 1  # create only
    assert resp_b.json()["items"][0]["payload"]["name"] == "Bob"


# ── Cross-account isolation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_cross_account_returns_404(
    client: AsyncClient,
) -> None:
    profile = await _create_profile(client)
    pid = profile["id"]
    use_account(OTHER_ACCOUNT_ID)
    resp = await client.get(_activity_url(pid))
    assert resp.status_code == 404


# ── Nonexistent profile ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_nonexistent_profile(client: AsyncClient) -> None:
    resp = await client.get(_activity_url(str(uuid.uuid4())))
    assert resp.status_code == 404


# ── Append-only: no mutation endpoints ───────────────────────────────────────


@pytest.mark.asyncio
async def test_no_put_patch_delete_on_activity(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    url = _activity_url(profile["id"])
    assert (await client.put(url, json={})).status_code == 405
    assert (await client.patch(url, json={})).status_code == 405
    assert (await client.delete(url)).status_code == 405
    assert (await client.post(url, json={})).status_code == 405


# ── Response schema fields ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activity_response_has_all_fields(client: AsyncClient) -> None:
    profile = await _create_profile(client)
    resp = await client.get(_activity_url(profile["id"]))
    entry = resp.json()["items"][0]
    assert "id" in entry
    assert "profile_id" in entry
    assert "account_id" in entry
    assert "action_type" in entry
    assert "payload" in entry
    assert "created_at" in entry
    assert isinstance(entry["id"], int)
    assert entry["profile_id"] == profile["id"]

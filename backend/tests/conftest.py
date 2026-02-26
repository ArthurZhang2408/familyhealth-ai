import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.core import AgentCore
from app.agents.registry import ToolRegistry
from app.api.deps import get_agent_core
from app.core.config import settings
from app.core.database import get_db
from app.core.security import CurrentAccount, get_current_account
from app.main import app
from app.models import Base

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.pg_user}:{settings.pg_password}"
    f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_database}_test"
)

TEST_ACCOUNT_ID = uuid.uuid4()
OTHER_ACCOUNT_ID = uuid.uuid4()

# Mutable container so tests can swap the active account mid-test
_current_account = {"id": TEST_ACCOUNT_ID, "email": "test@example.com"}


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    _current_account["id"] = TEST_ACCOUNT_ID
    _current_account["email"] = "test@example.com"

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def override_get_current_account() -> CurrentAccount:
        return CurrentAccount(id=_current_account["id"], email=_current_account["email"])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_account] = override_get_current_account
    # Provide a real AgentCore with a mock LLM router — no fallback.
    # Tests that need specific LLM responses override get_agent_core again
    # in their own fixture (e.g., _override_diagnosis_deps).
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(
        return_value=AsyncMock(content="mock", model="test", usage={}, tool_calls=None)
    )
    app.dependency_overrides[get_agent_core] = lambda: AgentCore(
        llm_router=mock_router, tool_registry=ToolRegistry()
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def use_account(account_id: uuid.UUID, email: str = "other@example.com") -> None:
    """Switch the active test account for subsequent requests."""
    _current_account["id"] = account_id
    _current_account["email"] = email

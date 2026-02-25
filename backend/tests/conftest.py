import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import CurrentAccount, get_current_account
from app.main import app
from app.models import Base

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.pg_user}:{settings.pg_password}"
    f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_database}_test"
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

TEST_ACCOUNT_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def override_get_current_account() -> CurrentAccount:
        return CurrentAccount(id=TEST_ACCOUNT_ID, email="test@example.com")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_account] = override_get_current_account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

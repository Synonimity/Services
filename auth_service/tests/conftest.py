import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.config import Settings, get_settings
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password

# Use temporary file SQLite for testing
db_fd, db_path = tempfile.mkstemp()
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

# Generate temp JWT keys
temp_dir = tempfile.mkdtemp()
priv_key_path = Path(temp_dir) / "private.pem"
pub_key_path = Path(temp_dir) / "public.pem"

@pytest.fixture(autouse=True)
def disable_rate_limiter():
    from app.dependencies import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
priv_key_path.write_bytes(private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
))

public_key = private_key.public_key()
pub_key_path.write_bytes(public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
))

def get_test_settings() -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL,
        secret_key="test-secret-key-that-is-at-least-32-bytes-long",
        jwt_private_key_path=str(priv_key_path),
        jwt_public_key_path=str(pub_key_path),
        is_production=False,
    )





@pytest_asyncio.fixture(scope="function", autouse=True)
async def init_db():
    engine = create_async_engine(
        TEST_DATABASE_URL, 
        echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(init_db) -> AsyncGenerator[AsyncSession, None]:
    TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=init_db, class_=AsyncSession, expire_on_commit=False)
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session
        
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = get_test_settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def create_user(db_session: AsyncSession):
    async def _create_user(username: str, email: str, password: str = "P@ssw0rd123!") -> User:
        user = User(
            username=username,
            email=email.lower(),
            password_hash=hash_password(password),
            is_active=True,
            is_verified=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create_user

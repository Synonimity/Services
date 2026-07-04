"""
All cryptographic primitives live here so there's exactly one place to
audit. Nothing in routers should touch jwt/hashlib/passlib directly.
"""
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# Argon2id - OWASP's current recommendation over bcrypt for new systems.
# Falls back to verifying (not creating) bcrypt hashes if you ever migrate
# from a legacy system.
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def needs_rehash(password_hash: str) -> bool:
    """Call after a successful login; rehash transparently if params changed."""
    return pwd_context.needs_update(password_hash)


# ---------------------------------------------------------------------------
# Access tokens (JWT, RS256 - asymmetric so other KerfSuite services can
# verify with only the public key, never touching the private signing key)
# ---------------------------------------------------------------------------
def create_access_token(user_id: uuid.UUID, extra_claims: dict | None = None) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired/wrong-audience tokens."""
    return jwt.decode(
        token,
        settings.jwt_public_key,
        algorithms=["RS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


# ---------------------------------------------------------------------------
# Refresh tokens - opaque random strings, stored only as a SHA-256 hash.
# Rotated on every use (old one revoked, new one issued) so a replayed/stolen
# token is detectable and single-use.
# ---------------------------------------------------------------------------
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def constant_time_compare(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


# ---------------------------------------------------------------------------
# Symmetric Encryption (for cookies, state, etc.)
# ---------------------------------------------------------------------------
def _get_fernet() -> Fernet:
    # Derive a safe 32-byte Fernet key from the app's secret key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"kerfsuite-fernet-salt",
        info=b"kerfsuite-fernet-info",
    )
    key = base64.urlsafe_b64encode(hkdf.derive(settings.secret_key.encode()))
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()

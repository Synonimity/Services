"""
Every secret value is encrypted with Fernet (AES-128-CBC + HMAC, i.e.
authenticated encryption - a tampered ciphertext fails to decrypt rather
than silently decrypting to garbage) before it touches the database.
Postgres/Supabase only ever sees ciphertext.

This is symmetric encryption with a single master key, not envelope
encryption with per-secret keys or a real KMS. That's a deliberate
simplicity tradeoff for a solo-dev tool, not a claim that this matches
what a managed secrets product (Vault, Doppler, Infisical, cloud KMS)
gives you. See the README for the honest version of that tradeoff.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

settings = get_settings()


class DecryptionError(Exception):
    pass


def _fernet() -> Fernet:
    try:
        return Fernet(settings.master_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "MASTER_ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


def encrypt_value(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        # Either the wrong master key, or the row was tampered with.
        raise DecryptionError("Failed to decrypt - wrong master key or corrupted value.") from exc

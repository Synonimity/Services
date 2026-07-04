import pytest
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    encrypt_value,
    decrypt_value,
)

def test_password_hashing():
    password = "StrongPassword123!"
    hashed = hash_password(password)
    
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

def test_access_token():
    import uuid
    user_id = uuid.uuid4()
    
    token, expires_in = create_access_token(user_id)
    assert expires_in > 0
    
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)

def test_encryption_roundtrip():
    plaintext = "super_secret_code_verifier"
    ciphertext = encrypt_value(plaintext)
    
    assert ciphertext != plaintext
    
    decrypted = decrypt_value(ciphertext)
    assert decrypted == plaintext

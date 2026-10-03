import pytest
from app.security import encrypt_bot_token, decrypt_bot_token, mask_bot_token, generate_csrf_token, verify_csrf_token


def test_bot_token_encryption_at_rest():
    token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyZ"
    encrypted = encrypt_bot_token(token)
    assert encrypted != token
    assert token not in encrypted

    decrypted = decrypt_bot_token(encrypted)
    assert decrypted == token


def test_mask_bot_token():
    token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyZ"
    masked = mask_bot_token(token)
    assert masked.startswith("1234")
    assert masked.endswith("wxyZ")
    assert "..." in masked
    assert token not in masked


def test_csrf_token_generation():
    session_val = "user_session_abc123"
    csrf = generate_csrf_token(session_val)
    assert csrf is not None

    assert verify_csrf_token(csrf, session_val) is True
    assert verify_csrf_token(csrf, "wrong_session") is False
    assert verify_csrf_token("invalid_csrf", session_val) is False

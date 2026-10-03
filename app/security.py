import hmac
import hashlib
import time
import base64
import secrets
from typing import Optional
from cryptography.fernet import Fernet
from app.config import SECRET_KEY, ENCRYPTION_KEY

# Password Hashing using Argon2 with fallback
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _ph = PasswordHasher()

    def hash_password(password: str) -> str:
        return _ph.hash(password)

    def verify_password(password_hash: str, password: str) -> bool:
        try:
            return _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False
        except Exception:
            return False

except ImportError:
    import bcrypt

    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(password_hash: str, password: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False


# Token encryption at rest using Fernet
def _get_fernet() -> Fernet:
    key_bytes = ENCRYPTION_KEY.encode('utf-8')
    # If key length is not valid 32 url-safe base64 bytes, derive a key using SHA256
    if len(key_bytes) != 44:
        derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
        return Fernet(derived)
    return Fernet(key_bytes)


def encrypt_bot_token(token: str) -> str:
    if not token:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(token.encode('utf-8')).decode('utf-8')


def decrypt_bot_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return ""
    try:
        fernet = _get_fernet()
        return fernet.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
    except Exception:
        return ""


def mask_bot_token(token: str) -> str:
    if not token or len(token) < 10:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


# Session Signing & Verification
def sign_session(user_id: int) -> str:
    timestamp = str(int(time.time()))
    payload = f"{user_id}:{timestamp}"
    signature = hmac.new(
        SECRET_KEY.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def verify_session(cookie_val: Optional[str], max_age_seconds: int = 86400 * 7) -> Optional[int]:
    if not cookie_val:
        return None
    try:
        parts = cookie_val.split(":")
        if len(parts) != 3:
            return None
        user_id_str, timestamp_str, signature = parts
        payload = f"{user_id_str}:{timestamp_str}"
        
        expected_sig = hmac.new(
            SECRET_KEY.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Check expiration
        ts = int(timestamp_str)
        if time.time() - ts > max_age_seconds:
            return None

        return int(user_id_str)
    except Exception:
        return None


# CSRF Token Generator & Validator
def generate_csrf_token(session_val: str) -> str:
    return hmac.new(
        SECRET_KEY.encode('utf-8'),
        f"csrf:{session_val}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verify_csrf_token(csrf_token: str, session_val: str) -> bool:
    if not csrf_token or not session_val:
        return False
    expected = generate_csrf_token(session_val)
    return hmac.compare_digest(csrf_token, expected)

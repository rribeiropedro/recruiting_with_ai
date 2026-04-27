import json
from cryptography.fernet import Fernet
from ..config import settings


def encrypt_oauth_token(token_data: dict) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(json.dumps(token_data).encode()).decode()


def decrypt_oauth_token(encrypted: str | None) -> dict | None:
    if not encrypted:
        return None
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return json.loads(f.decrypt(encrypted.encode()))
    except Exception:
        return None

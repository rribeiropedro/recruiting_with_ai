import json
from typing import Any

from cryptography.fernet import Fernet

from ..config import settings


def encrypt_oauth_token(token_data: dict[str, Any]) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(json.dumps(token_data).encode()).decode()


def decrypt_oauth_token(encrypted: str | None) -> dict[str, Any] | None:
    if not encrypted:
        return None
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        result: dict[str, Any] = json.loads(f.decrypt(encrypted.encode()))
        return result
    except Exception:
        return None

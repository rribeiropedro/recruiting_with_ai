from uuid import UUID
from fastapi import Depends, HTTPException, Header
import jwt
from .config import settings


async def get_current_user(authorization: str = Header(...)) -> UUID:
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return UUID(payload["sub"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

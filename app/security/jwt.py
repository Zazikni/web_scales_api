from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from ..config import settings


def create_access_token(subject: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_minutes
    )
    payload = {"sub": subject, "exp": exp}
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> str:
    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Missing sub")
    return str(sub)

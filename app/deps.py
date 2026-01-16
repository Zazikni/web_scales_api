from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_access_token
from .models import User, Device

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    try:
        user_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    user = db.query(User).filter(User.id == int(user_id)).one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


def get_user_device_or_404(db: Session, user_id: int, device_id: int) -> Device:
    dev = (
        db.query(Device)
        .filter(Device.id == device_id, Device.owner_id == user_id)
        .one_or_none()
    )
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import RegisterRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password

logger = logging.getLogger("app.main")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == req.email).one_or_none()
    if exists:
        logger.warning("register failed | email=%s | reason=email_taken", req.email)
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("register success | user_id=%s | email=%s", user.id, user.email)
    return {"id": user.id, "email": user.email}


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        logger.warning(
            "login failed | email=%s",
            form_data.username,
        )
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    logger.info(
        "login success | user_id=%s",
        user.id,
    )
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)

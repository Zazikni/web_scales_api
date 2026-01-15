from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

import logging

from .config import settings
from .db import Base, engine, get_db
from .models import User, Device, AutoUpdateSchedule
from .schemas import (
    RegisterRequest,
    TokenResponse,
    DeviceCreate,
    DeviceUpdate,
    DeviceOut,
    ProductsResponse,
    ProductPatchRequest,
    AutoUpdateConfig,
)
from .security import hash_password, verify_password, create_access_token
from .deps import get_current_user
from .scales_client import (
    encrypt_device_password,
    fetch_products_and_cache,
    load_cached_products,
    save_cached_products,
    push_cache_to_scales,
)
from .scheduler import scheduler, rebuild_jobs_from_db
from .logging_config import setup_logging
from scales.exceptions import DeviceError
from fastapi.middleware.cors import CORSMiddleware


setup_logging(settings.log_level)
logger = logging.getLogger("app.main")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Scales API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)
logger.info("Application started")
logger.info("CORS origins: %s", settings.cors_allow_origins)
logger.info("Database URL: %s", settings.database_url)

origins = settings.cors_allow_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    scheduler.start()
    rebuild_jobs_from_db()


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown(wait=False)


def get_user_device_or_404(db: Session, user_id: int, device_id: int) -> Device:
    dev = (
        db.query(Device)
        .filter(Device.id == device_id, Device.owner_id == user_id)
        .one_or_none()
    )
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev


@app.post("/auth/register", status_code=201)
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


@app.post("/auth/login", response_model=TokenResponse)
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


# ---------- devices ----------


@app.get("/devices", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    logger.info(
        "list devices | user_id=%s",
        user.id,
    )
    return db.query(Device).filter(Device.owner_id == user.id).all()


@app.post("/devices", response_model=DeviceOut, status_code=201)
def create_device(
    req: DeviceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "create device requested | user_id=%s | name=%s | ip=%s | port=%s | protocol=%s",
        user.id,
        req.name,
        req.ip,
        req.port,
        req.protocol,
    )
    dev = Device(
        owner_id=user.id,
        name=req.name,
        description=req.description,
        ip=req.ip,
        port=req.port,
        protocol=req.protocol,
        password_encrypted=encrypt_device_password(req.password),
        products_cache_json=None,
        cached_dirty=False,
    )
    db.add(dev)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "create device failed | user_id=%s | name=%s | reason=name_conflict",
            user.id,
            req.name,
        )
        raise HTTPException(
            status_code=409, detail="Device with this name already exists"
        )

    db.refresh(dev)

    sch = AutoUpdateSchedule(
        device_id=dev.id,
        enabled=settings.scheduler_enabled,
        interval_minutes=settings.scheduler_interval,
        last_run_utc=None,
        last_status=None,
        last_error=None,
    )
    db.add(sch)
    db.commit()
    logger.info(
        "create device success | user_id=%s | device_id=%s | name=%s",
        user.id,
        dev.id,
        dev.name,
    )
    rebuild_jobs_from_db()
    return dev


@app.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "get device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    device = get_user_device_or_404(db, user.id, device_id)

    logger.info(
        "get device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    return device


@app.put("/devices/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    req: DeviceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "update device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)

    if req.name is not None:
        dev.name = req.name
    if req.description is not None:
        dev.description = req.description
    if req.ip is not None:
        dev.ip = req.ip
    if req.port is not None:
        dev.port = req.port
    if req.protocol is not None:
        dev.protocol = req.protocol
    if req.password is not None:
        dev.password_encrypted = encrypt_device_password(req.password)

    db.add(dev)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "update device failed | user_id=%s | device_id=%s | reason=name_conflict",
            user.id,
            device_id,
        )
        raise HTTPException(status_code=409, detail="Device name conflict")
    db.refresh(dev)
    logger.info(
        "update device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    return dev


@app.delete("/devices/{device_id}", status_code=204)
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "delete device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    db.delete(dev)
    db.commit()
    logger.info(
        "delete device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    if settings.scheduler_enabled:
        rebuild_jobs_from_db()
    else:
        logger.info("scheduler disabled | skip rebuild_jobs_from_db")
    return None


# ---------- products ----------


@app.get("/devices/{device_id}/products", response_model=ProductsResponse)
def fetch_products(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "fetch products requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    try:
        products = fetch_products_and_cache(db, dev)
        count = "n/a"
        if isinstance(products, dict) and isinstance(products.get("products"), list):
            count = len(products["products"])
        logger.info(
            "fetch products success | user_id=%s | device_id=%s | count=%s",
            user.id,
            device_id,
            count,
        )
        return ProductsResponse(products=products)
    except DeviceError as e:
        logger.warning(
            "fetch products failed | user_id=%s | device_id=%s | status=503 | err=%s",
            user.id,
            device_id,
            str(e),
        )
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/devices/{device_id}/products/cached", response_model=ProductsResponse)
def get_cached_products(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "get cached products requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    logger.info(
        "get cached products success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    return ProductsResponse(products=load_cached_products(dev))


@app.patch("/devices/{device_id}/products/{plu}", response_model=ProductsResponse)
def patch_product_by_plu(
    device_id: int,
    plu: str,
    req: ProductPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "patch product requested | user_id=%s | device_id=%s | plu=%s",
        user.id,
        device_id,
        plu,
    )

    dev = get_user_device_or_404(db, user.id, device_id)
    products = load_cached_products(dev)

    items = products.get("products", [])
    if not isinstance(items, list):
        logger.error(
            "patch product failed | user_id=%s | device_id=%s | plu=%s | reason=invalid_cache_format",
            user.id,
            device_id,
            plu,
        )
        raise HTTPException(status_code=400, detail="Invalid cached products format")

    found = False
    for p in items:

        if isinstance(p, dict) and "pluNumber" in p and str(p["pluNumber"]) == str(plu):
            for k, v in req.fields.items():
                p[k] = v
            found = True
            break

    if not found:
        logger.warning(
            "patch product failed | user_id=%s | device_id=%s | plu=%s | reason=not_found",
            user.id,
            device_id,
            plu,
        )
        raise HTTPException(status_code=404, detail="Product not found (plu)")

    save_cached_products(db, dev, products, dirty=True)
    logger.info(
        "patch product success | user_id=%s | device_id=%s | plu=%s | fields_updated=%s",
        user.id,
        device_id,
        plu,
        len(req.fields),
    )
    return ProductsResponse(products=products)


@app.post("/devices/{device_id}/upload", status_code=200)
def upload_cache(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "upload cache requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    try:
        push_cache_to_scales(db, dev)
        logger.info(
            "upload cache success | user_id=%s | device_id=%s",
            user.id,
            device_id,
        )
        return {"status": "ok"}
    except DeviceError as e:
        logger.warning(
            "upload cache failed | user_id=%s | device_id=%s | status=503 | err=%s",
            user.id,
            device_id,
            str(e),
        )
        raise HTTPException(status_code=503, detail=str(e))


# ---------- auto update ----------


@app.get("/devices/{device_id}/auto-update", response_model=AutoUpdateConfig)
def get_auto_update(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "get auto-update requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    sch = (
        db.query(AutoUpdateSchedule)
        .filter(AutoUpdateSchedule.device_id == dev.id)
        .one_or_none()
    )
    if not sch:
        logger.info(
            "auto-update config missing | user_id=%s | device_id=%s | action=create_default",
            user.id,
            dev.id,
        )
        sch = AutoUpdateSchedule(
            device_id=dev.id,
            enabled=False,
            interval_minutes=settings.scheduler_interval,
            last_run_utc=None,
            last_status=None,
            last_error=None,
        )
        db.add(sch)
        db.commit()
        db.refresh(sch)
    logger.info(
        "get auto-update success | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        dev.id,
        sch.enabled,
        sch.interval_minutes,
    )
    return AutoUpdateConfig(
        enabled=sch.enabled,
        interval_minutes=sch.interval_minutes,
        last_run_utc=sch.last_run_utc,
        last_status=sch.last_status,
        last_error=sch.last_error,
    )


@app.put("/devices/{device_id}/auto-update", response_model=AutoUpdateConfig)
def set_auto_update(
    device_id: int,
    req: AutoUpdateConfig,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "set auto-update requested | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        device_id,
        req.enabled,
        req.interval_minutes,
    )
    dev = get_user_device_or_404(db, user.id, device_id)

    sch = (
        db.query(AutoUpdateSchedule)
        .filter(AutoUpdateSchedule.device_id == dev.id)
        .one_or_none()
    )
    if not sch:
        logger.info(
            "auto-update config missing | user_id=%s | device_id=%s | action=create",
            user.id,
            dev.id,
        )
        sch = AutoUpdateSchedule(
            device_id=dev.id,
            enabled=req.enabled,
            interval_minutes=req.interval_minutes,
            last_run_utc=None,
            last_status=None,
            last_error=None,
        )
    else:
        logger.info(
            "auto-update config found | user_id=%s | device_id=%s | action=update",
            user.id,
            dev.id,
        )
        sch.enabled = req.enabled
        sch.interval_minutes = req.interval_minutes

    db.add(sch)
    db.commit()
    db.refresh(sch)

    rebuild_jobs_from_db()
    logger.info(
        "set auto-update success | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        dev.id,
        sch.enabled,
        sch.interval_minutes,
    )

    return AutoUpdateConfig(
        enabled=sch.enabled,
        interval_minutes=sch.interval_minutes,
        last_run_utc=sch.last_run_utc,
        last_status=sch.last_status,
        last_error=sch.last_error,
    )

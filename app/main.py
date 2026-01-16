import logging

from fastapi import Depends
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scales.exceptions import DeviceError
from sqlalchemy.orm import Session

from .api.router import api_router
from .config import settings
from .db import Base, engine, get_db
from .deps import get_current_user, get_user_device_or_404
from .logging_config import setup_logging
from .models import User, AutoUpdateSchedule
from .schemas import (
    ProductsResponse,
    ProductPatchRequest,
    AutoUpdateConfig,
)
from .services import (
    fetch_products_and_cache,
    push_cache_to_scales,
)
from .services import load_cached_products, save_cached_products
from .services.scheduler_service import (
    scheduler_rebuild_jobs_from_db,
    scheduler_start,
    scheduler_shutdown,
)

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

app.include_router(api_router)

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
    scheduler_start()
    scheduler_rebuild_jobs_from_db()


@app.on_event("shutdown")
def shutdown():
    scheduler_shutdown()


# ---------- devices ----------


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

    scheduler_rebuild_jobs_from_db()
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

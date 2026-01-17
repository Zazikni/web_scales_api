import logging

from fastapi import APIRouter, Depends, HTTPException
from scales.exceptions import DeviceError
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.schemas import (
    ProductsResponse,
    ProductPatchRequest,
)
from app.services import (
    fetch_products_and_cache,
    push_cache_to_scales,
)
from app.services import load_cached_products, save_cached_products
from app.deps import get_current_user, get_user_device_or_404

logger = logging.getLogger("app.main")

router = APIRouter(prefix="/devices", tags=["products"])


@router.get("/{device_id}/products", response_model=ProductsResponse)
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


@router.get("/{device_id}/products/cached", response_model=ProductsResponse)
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


@router.patch("/{device_id}/products/{plu}", response_model=ProductsResponse)
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


@router.post("/{device_id}/upload", status_code=200)
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

from pydantic import BaseModel
from typing import Any


class ProductsResponse(BaseModel):
    products: Any


class ProductPatchRequest(BaseModel):
    fields: dict[str, Any]

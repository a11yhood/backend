from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class ProductUrlBase(BaseModel):
    url: HttpUrl
    description: str | None = None


class ProductUrlCreate(ProductUrlBase):
    pass


class ProductUrlUpdate(BaseModel):
    url: HttpUrl | None = None
    description: str | None = None


class ProductUrlResponse(ProductUrlBase):
    id: str
    product_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

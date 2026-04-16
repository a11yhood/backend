from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl

from services.timestamps import ApiTimestamp


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
    created_at: ApiTimestamp
    updated_at: ApiTimestamp

    model_config = ConfigDict(from_attributes=True)

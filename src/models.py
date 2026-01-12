from typing import Optional

from pydantic import BaseModel, Field


class Reserved(BaseModel):
    flag: bool = False


class Price(BaseModel):
    amount: Optional[float] = None


class MarketplaceItem(BaseModel):
    title: str = "No title"
    id: str = ""
    web_slug: str = ""
    description: str = ""
    reserved: Reserved = Field(default_factory=Reserved)
    price: Price = Field(default_factory=Price)

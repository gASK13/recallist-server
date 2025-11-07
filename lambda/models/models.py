from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime

class StatusEnum(str, Enum):  # Define the Enum for status
    NEW = "NEW"
    RESOLVED = "RESOLVED"

class Item(BaseModel):
    item: str
    status: Optional[StatusEnum] = StatusEnum.NEW
    createdDate: Optional[datetime] = None
    resolutionDate: Optional[datetime] = None

class ItemList(BaseModel):
    items: list[Item]
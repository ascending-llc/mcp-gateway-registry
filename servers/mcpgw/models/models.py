from typing import Optional

from pydantic import BaseModel, Field

from .enums import DataSourceType, SearchType


class DatabaseQueryRequestBody(BaseModel):
    query: str
    k: int = 4
    entity_id: Optional[str] = None
    sourceType: DataSourceType
    searchType: SearchType



from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    original_filename: str
    file_size: int
    content_type: str
    uploaded_by: int = Field(foreign_key="user.id")
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentResponse(SQLModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    content_type: str
    description: Optional[str]
    created_at: datetime
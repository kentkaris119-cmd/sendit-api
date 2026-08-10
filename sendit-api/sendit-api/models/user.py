from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: str = Field(default="employee")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserCreate(SQLModel):
    username: str
    email: str
    password: str
    full_name: str
    role: str = "employee"


class UserLogin(SQLModel):
    username: str
    password: str


class UserResponse(SQLModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
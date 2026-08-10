from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import aiofiles
import os
import uuid

from database.session import get_session, create_tables
from models.user import User, UserCreate
from models.document import Document, DocumentResponse
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_admin,
    get_employee,
)
from services.weather import get_weather


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()

    if not os.path.exists("uploads"):
        os.makedirs("uploads")

    yield


app = FastAPI(
    title="SendIT API",
    version="1.0",
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)
@app.post("/register")
@limiter.limit("5/minute")
def register(
    request: Request,
    user: UserCreate,
    session: Session = Depends(get_session),
):
    existing = session.exec(
        select(User).where(User.username == user.username)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Username already exists",
        )

    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
        full_name=user.full_name,
        role=user.role,
    )

    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    return db_user
@app.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = session.exec(
        select(User).where(
            User.username == form_data.username
        )
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    if not verify_password(
        form_data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    token = create_access_token(
        {"sub": user.username}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }
@app.get("/weather")
async def weather(
    latitude: float,
    longitude: float,
    current_user: User = Depends(get_current_user),
):
    return await get_weather(latitude, longitude)
@app.post("/upload")
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    current_user: User = Depends(get_employee),
    session: Session = Depends(get_session),
):
    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png", ".docx"]
    extension = os.path.splitext(file.filename)[1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed"
        )

    unique_filename = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join("uploads", unique_filename)

    async with aiofiles.open(file_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    document = Document(
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(content),
        content_type=file.content_type,
        uploaded_by=current_user.id,
        description=description,
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    return {
        "message": "File uploaded successfully",
        "document": document,
    }

@app.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    current_user: User = Depends(get_employee),
    session: Session = Depends(get_session),
):
    return session.exec(select(Document)).all()
@app.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    current_user: User = Depends(get_employee),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return document
@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    admin: User = Depends(get_admin),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    file_path = os.path.join("uploads", document.filename)

    if os.path.exists(file_path):
        os.remove(file_path)

    session.delete(document)
    session.commit()

    return {"message": "Document deleted successfully"}

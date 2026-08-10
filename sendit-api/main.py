from contextlib import asynccontextmanager
from datetime import datetime
import os
import uuid

import aiofiles
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
    UploadFile,
    File,
    Form,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from database.session import create_tables, get_session
from models.user import User, UserCreate
from models.document import Document, DocumentCreate
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
    require_manager_or_admin,
)
from services.weather import get_weather_data

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()

    if not os.path.exists("uploads"):
        os.makedirs("uploads")

    yield


app = FastAPI(
    title="SendIT API",
    version="1.0.0",
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)
@app.post("/register", status_code=201)
@limiter.limit("5/minute")
def register(
    request: Request,
    user_data: UserCreate,
    session: Session = Depends(get_session),
):
    existing = session.exec(
        select(User).where(User.username == user_data.username)
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    existing = session.exec(
        select(User).where(User.email == user_data.email)
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email already exists",
        )

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return {
        "message": "User registered successfully",
        "user": user,
    }
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

    user.last_login = datetime.utcnow()
    session.commit()

    token = create_access_token(
        {"sub": user.username}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }
@app.post("/documents/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    city: str = Form(...),
    country: str = Form("Kenya"),
    description: str = Form(""),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    extension = os.path.splitext(file.filename)[1].lower()

    allowed = [".pdf", ".jpg", ".jpeg", ".png", ".docx"]

    if extension not in allowed:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed",
        )

    unique_name = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join("uploads", unique_name)

    content = await file.read()

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    document = Document(
        filename=unique_name,
        original_filename=file.filename,
        file_size=len(content),
        file_type=file.content_type,
        city=city,
        country=country,
        description=description,
        uploader_id=current_user.id,
        file_path=file_path,
    )

    session.add(document)
    session.commit()
    session.refresh(document)

    return {
        "message": "Document uploaded successfully",
        "document": document,
    }
@app.get("/documents")
@limiter.limit("30/minute")
def list_documents(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(Document)).all()
@app.get("/documents/{document_id}")
@limiter.limit("30/minute")
def get_document(
    request: Request,
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document
@app.post("/documents/{document_id}/weather")
@limiter.limit("20/minute")
async def enrich_document_weather(
    request: Request,
    document_id: int,
    current_user: User = Depends(require_manager_or_admin),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # Example coordinates (replace with actual geocoding if required)
    latitude = -1.286389
    longitude = 36.817223

    weather = await get_weather_data(latitude, longitude)

    document.weather_data = str(weather)
    document.status = "enriched"
    document.weather_fetched_at = datetime.utcnow()
    document.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(document)

    return {
        "message": "Weather data added successfully",
        "document": document,
    }
@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    session.delete(document)
    session.commit()

    return {
        "message": "Document deleted successfully"
    }

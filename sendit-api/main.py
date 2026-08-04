from datetime import datetime
from typing import Optional
import json
import os

import aiofiles

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Request,
    Form
)

from fastapi.security import OAuth2PasswordRequestForm

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from sqlmodel import Session, SQLModel, select

from database.session import (
    get_session,
    engine
)

from models.user import (
    User,
    UserCreate,
    UserResponse
)

from models.document import (
    Document
)

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_admin,
    get_current_manager
)

from services.weather import get_weather


load_dotenv()


app = FastAPI(
    title="SendIt API",
    version="1.0.0",
    description="Document Management & Enrichment API"
)


# ============================================================
# DATABASE
# ============================================================

@app.on_event("startup")
def startup():
    SQLModel.metadata.create_all(engine)


# ============================================================
# FILE CONFIGURATION
# ============================================================

UPLOAD_DIR = "uploads"

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)


MAX_FILE_SIZE = int(
    os.getenv(
        "MAX_UPLOAD_SIZE",
        5 * 1024 * 1024
    )
)


ALLOWED_EXTENSIONS = [
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".docx"
]


# ============================================================
# RATE LIMITING
# ============================================================

limiter = Limiter(
    key_func=get_remote_address
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler
)


# ============================================================
# BASIC ROUTE
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Welcome to SendIt API",
        "version": "1.0.0"
    }


# ============================================================
# REGISTER
# ============================================================

@app.post(
    "/register",
    response_model=UserResponse
)
def register(
    user_data: UserCreate,
    session: Session = Depends(get_session)
):

    existing_username = session.exec(
        select(User).where(
            User.username == user_data.username
        )
    ).first()

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    existing_email = session.exec(
        select(User).where(
            User.email == user_data.email
        )
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    if user_data.role not in [
        "admin",
        "manager",
        "staff"
    ]:
        raise HTTPException(
            status_code=400,
            detail="Invalid role"
        )

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(
            user_data.password
        ),
        full_name=user_data.full_name,
        role=user_data.role
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


# ============================================================
# LOGIN
# ============================================================

@app.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):

    user = session.exec(
        select(User).where(
            User.username == form_data.username
        )
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(
        form_data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User is inactive"
        )

    user.last_login = datetime.utcnow()

    session.add(user)
    session.commit()

    access_token = create_access_token(
        {
            "sub": user.username
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


# ============================================================
# CURRENT USER
# ============================================================

@app.get(
    "/me",
    response_model=UserResponse
)
def get_me(
    current_user: User = Depends(
        get_current_user
    )
):

    return current_user


# ============================================================
# FILE VALIDATION
# ============================================================

def validate_file(
    file: UploadFile
) -> tuple:

    if not file.filename:
        return False, "Filename is required"

    file_extension = os.path.splitext(
        file.filename
    )[1].lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        return (
            False,
            "File type not allowed. "
            f"Allowed types: "
            f"{', '.join(ALLOWED_EXTENSIONS)}"
        )

    return True, ""


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@app.post("/documents/upload")
@limiter.limit("10/hour")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    city: str = Form(...),
    description: Optional[str] = Form(None),
    country: str = Form("Kenya"),
    current_user: User = Depends(
        get_current_user
    ),
    session: Session = Depends(
        get_session
    )
):

    # 1. Validate extension

    valid, error_message = validate_file(
        file
    )

    if not valid:
        raise HTTPException(
            status_code=400,
            detail=error_message
        )

    # 2. Read file

    contents = await file.read()

    file_size = len(contents)

    # 3. Validate size

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                "File too large. "
                f"Maximum size: "
                f"{MAX_FILE_SIZE // (1024 * 1024)} MB"
            )
        )

    # 4. Generate safe filename

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    original_name = os.path.basename(
        file.filename
    )

    safe_original_name = (
        original_name
        .replace(" ", "_")
    )

    safe_filename = (
        f"{timestamp}_"
        f"{current_user.id}_"
        f"{safe_original_name}"
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        safe_filename
    )

    # 5. Save file

    async with aiofiles.open(
        file_path,
        "wb"
    ) as out_file:

        await out_file.write(
            contents
        )

    # 6. Create database record

    document = Document(
        filename=safe_filename,
        original_filename=original_name,
        file_size=file_size,
        file_type=(
            file.content_type
            or "application/octet-stream"
        ),
        city=city,
        country=country,
        description=description,
        uploader_id=current_user.id,
        file_path=file_path,
        status="processing"
    )

    session.add(document)

    session.commit()

    session.refresh(document)

    # 7. Weather enrichment

    try:

        weather_data = await get_weather(
            city,
            country
        )

        if weather_data:

            document.weather_data = (
                json.dumps(weather_data)
            )

            document.weather_fetched_at = (
                datetime.utcnow()
            )

            document.status = "enriched"

            session.commit()

    except Exception as e:

        print(
            f"Weather API error: {e}"
        )

        document.status = "uploaded"

        session.commit()

    return {
        "message": "Document uploaded successfully",
        "document_id": document.id,
        "filename": document.original_filename,
        "status": document.status
    }


# ============================================================
# LIST DOCUMENTS
# ============================================================

@app.get("/documents")
@limiter.limit("30/minute")
def list_documents(
    request: Request,
    status: Optional[str] = None,
    city: Optional[str] = None,
    current_user: User = Depends(
        get_current_user
    ),
    session: Session = Depends(
        get_session
    )
):

    query = select(Document)

    if current_user.role not in [
        "admin",
        "manager"
    ]:

        query = query.where(
            Document.uploader_id
            == current_user.id
        )

    if status:

        query = query.where(
            Document.status == status
        )

    if city:

        query = query.where(
            Document.city == city
        )

    return session.exec(query).all()


# ============================================================
# GET DOCUMENT
# ============================================================

@app.get("/documents/{document_id}")
@limiter.limit("30/minute")
def get_document(
    request: Request,
    document_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    session: Session = Depends(
        get_session
    )
):

    document = session.get(
        Document,
        document_id
    )

    if not document:

        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if (
        current_user.role
        not in ["admin", "manager"]
        and document.uploader_id
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    return document


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(
        get_current_manager
    ),
    session: Session = Depends(
        get_session
    )
):

    document = session.get(
        Document,
        document_id
    )

    if not document:

        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if os.path.exists(
        document.file_path
    ):

        os.remove(
            document.file_path
        )

    session.delete(document)

    session.commit()

    return {
        "message": "Document deleted successfully"
    }


# ============================================================
# MANUAL WEATHER ENRICHMENT
# ============================================================

@app.post(
    "/documents/{document_id}/enrich"
)
@limiter.limit("5/minute")
async def enrich_document(
    request: Request,
    document_id: int,
    current_user: User = Depends(
        get_current_manager
    ),
    session: Session = Depends(
        get_session
    )
):

    document = session.get(
        Document,
        document_id
    )

    if not document:

        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if document.status == "enriched":

        return {
            "message": "Document already enriched"
        }

    weather_data = await get_weather(
        document.city,
        document.country
    )

    if weather_data and "error" not in weather_data:

        document.weather_data = (
            json.dumps(weather_data)
        )

        document.weather_fetched_at = (
            datetime.utcnow()
        )

        document.status = "enriched"

        session.commit()

        return {
            "message": "Document enriched successfully",
            "weather": weather_data
        }

    document.status = "failed"

    session.commit()

    raise HTTPException(
        status_code=500,
        detail="Failed to enrich document with weather data"
    )


# ============================================================
# GET DOCUMENT WEATHER
# ============================================================

@app.get(
    "/documents/{document_id}/weather"
)
@limiter.limit("10/minute")
def get_document_weather(
    request: Request,
    document_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    session: Session = Depends(
        get_session
    )
):

    document = session.get(
        Document,
        document_id
    )

    if not document:

        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if (
        current_user.role
        not in ["admin", "manager"]
        and document.uploader_id
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    if not document.weather_data:

        raise HTTPException(
            status_code=404,
            detail="No weather data available for this document"
        )

    return {
        "document_id": document.id,
        "city": document.city,
        "country": document.country,
        "weather": json.loads(
            document.weather_data
        )
    }

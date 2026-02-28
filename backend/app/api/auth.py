"""
TenderWriter — Authentication API

Simple JWT-based authentication with user registration and login.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
import string
import structlog
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio

from app.config import settings
from app.db.database import get_db
from app.models import User, OTPToken

logger = structlog.get_logger()

router = APIRouter()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Schemas ──


class UserRegister(BaseModel):
    email: str
    name: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str

class OTPVerify(BaseModel):
    email: str
    otp: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Helpers ──


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)

def generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))

async def send_otp_email(email: str, otp: str):
    """Send an OTP email using SMTP if configured, otherwise fallback to logging."""
    if not settings.smtp_host:
        print(f"DEBUG: SMTP host not configured. Fallback to mock log. email={email} otp={otp}")
        logger.info("SMTP host not configured. Fallback to mock log.", action="send_otp", email=email, otp=otp)
        return

    subject = f"{otp} is your TenderWriter verification code"
    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #2563eb;">TenderWriter Verification</h2>
                <p>Hello,</p>
                <p>Use the following code to verify your account:</p>
                <div style="background: #f3f4f6; padding: 15px; border-radius: 5px; font-size: 24px; font-weight: bold; text-align: center; letter-spacing: 5px; color: #1e40af;">
                    {otp}
                </div>
                <p>This code will expire in 15 minutes.</p>
                <p>If you didn't request this, please ignore this email.</p>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #666;">This is an automated message from TenderWriter AI.</p>
            </div>
        </body>
    </html>
    """

    try:
        # We run the synchronous smtp calls in a separate thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_sync_email, email, subject, body)
        logger.info("OTP email sent successfully", email=email)
    except Exception as e:
        logger.error("Failed to send OTP email", error=str(e), email=email)

def _send_sync_email(to_email: str, subject: str, html_content: str):
    """Synchronous function to send email via smtplib."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    
    msg.attach(MIMEText(html_content, "html"))
    
    print(f"DEBUG: Attempting to connect to SMTP {settings.smtp_host}:{settings.smtp_port}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
    print(f"DEBUG: Email sent successfully to {to_email}")


# ── Routes ──


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user account and generate OTP for email verification."""
    print(f"DEBUG: RECEIVED_REGISTER_REQUEST email={data.email} smtp_host={settings.smtp_host} smtp_port={settings.smtp_port}")
    
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    logger.info("Checks passed, creating user object")
    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        role="editor",
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    logger.info("User added to session, flushing...")
    await db.flush()
    logger.info("Flush complete", user_id=user.id)

    # Generate OTP
    logger.info("Generating OTP")
    otp = generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    logger.info("Creating OTP record", expires_at=str(expires))
    otp_token = OTPToken(user_id=user.id, token=otp, expires_at=expires)
    db.add(otp_token)
    logger.info("Committing transaction")
    await db.commit()
    logger.info("Commit complete, refreshing user")
    await db.refresh(user)

    # Send OTP
    await send_otp_email(user.email, otp_token.token)

    return {"message": "Registration successful. Please check your email for the OTP to verify your account."}

@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db)):
    """Verify the 2FA OTP and return JWT token."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
        
    result = await db.execute(select(OTPToken).where(OTPToken.user_id == user.id, OTPToken.token == data.otp))
    otp_record = result.scalar_one_or_none()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    if otp_record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Expired OTP")

    user.is_verified = True
    await db.delete(otp_record)
    await db.commit()
    
    logger.info("User verified via OTP", user_id=user.id, email=user.email)
    
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and get an access token."""
    print(f"DEBUG: Login attempt for {data.email}")
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"Login failed: User {data.email} not found")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.is_active:
        logger.warning(f"Login failed: Account disabled for {data.email}")
        raise HTTPException(status_code=403, detail="Account disabled")
        
    if not user.is_verified:
        logger.warning(f"Login failed: Account not verified for {data.email}")
        raise HTTPException(status_code=403, detail="Account not verified (2FA required)")
    
    if not verify_password(data.password, user.hashed_password):
        logger.warning(f"Login failed: Password mismatch for {data.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id), "email": user.email})

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
):
    """
    Validate access token and return the current user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: UserResponse = Depends(get_current_user)):
    """Get current user profile."""
    return current_user

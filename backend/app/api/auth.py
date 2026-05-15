"""
TenderWriter — Authentication API

Simple JWT-based authentication with user registration and login.
"""

import asyncio
import hashlib
import hmac
import secrets
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models import OTPToken, User
from app.services.mattermost import provision_mm_user_for_tw_user

# Auth mode detection
_AUTH_MODE = (settings.auth_provider or "legacy").strip().lower()

logger = structlog.get_logger()

router = APIRouter()

limiter = Limiter(key_func=get_remote_address)

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    default="argon2",
    deprecated=["pbkdf2_sha256"],
    argon2__time_cost=3,
    argon2__memory_cost=65536,  # 64 MB
    argon2__parallelism=2,
    argon2__hash_len=32,
    argon2__salt_len=16,
)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Schemas ──


class UserRegister(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class OTPVerify(BaseModel):
    email: EmailStr
    otp: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    auth_source: str | None = None

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


def get_frontend_base_url() -> str:
    origins = [
        origin.strip() for origin in (settings.cors_origins or "").split(",") if origin.strip()
    ]
    return origins[0].rstrip("/") if origins else "http://localhost:3000"


def password_reset_signature(hashed_password: str) -> str:
    return hmac.new(
        settings.app_secret_key.encode("utf-8"),
        hashed_password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_password_reset_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "purpose": "password_reset",
        "pwd_sig": password_reset_signature(user.hashed_password),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Check if a password hash should be upgraded to the current default algorithm."""
    return pwd_context.needs_update(hashed)


def hash_password(password: str) -> str:
    """Hash a password for storage (uses Argon2id as default)."""
    return pwd_context.hash(password)


def generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def mask_email(email: str) -> str:
    """Mask email for safe logging."""
    if "@" in email:
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"
    return "***@***"


async def send_otp_email(email: str, otp: str):
    """Send an OTP email using SMTP if configured, otherwise fallback to logging."""
    if not settings.smtp_host:
        logger.info(
            "SMTP host not configured. Fallback to mock log.",
            action="send_otp",
            email=mask_email(email),
        )
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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_sync_email, email, subject, body)
        logger.info("OTP email sent successfully", email=mask_email(email))
    except Exception as e:
        logger.error("Failed to send OTP email", error=str(e), email=mask_email(email))
        raise


async def send_password_reset_email(email: str, reset_url: str):
    """Send a password reset email."""
    if not settings.smtp_host:
        logger.info(
            "SMTP host not configured. Fallback to mock log.",
            action="send_password_reset",
            email=mask_email(email),
        )
        return

    subject = "TenderWriter password reset"
    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #2563eb;">TenderWriter Password Reset</h2>
                <p>Hello,</p>
                <p>You requested a password reset for your TenderWriter account.</p>
                <p>
                    <a
                        href="{reset_url}"
                        style="display: inline-block; background: #2563eb; color: #fff; text-decoration: none; padding: 12px 18px; border-radius: 8px; font-weight: bold;"
                    >
                        Reset password
                    </a>
                </p>
                <p>If the button does not work, copy and paste this URL into your browser:</p>
                <p style="word-break: break-all;">{reset_url}</p>
                <p>This link expires in {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
                <p>If you didn't request this, you can ignore this email.</p>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #666;">This is an automated message from TenderWriter AI.</p>
            </div>
        </body>
    </html>
    """

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_sync_email, email, subject, body)
        logger.info("Password reset email sent successfully", email=mask_email(email))
    except Exception as e:
        logger.error("Failed to send password reset email", error=str(e), email=mask_email(email))
        raise


def _send_sync_email(to_email: str, subject: str, html_content: str):
    """Synchronous function to send email via smtplib."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


# ── Routes ──


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user account and generate OTP for email verification."""
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        role="editor",
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Generate OTP
    otp = generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    otp_token = OTPToken(user_id=user.id, token=otp, expires_at=expires)
    db.add(otp_token)

    try:
        await send_otp_email(user.email, otp_token.token)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Unable to send verification code. Please try again.",
        ) from exc

    await db.commit()

    return {
        "message": "Registration successful. Please check your email for the OTP to verify your account."
    }


@router.post("/verify-otp", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_otp(
    request: Request,
    data: OTPVerify,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Verify the 2FA OTP and return JWT token."""
    invalid_otp_error = HTTPException(status_code=400, detail="Invalid OTP")

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise invalid_otp_error

    result = await db.execute(
        select(OTPToken)
        .where(OTPToken.user_id == user.id)
        .order_by(OTPToken.created_at.desc(), OTPToken.id.desc())
        .limit(1)
    )
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        raise invalid_otp_error

    # Check max attempts
    if otp_record.attempts >= otp_record.max_attempts:
        await db.execute(delete(OTPToken).where(OTPToken.user_id == user.id))
        await db.commit()
        raise HTTPException(
            status_code=400, detail="Too many failed attempts. Please request a new OTP."
        )

    # Check expiration
    if otp_record.expires_at < datetime.now(timezone.utc):
        await db.execute(delete(OTPToken).where(OTPToken.user_id == user.id))
        await db.commit()
        raise HTTPException(status_code=400, detail="Expired OTP")

    # Timing-safe comparison
    if not hmac.compare_digest(otp_record.token.encode(), data.otp.encode()):
        # Increment failed attempts
        otp_record.attempts += 1
        if otp_record.attempts >= otp_record.max_attempts:
            await db.execute(delete(OTPToken).where(OTPToken.user_id == user.id))
            await db.commit()
            raise HTTPException(
                status_code=400, detail="Too many failed attempts. Please request a new OTP."
            )
        await db.commit()
        remaining = otp_record.max_attempts - otp_record.attempts
        raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempts remaining.")

    user.is_verified = True
    await db.execute(delete(OTPToken).where(OTPToken.user_id == user.id))
    await db.commit()

    logger.info("User verified via OTP", user_id=user.id, email=mask_email(user.email))

    token = create_access_token({"sub": str(user.id), "email": user.email})

    background_tasks.add_task(
        provision_mm_user_for_tw_user,
        user_email=user.email,
        user_name=user.name,
        tw_user_id=user.id,
    )

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: UserLogin,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and get an access token."""
    if _AUTH_MODE == "keycloak":
        logger.warning(
            "auth.legacy_login_blocked",
            email=mask_email(data.email),
            auth_mode=_AUTH_MODE,
        )
        raise HTTPException(
            status_code=409,
            detail="Password login is disabled while Keycloak auth is enabled. Use SSO.",
        )

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"Login failed: User {mask_email(data.email)} not found")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        logger.warning(f"Login failed: Account disabled for {mask_email(data.email)}")
        raise HTTPException(status_code=403, detail="Account disabled")

    if not user.is_verified:
        logger.warning(f"Login failed: Account not verified for {mask_email(data.email)}")
        raise HTTPException(status_code=403, detail="Account not verified (2FA required)")

    if user.hashed_password == "__keycloak_managed__":
        logger.warning(
            "auth.local_login_unavailable",
            email=mask_email(data.email),
            auth_mode=_AUTH_MODE,
        )
        raise HTTPException(
            status_code=403,
            detail="This account does not have a local password yet. Use SSO or set a local password first.",
        )

    if not verify_password(data.password, user.hashed_password):
        logger.warning(f"Login failed: Password mismatch for {mask_email(data.email)}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Transparent rehash: upgrade legacy hashes (pbkdf2/bcrypt) to Argon2id
    if needs_rehash(user.hashed_password):
        new_hash = hash_password(data.password)
        user.hashed_password = new_hash
        await db.commit()
        logger.info(
            "auth.password_rehashed",
            email=mask_email(data.email),
            reason="deprecated_algorithm",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})

    background_tasks.add_task(
        provision_mm_user_for_tw_user,
        user_email=user.email,
        user_name=user.name,
        tw_user_id=user.id,
    )

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/request-password-reset")
@limiter.limit("3/minute")
async def request_password_reset(
    request: Request,
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a password reset link for a local password account."""
    generic_response = {
        "message": "If an account exists for that email, a password reset link has been sent."
    }

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    logger.info(
        "auth.password_reset_requested",
        email=mask_email(data.email),
        account_found=bool(user),
    )

    if not user or not user.is_active:
        return generic_response

    token = create_password_reset_token(user)
    reset_url = f"{get_frontend_base_url()}/forgot-password?token={token}"

    try:
        await send_password_reset_email(user.email, reset_url)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to send password reset email. Please try again.",
        ) from exc

    return generic_response


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Reset the local password using a short-lived signed token."""
    invalid_token_error = HTTPException(
        status_code=400,
        detail="Invalid or expired reset token.",
    )

    try:
        payload = jwt.decode(data.token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise invalid_token_error from exc

    if payload.get("purpose") != "password_reset":
        raise invalid_token_error

    user_id = payload.get("sub")
    if not user_id:
        raise invalid_token_error

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise invalid_token_error

    expected_sig = password_reset_signature(user.hashed_password)
    if not hmac.compare_digest(payload.get("pwd_sig", ""), expected_sig):
        raise invalid_token_error

    user.hashed_password = hash_password(data.new_password)
    user.is_verified = True
    await db.commit()

    logger.info(
        "auth.password_reset_completed",
        user_id=user.id,
        email=mask_email(user.email),
    )

    return {"message": "Password reset successful. You can now log in."}


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Validate access token via the configured auth provider.

    Delegates to ``app.auth.provider`` — see ``AUTH_PROVIDER`` in .env.
    """
    from app.auth.provider import get_current_user as _provider_get_current_user

    return await _provider_get_current_user(token=token, db=db)


class ProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: UserResponse = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile (name and/or email)."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.email is not None and data.email != user.email:
        dup = await db.execute(select(User).where(User.email == data.email))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = data.email

    if data.name is not None:
        user.name = data.name

    await db.commit()
    await db.refresh(user)
    logger.info("Profile updated", user_id=user.id, email=mask_email(user.email))
    return UserResponse.model_validate(user)


# ── Auth config (public, no auth required) ──


@router.get("/config")
async def auth_config():
    """Return auth configuration for the frontend.

    Public endpoint — no authentication required.
    Tells the frontend which auth mode is active so it can render
    the correct login UI (form, SSO, or both).
    """
    config = {"auth_mode": _AUTH_MODE}
    if _AUTH_MODE in {"keycloak", "hybrid"}:
        config.update(
            {
                "keycloak_url": settings.keycloak_url,
                "keycloak_realm": settings.keycloak_realm,
                "keycloak_client_id": settings.keycloak_client_id,
            }
        )
    return config


# ── Logout ──


@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    """Server-side logout.

    In legacy mode: no-op (client just removes localStorage token).
    In keycloak mode: logs the event for audit. The frontend then
    redirects to Keycloak end-session endpoint for federated logout.

    In both cases the frontend clears its local state.
    """
    logger.info(
        "auth.logout",
        user_id=current_user.id,
        email=mask_email(current_user.email),
        auth_mode=_AUTH_MODE,
    )

    if _AUTH_MODE == "keycloak":
        # Build Keycloak end-session URL for the frontend to redirect to
        end_session_url = (
            f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
            f"/protocol/openid-connect/logout"
            f"?client_id={settings.keycloak_client_id}"
        )
        return {
            "message": "Logged out",
            "redirect_url": end_session_url,
        }

    return {"message": "Logged out"}


@router.get("/password-hash-stats")
async def password_hash_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return password hashing algorithm distribution (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    from sqlalchemy import text

    query = text("""
        SELECT
            CASE
                WHEN hashed_password LIKE '$argon2%' THEN 'argon2'
                WHEN hashed_password LIKE '$pbkdf2%' THEN 'pbkdf2'
                WHEN hashed_password LIKE '$2b$%'    THEN 'bcrypt'
                WHEN hashed_password = '__keycloak_managed__' THEN 'keycloak'
                ELSE 'unknown'
            END AS algorithm,
            COUNT(*) AS user_count
        FROM users
        GROUP BY algorithm
        ORDER BY user_count DESC
    """)
    result = await db.execute(query)
    rows = result.all()

    total = sum(r.user_count for r in rows)
    return {
        "total_users": total,
        "algorithms": [
            {
                "algorithm": r.algorithm,
                "count": r.user_count,
                "percentage": round(r.user_count * 100.0 / max(total, 1), 1),
            }
            for r in rows
        ],
    }

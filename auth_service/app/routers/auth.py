from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
import structlog
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, limiter
from app.models import RefreshToken, User
from app.schemas import RefreshRequest, TokenResponse, UserCreate, UserLogin, UserOut
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)

settings = get_settings()
logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    access_token, expires_in = create_access_token(user.id)

    raw_refresh = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_token_expiry(),
        )
    )
    await db.commit()

    # The raw refresh token only ever exists in this response - the DB only
    # ever holds its hash, same principle as a password.
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh, expires_in=expires_in)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(
        username=payload.username,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("registration_failed_duplicate", email=payload.email.lower())
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        )
    await db.refresh(user)
    logger.info("user_registered", user_id=user.id, email=user.email)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(or_(User.username == payload.identifier, User.email == payload.identifier.lower()))
    )
    user = result.scalar_one_or_none()

    # Deliberately identical error/timing path for "no such user" and "bad
    # password" so the endpoint can't be used to enumerate valid usernames.
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if user is None or user.password_hash is None:
        # Still run a hash to keep response timing similar to the real path.
        hash_password(payload.password)
        logger.warning("login_failed_invalid_user", identifier=payload.identifier)
        raise generic_error

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to repeated failed login attempts.",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_logins:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.lockout_minutes)
            logger.warning("account_locked", user_id=user.id, failed_attempts=user.failed_login_attempts)
        await db.commit()
        logger.warning("login_failed_bad_password", user_id=user.id)
        raise generic_error

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled.")

    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()

    logger.info("user_logged_in", user_id=user.id)
    token_response = await _issue_tokens(db, user)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()

    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    if stored is None:
        raise invalid

    if stored.revoked:
        logger.warning("refresh_token_replay_detected", user_id=stored.user_id)
        await db.execute(update(RefreshToken).where(RefreshToken.user_id == stored.user_id).values(revoked=True))
        await db.commit()
        raise invalid

    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if expires_at < datetime.now(timezone.utc):
        raise invalid

    # Rotation: this token is single-use. Revoke it immediately, then issue
    # a brand new access + refresh pair. If a revoked token is ever replayed,
    # that's a strong signal of theft - in a production system you'd also
    # revoke the whole token family here.
    stored.revoked = True

    result = await db.execute(select(User).where(User.id == stored.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await db.commit()
        raise invalid

    token_response = await _issue_tokens(db, user)

    # Cleanup expired/revoked tokens older than 7 days for this user
    # Handle naive datetimes for SQLite compatibility
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.id,
            or_(
                RefreshToken.revoked == True,
                RefreshToken.expires_at < cutoff,
            ),
        )
    )
    await db.commit()
    logger.info("token_refreshed", user_id=user.id)

    return token_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def logout(request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    stored = result.scalar_one_or_none()
    if stored is not None:
        stored.revoked = True
        await db.commit()
        logger.info("user_logged_out", user_id=stored.user_id)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

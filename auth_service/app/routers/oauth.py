"""
Generic OAuth2 authorization-code flow, manually implemented so every step
is auditable: PKCE everywhere it's supported, a signed+expiring `state`
token for CSRF protection (no server-side session needed), and Apple's
id_token is signature-verified against Apple's published JWKS rather than
trusted blindly.
"""
import base64
import hashlib
import secrets
import uuid

import httpx
import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import OAuthAccount, User
from app.oauth_providers import APPLE_KEYS_URL, PROVIDERS, generate_apple_client_secret
from app.routers.auth import _issue_tokens
from app.schemas import TokenResponse
from app.security import decrypt_value, encrypt_value

settings = get_settings()
logger = structlog.get_logger()
router = APIRouter(prefix="/oauth", tags=["oauth"])

_state_serializer = URLSafeTimedSerializer(settings.secret_key, salt="oauth-state")
_STATE_MAX_AGE_SECONDS = 600  # 10 minutes to complete the provider's login screen


def _make_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _get_provider(provider: str):
    cfg = PROVIDERS.get(provider)
    if cfg is None or not cfg.client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown or unconfigured provider: {provider}")
    return cfg


@router.get("/{provider}/authorize")
async def oauth_authorize(provider: str):
    cfg = _get_provider(provider)
    code_verifier, code_challenge = _make_pkce_pair()

    state = _state_serializer.dumps({"provider": provider, "nonce": secrets.token_urlsafe(16)})

    params = {
        "client_id": cfg.client_id,
        "redirect_uri": f"{settings.base_url}/oauth/{provider}/callback",
        "response_type": "code",
        "scope": cfg.scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if provider == "apple":
        params["response_mode"] = "form_post"

    query = httpx.QueryParams(params)
    response = JSONResponse({"authorization_url": f"{cfg.authorize_url}?{query}"})
    
    response.set_cookie(
        key="pkce_verifier",
        value=encrypt_value(code_verifier),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=_STATE_MAX_AGE_SECONDS,
        domain=settings.cookie_domain,
    )
    logger.info("oauth_flow_started", provider=provider)
    return response


async def _exchange_code(cfg, provider: str, code: str, code_verifier: str) -> dict:
    redirect_uri = f"{settings.base_url}/oauth/{provider}/callback"
    client_secret = generate_apple_client_secret() if provider == "apple" else cfg.client_secret

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cfg.client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(cfg.token_url, data=data, headers={"Accept": "application/json"})

    if resp.status_code != 200:
        logger.warning("oauth_token_exchange_failed", provider=provider, status_code=resp.status_code, response=resp.text)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth token exchange failed.")
    return resp.json()


async def _normalize_identity(cfg, provider: str, token_data: dict) -> tuple[str, str | None, bool]:
    """Returns (provider_user_id, email, email_verified)."""
    if provider == "apple":
        id_token = token_data.get("id_token")
        if not id_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Apple did not return an id_token.")
        jwks_client = jwt.PyJWKClient(APPLE_KEYS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer="https://appleid.apple.com",
        )
        return claims["sub"], claims.get("email"), claims.get("email_verified", False)

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No access token returned by provider.")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(cfg.userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch profile from provider.")
    info = resp.json()

    if provider == "google":
        return info["sub"], info.get("email"), info.get("email_verified", False)
    if provider == "facebook":
        return info["id"], info.get("email"), False
    if provider == "discord":
        return info["id"], info.get("email"), info.get("verified", False)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider.")


async def _get_or_create_user(db: AsyncSession, provider: str, provider_user_id: str, email: str | None, email_verified: bool) -> User:
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider, OAuthAccount.provider_user_id == provider_user_id
        )
    )
    linked = result.scalar_one_or_none()
    if linked is not None:
        result = await db.execute(select(User).where(User.id == linked.user_id))
        user = result.scalar_one()
        logger.info("oauth_user_logged_in", user_id=user.id, provider=provider)
        return user

    # No existing link. If the provider gave us a verified email that
    # matches an existing account, link to it; otherwise create a new user.
    user = None
    if email and email_verified:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if user is not None:
            logger.info("oauth_account_linked", user_id=user.id, provider=provider)

    if user is None:
        base_username = (email.split("@")[0] if email else f"{provider}user")[:24]
        username = f"{base_username}_{secrets.token_hex(3)}"
        user = User(
            username=username,
            email=(email or f"{provider}_{provider_user_id}@noemail.invalid").lower(),
            password_hash=None,
            is_verified=bool(email),
        )
        db.add(user)
        await db.flush()  # get user.id without committing yet
        logger.info("oauth_account_created", user_id=user.id, provider=provider)

    db.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=provider_user_id))
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{provider}/callback", response_model=TokenResponse)
@router.post("/{provider}/callback", response_model=TokenResponse)
async def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    cfg = _get_provider(provider)

    try:
        state_data = _state_serializer.loads(state, max_age=_STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        logger.warning("oauth_state_expired", provider=provider)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth session expired, please try again.")
    except BadSignature:
        logger.warning("oauth_state_invalid", provider=provider)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state.")

    if state_data.get("provider") != provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider/state mismatch.")

    encrypted_verifier = request.cookies.get("pkce_verifier")
    if not encrypted_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing PKCE verifier cookie.")
    
    try:
        code_verifier = decrypt_value(encrypted_verifier)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PKCE verifier cookie.")

    token_data = await _exchange_code(cfg, provider, code, code_verifier)
    provider_user_id, email, email_verified = await _normalize_identity(cfg, provider, token_data)

    user = await _get_or_create_user(db, provider, provider_user_id, email, email_verified)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled.")

    response.delete_cookie("pkce_verifier", domain=settings.cookie_domain)
    return await _issue_tokens(db, user)

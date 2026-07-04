import secrets

from fastapi import Header, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


async def require_api_key(x_api_key: str = Header(...)) -> None:
    """
    Guards the endpoints your own backend calls (checkout creation,
    subscription management, listing). The public ITN webhook does NOT use
    this - PayFast can't send your API key, it's authenticated by its own
    signature + re-validation instead (see app/payfast.py).
    """
    if not secrets.compare_digest(x_api_key, settings.service_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")

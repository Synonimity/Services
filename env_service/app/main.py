import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.dependencies import limiter
from app.routers import admin, secrets, templates

settings = get_settings()
logger = logging.getLogger("env_service")

if settings.is_production and not settings.allowed_client_ips_list:
    logger.warning(
        "ALLOWED_CLIENT_IPS is empty in production - this service has no IP "
        "allowlist on top of its API keys. Strongly consider restricting "
        "this further; see the README's deployment guidance."
    )

app = FastAPI(
    title="KerfSuite Env/Secrets Service",
    version="1.0.0",
    # Disabled regardless of environment - this is a private dev tool, not
    # something to advertise an interactive API explorer for, ever.
    docs_url=None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[settings.base_url.split("//")[-1]])

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def ip_allowlist(request: Request, call_next):
    allowlist = settings.allowed_client_ips_list
    if allowlist and request.url.path != "/healthz":
        client_ip = request.client.host if request.client else ""
        if client_ip not in allowlist:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "IP not allowed."})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.include_router(admin.router)
app.include_router(secrets.router)
app.include_router(templates.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

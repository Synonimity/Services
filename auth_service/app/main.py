import time

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.dependencies import limiter
from app.logging_config import configure_logging
from app.routers import auth, oauth

settings = get_settings()
configure_logging("production" if settings.is_production else "development")
logger = structlog.get_logger()

from app.database import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Application starting up")
    yield
    # Graceful shutdown actions
    logger.info("Application shutting down, disposing database engine")
    await engine.dispose()

app = FastAPI(
    title="KerfSuite Auth Service",
    version="1.0.0",
    # Hide interactive docs in production - don't advertise your auth
    # surface area to the internet.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Force HTTPS and only allow known hosts in production. Behind a reverse
# proxy (nginx/Caddy/Cloudflare) doing TLS termination, these are a second
# line of defense; if you run uvicorn with --ssl-keyfile/--ssl-certfile
# directly instead, they're your first.
if settings.is_production:
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[settings.base_url.split("//")[-1]])

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    # Don't log health checks to keep logs clean
    if request.url.path != "/healthz":
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces or internal details to clients.
    logger.exception("unhandled_exception", method=request.method, path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.include_router(auth.router)
app.include_router(oauth.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

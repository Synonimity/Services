"""
The only endpoint that genuinely needs to be publicly reachable is /itn —
PayFast calls it from outside. Everything else (create_checkout, cancel,
pause, etc.) is called directly in Python from your own route handlers.

Mount in your host app:
    from billing import make_router
    app.include_router(make_router(billing_service, db_dep=get_db))
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .service import BillingService


def make_router(service: BillingService, db_dep, prefix: str = "/billing") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["billing"])

    @router.post("/itn", status_code=status.HTTP_200_OK)
    async def payfast_itn(request: Request, db: AsyncSession = Depends(db_dep)):
        form = dict(await request.form())
        data = {k: str(v) for k, v in form.items()}
        client_ip = request.client.host if request.client else ""
        try:
            return await service.handle_itn(db, data, client_ip)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return router

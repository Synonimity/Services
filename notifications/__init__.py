from .config import NotificationsConfig
from .models import Base, EmailEvent, NotificationLog
from .router import make_router
from .schemas import AlertRequest, NotificationOut, SendEmailRequest, SendEmailResponse
from .service import NotificationsService

__all__ = [
    "NotificationsConfig",
    "NotificationsService",
    "make_router",
    "Base",
    "NotificationLog",
    "EmailEvent",
    "SendEmailRequest",
    "SendEmailResponse",
    "NotificationOut",
    "AlertRequest",
]

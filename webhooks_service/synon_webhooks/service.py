import logging
from typing import Dict, Optional, Callable

from .config import WebhooksConfig
from .store import WebhookStore
from .models import WebhookEvent
from .queue_processor import process_due_events

logger = logging.getLogger("synon_webhooks")

EventHandler = Callable[[WebhookEvent], None]


class WebhookService:
    def __init__(self, config: WebhooksConfig, store: Optional[WebhookStore] = None):
        self.config = config
        self.store = store or WebhookStore(config=config)

    def process_due_events(self, handlers: Dict[str, EventHandler], limit: int = 50) -> Dict[str, int]:
        return process_due_events(self.store, handlers, limit)

    def get_dead_lettered(self, limit: int = 50):
        return self.store.get_dead_lettered(limit)

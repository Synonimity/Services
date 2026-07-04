"""
Drop-in client for the KerfSuite Observability Service. Two pieces:

1. RemoteLogHandler - a standard logging.Handler. Attach it to any
   Python app's root logger (or a specific one) and every log call goes
   to this service too, batched and sent on a background thread so it
   never blocks your app, and never raises into your app if the network
   call fails.

2. install_fastapi_error_reporting() - wires unhandled exceptions in a
   FastAPI app straight to /errors/report, with the request path/method
   as context automatically.

Usage:
    from client.logging_handler import RemoteLogHandler, install_fastapi_error_reporting
    import logging

    handler = RemoteLogHandler(
        base_url="https://obs.kerfsuite.com",
        api_key="...",
        service_name="kerfportal",
        environment="production",
    )
    logging.getLogger().addHandler(handler)

    # FastAPI apps additionally:
    install_fastapi_error_reporting(app, handler)
"""
import atexit
import logging
import queue
import threading
import time
import traceback

import httpx

_LEVEL_MAP = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "critical",
}


class RemoteLogHandler(logging.Handler):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        service_name: str,
        environment: str = "production",
        batch_size: int = 20,
        flush_interval_seconds: float = 5.0,
        also_report_errors: bool = True,
    ):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.service_name = service_name
        self.environment = environment
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self.also_report_errors = also_report_errors

        self._queue: queue.Queue = queue.Queue(maxsize=5000)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        atexit.register(self.close)

    # -- logging.Handler interface -----------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "service_name": self.service_name,
                "environment": self.environment,
                "level": _LEVEL_MAP.get(record.levelno, "info"),
                "message": self.format(record),
                "context": {"logger": record.name, "module": record.module, "line": record.lineno},
            }
            self._queue.put_nowait(entry)

            if self.also_report_errors and record.levelno >= logging.ERROR and record.exc_info:
                self._queue.put_nowait(self._build_error_payload(record))
        except queue.Full:
            pass  # never let logging itself block or crash the app
        except Exception:
            pass

    def _build_error_payload(self, record: logging.LogRecord) -> dict:
        exc_type, exc_value, exc_tb = record.exc_info
        return {
            "_kind": "error",
            "service_name": self.service_name,
            "environment": self.environment,
            "exception_type": exc_type.__name__ if exc_type else "UnknownError",
            "message": str(exc_value) if exc_value else record.getMessage(),
            "stack_trace": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            "context": {"logger": record.name},
        }

    # -- background sender ---------------------------------------------
    def _worker(self) -> None:
        log_batch: list[dict] = []
        last_flush = time.monotonic()

        while not self._stop.is_set():
            timeout = max(0.1, self.flush_interval_seconds - (time.monotonic() - last_flush))
            try:
                item = self._queue.get(timeout=timeout)
                if item.get("_kind") == "error":
                    self._send_error(item)
                else:
                    log_batch.append(item)
            except queue.Empty:
                pass

            if log_batch and (len(log_batch) >= self.batch_size or time.monotonic() - last_flush >= self.flush_interval_seconds):
                self._send_logs(log_batch)
                log_batch = []
                last_flush = time.monotonic()

        if log_batch:
            self._send_logs(log_batch)

    def _send_logs(self, entries: list[dict]) -> None:
        try:
            httpx.post(
                f"{self.base_url}/logs",
                json={"entries": entries},
                headers={"X-API-Key": self.api_key},
                timeout=10,
            )
        except httpx.TransportError:
            pass  # best-effort - never crash the app over a logging hiccup

    def _send_error(self, payload: dict) -> None:
        payload = {k: v for k, v in payload.items() if k != "_kind"}
        try:
            httpx.post(
                f"{self.base_url}/errors/report",
                json=payload,
                headers={"X-API-Key": self.api_key},
                timeout=10,
            )
        except httpx.TransportError:
            pass

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self.flush_interval_seconds + 2)
        super().close()


def install_fastapi_error_reporting(app, handler: RemoteLogHandler) -> None:
    """Reports any unhandled exception in a FastAPI app, with request context attached."""

    @app.middleware("http")
    async def _report_unhandled_exceptions(request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            record = logging.LogRecord(
                name="fastapi.unhandled",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg=f"Unhandled exception on {request.method} {request.url.path}",
                args=(),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            handler.emit(record)
            raise

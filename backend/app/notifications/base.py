import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str | None = None


@runtime_checkable
class Notifier(Protocol):
    def send_email(self, message: EmailMessage) -> None: ...


class ConsoleNotifier:
    """Development notifier: logs emails instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send_email(self, message: EmailMessage) -> None:
        self.sent.append(message)
        logger.info("[email] to=%s subject=%s", message.to, message.subject)


@lru_cache
def get_notifier() -> Notifier:
    settings = get_settings()
    if settings.resend_api_key:
        from app.notifications.resend_notifier import ResendNotifier

        return ResendNotifier(settings.resend_api_key, settings.email_from)
    logger.info("RESEND_API_KEY not set; using ConsoleNotifier")
    return ConsoleNotifier()

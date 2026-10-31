from dataclasses import dataclass, field
from hashlib import sha256

import structlog
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BrowserSnapshot:
    """Safe structured fields and text that is only hashed when logged."""

    fields: dict[str, object]
    text: str = field(default="", repr=False)


class BrowserDiagnostics:
    """Observe a browser without owning its lifecycle or interpreting failures."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def capture(self, script: str) -> BrowserSnapshot:
        """Run a source's snapshot script, keeping text separate from log fields."""
        try:
            fields = self.driver.execute_script(script)
        except WebDriverException as exc:
            # Snapshot failure must not replace the operation's actual error.
            return BrowserSnapshot({"diagnostic_error": type(exc).__name__})
        return BrowserSnapshot(fields, text=fields.pop("text", ""))

    @staticmethod
    def log(
        event: str,
        stage: str,
        snapshot: BrowserSnapshot,
        *,
        message: str = "",
        **details: object,
    ) -> None:
        text = message or snapshot.text
        logger.warning(
            event,
            stage=stage,
            message_length=len(text),
            message_hash=sha256(text.encode()).hexdigest() if text else None,
            **snapshot.fields,
            **details,
        )

from app.configs.selenium import FALLBACK_TO_EXTERNAL_SELENIUM

from ._external import ExternalSelenium
from ._worker import WorkerSelenium
from .schemas import SeleniumGetHtmlArgs


class SeleniumService:
    @staticmethod
    async def get_html(
        args: SeleniumGetHtmlArgs,
        fallback_to_external_selenium: bool | None = None,
    ) -> str:
        if fallback_to_external_selenium is None:
            fallback_to_external_selenium = FALLBACK_TO_EXTERNAL_SELENIUM

        try:
            html = await WorkerSelenium.get_html(args)
        except Exception:
            if fallback_to_external_selenium:
                html = await ExternalSelenium.get_html(
                    args, timeout=args.selenium_wait_timeout_seconds + 60
                )
            else:
                raise
        return html

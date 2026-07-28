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
            # The external worker receives serialized arguments and cannot run a
            # parser's browser callback. Let action-based parsers keep the actual
            # local Selenium error instead of replacing it with a misleading
            # external-worker error.
            if fallback_to_external_selenium and args.make_actions_function is None:
                html = await ExternalSelenium.get_html(
                    args, timeout=args.selenium_wait_timeout_seconds + 60
                )
            else:
                raise
        return html

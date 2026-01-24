from ._worker import WorkerSelenium
from ._external import ExternalSelenium
from .schemas import SeleniumGetHtmlArgs


class SeleniumService:
    @staticmethod
    async def get_html(args: SeleniumGetHtmlArgs) -> str:
        try:
            html = await WorkerSelenium.get_html(args)
        except Exception:
            html = await ExternalSelenium.get_html(
                args, timeout=args.selenium_wait_timeout_seconds + 60
            )
        return html

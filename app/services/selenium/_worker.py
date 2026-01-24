from app.services.selenium.schemas import SeleniumGetHtmlArgs
from app.workers.selenium import get_html as worker_get_html


class WorkerSelenium:
    @staticmethod
    async def get_html(args: SeleniumGetHtmlArgs) -> str:
        return await worker_get_html(args)

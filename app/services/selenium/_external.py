from dataclasses import asdict

from app.configs.env import BROKER_URL
from app.services.broker import BrokerService
from app.services.http import HttpClient
from app.services.selenium.schemas import SeleniumGetHtmlArgs


class ExternalSeleniumError(Exception):
    """External selenium error"""


class ExternalSelenium:
    @classmethod
    async def get_html(
        cls, http: HttpClient, args: SeleniumGetHtmlArgs, timeout: int = 60
    ) -> str:
        if not BROKER_URL:
            raise ExternalSeleniumError("BROKER_URL is not configured")

        broker = BrokerService(BROKER_URL, http)

        data = asdict(args)
        if data.pop("make_actions_function") is not None:
            raise ExternalSeleniumError(
                "make_actions_function is not supported in external selenium"
            )

        url = data.pop("url")
        options = data

        return await broker.put_and_wait_for_result(
            "selenium.get_html", [url, options], timeout=timeout
        )

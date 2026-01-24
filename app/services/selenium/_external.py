from dataclasses import asdict

from app.configs.env import EXTERNAL_SELENIUM_BROKER_URL
from app.services.broker import BrokerService, BrokerError
from app.services.selenium.schemas import SeleniumGetHtmlArgs


class ExternalSeleniumError(Exception):
    """External selenium error"""


class ExternalSelenium:
    @classmethod
    async def get_html(cls, args: SeleniumGetHtmlArgs, timeout: int = 60) -> str:
        if not EXTERNAL_SELENIUM_BROKER_URL:
            raise ExternalSeleniumError(
                "EXTERNAL_SELENIUM_BROKER_URL is not configured"
            )

        broker = BrokerService(EXTERNAL_SELENIUM_BROKER_URL)

        data = asdict(args)
        if "make_actions_function" in data:
            raise ExternalSeleniumError(
                "make_actions_function is not supported in external selenium"
            )

        url = data.pop("url")
        options = data

        return await broker.put_and_wait_for_result(
            "selenium.get_html", [url, options], timeout=timeout
        )

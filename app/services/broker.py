import asyncio
from typing import Any, Sequence

from app.services.http import HttpService, HttpRequestError


class BrokerError(Exception):
    """Broker error"""


class BrokerService:
    def __init__(self, broker_url: str):
        self.broker_url = broker_url.rstrip("/")

    async def put_and_wait_for_result(
        self, func: str, args: Sequence[Any], timeout: int
    ) -> Any:
        task_id = await self.enqueue(func, args)

        start_time = asyncio.get_event_loop().time()
        while True:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise BrokerError("Timeout waiting for result")

            result_data = await self.get_task_data(task_id)
            status = result_data.get("status")

            if status == "completed":
                return result_data.get("result")
            if status == "failed":
                raise BrokerError(f"Task failed: {result_data.get('error')}")

            await asyncio.sleep(1)

    async def get_task_data(self, task_id: str) -> dict:
        try:
            return await HttpService.get_json(
                f"{self.broker_url}/result/{task_id}"
            )
        except HttpRequestError:
            raise BrokerError("Failed to get task data from broker")

    async def enqueue(self, func: str, args: Sequence[Any]) -> str:
        try:
            response = await HttpService.post_json(
                f"{self.broker_url}/enqueue",
                {"function": func, "data": args},
            )
            return response["task_id"]
        except (HttpRequestError, KeyError):
            raise BrokerError("Failed to enqueue task to broker")

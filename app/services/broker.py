import asyncio
from typing import Any, Sequence
from dataclasses import dataclass

from app.services.http import HttpService, HttpRequestError


class BrokerError(Exception):
    """Broker error"""


@dataclass
class Task:
    id: str
    function: str
    args: list[Any]


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
                await self.cancel_task(task_id)
                raise BrokerError("Timeout waiting for result")

            result_data = await self.get_task_data(task_id)
            status = result_data.get("status")

            if status == "completed":
                return result_data.get("result")
            if status == "failed":
                raise BrokerError(f"Task failed: ")

            await asyncio.sleep(1)

    async def cancel_task(self, task_id: str) -> None:
        try:
            await HttpService.delete(f"{self.broker_url}/cancel/{task_id}")
        except HttpRequestError:
            raise BrokerError("Failed to cancel task in broker")

    async def get_task_data(self, task_id: str) -> dict:
        try:
            return await HttpService.get_json(f"{self.broker_url}/result/{task_id}")
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

    async def get_task(self, func: str) -> Task | None:
        try:
            resp = await HttpService.get_json(
                f"{self.broker_url}/get_task?function={func}"
            )

            if not resp.get("task_id"):
                return None

            return Task(
                id=resp["task_id"],
                function=resp.get("function", ""),
                args=resp.get("data", []),
            )
        except HttpRequestError:
            raise BrokerError("Failed to get task from broker")

    async def submit_result(self, task_id: str, result: Any) -> None:
        try:
            await HttpService.post_json(
                f"{self.broker_url}/submit_result",
                {"task_id": task_id, "result": result},
            )
        except HttpRequestError:
            raise BrokerError("Failed to submit result to broker")

    async def submit_error(self, task_id: str, error_message: str) -> None:
        try:
            await HttpService.post_json(
                f"{self.broker_url}/submit_error",
                json={"task_id": task_id, "error_message": error_message},
            )
        except HttpRequestError:
            raise BrokerError("Failed to submit error to broker")

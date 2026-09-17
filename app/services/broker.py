import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPMethod
from typing import Any

from app.services.http import HttpClient, HttpRequestError


class BrokerError(Exception):
    """Broker error"""


@dataclass
class Task:
    id: str
    function: str
    args: list[Any]


class BrokerService:
    def __init__(self, broker_url: str, http: HttpClient):
        self.broker_url = broker_url.rstrip("/")
        self.http = http

    # TODO: should have background task and make batch request
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
                raise BrokerError("Task failed: ")

            await asyncio.sleep(1)

    async def cancel_task(self, task_id: str) -> None:
        try:
            await self.http.request_bytes(
                HTTPMethod.DELETE, f"{self.broker_url}/cancel/{task_id}"
            )
        except HttpRequestError as error:
            raise BrokerError("Failed to cancel task in broker") from error

    async def get_task_data(self, task_id: str) -> dict:
        try:
            response = await self.http.request_json(
                HTTPMethod.GET, f"{self.broker_url}/result/{task_id}"
            )
            return response.data
        except HttpRequestError as error:
            raise BrokerError("Failed to get task data from broker") from error

    async def enqueue(self, func: str, args: Sequence[Any]) -> str:
        try:
            response = await self.http.request_json(
                HTTPMethod.POST,
                f"{self.broker_url}/enqueue",
                json={"function": func, "data": args},
            )
            return response.data["task_id"]
        except (HttpRequestError, KeyError) as error:
            raise BrokerError("Failed to enqueue task to broker") from error

    async def get_task(self, func: str) -> Task | None:
        try:
            resp = (
                await self.http.request_json(
                    HTTPMethod.GET, f"{self.broker_url}/get_task?function={func}"
                )
            ).data

            if not resp.get("task_id"):
                return None

            return Task(
                id=resp["task_id"],
                function=resp.get("function", ""),
                args=resp.get("data", []),
            )
        except HttpRequestError as error:
            raise BrokerError("Failed to get task from broker") from error

    async def submit_result(self, task_id: str, result: Any) -> None:
        try:
            await self.http.request_json(
                HTTPMethod.POST,
                f"{self.broker_url}/submit_result",
                json={"task_id": task_id, "result": result},
            )
        except HttpRequestError as error:
            raise BrokerError("Failed to submit result to broker") from error

    async def submit_error(self, task_id: str, error_message: str) -> None:
        try:
            await self.http.request_json(
                HTTPMethod.POST,
                f"{self.broker_url}/submit_error",
                json={"task_id": task_id, "error_message": error_message},
            )
        except HttpRequestError as error:
            raise BrokerError("Failed to submit error to broker") from error

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from pydantic import ValidationError
from structlog.contextvars import bound_contextvars

from app.serializers.feed import FeedFailure
from app.services.http import HttpRequestError, HttpService

logger = structlog.get_logger(__name__)


class BrokerError(Exception):
    """Broker error"""


class BrokerResultTooLarge(BrokerError):
    """The broker rejected a result with HTTP 413."""


class BrokerNoWorker(BrokerError):
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task has not been claimed: task_id={task_id}")


class BrokerFeedUnavailable(BrokerError):
    def __init__(self, reason: str, retry_at: datetime | None):
        super().__init__(f"Feed unavailable: {reason}")
        self.reason = reason
        self.retry_at = retry_at


@dataclass
class Task:
    id: str
    function: str
    args: list[Any]


class BrokerService:
    def __init__(self, broker_url: str, http: type[HttpService] = HttpService):
        self.broker_url = broker_url.rstrip("/")
        self.http = http
        self._active_tasks: dict[str, str] = {}

    # TODO: should have background task and make batch request
    async def put_and_wait_for_result(
        self, func: str, args: Sequence[Any], timeout: int, task_key: str | None = None
    ) -> Any:
        task_id = self._active_tasks.get(task_key) if task_key else None
        if task_id is None:
            task_id = await self.enqueue(func, args)
            if task_key:
                self._active_tasks[task_key] = task_id

        with bound_contextvars(task_id=task_id):
            logger.info("broker_task_queued")
            start_time = asyncio.get_event_loop().time()
            while True:
                result_data = await self.get_task_data(task_id)
                status = result_data.get("status")

                if status == "completed":
                    if task_key:
                        self._active_tasks.pop(task_key, None)
                    return result_data.get("result")
                if status == "failed":
                    if task_key:
                        self._active_tasks.pop(task_key, None)
                    result = result_data.get("result")
                    failure = None
                    if isinstance(result, str):
                        try:
                            failure = FeedFailure.model_validate_json(result)
                        except ValidationError:
                            pass
                    if failure is not None:
                        raise BrokerFeedUnavailable(failure.reason, failure.retry_at)
                    raise BrokerError(f"Task failed: task_id={task_id}")
                if asyncio.get_event_loop().time() - start_time > timeout:
                    if status == "pending":
                        raise BrokerNoWorker(task_id)
                    await self.cancel_task(task_id)
                    if task_key:
                        self._active_tasks.pop(task_key, None)
                    raise BrokerError(f"Timeout waiting for result: task_id={task_id}")

                await asyncio.sleep(1)

    async def cancel_task(self, task_id: str) -> None:
        try:
            await self.http.delete(f"{self.broker_url}/cancel/{task_id}")
        except HttpRequestError:
            raise BrokerError("Failed to cancel task in broker")

    async def get_task_data(self, task_id: str) -> dict:
        try:
            return await self.http.get_json(f"{self.broker_url}/result/{task_id}")
        except HttpRequestError:
            raise BrokerError("Failed to get task data from broker")

    async def enqueue(self, func: str, args: Sequence[Any]) -> str:
        try:
            response = await self.http.post_json(
                f"{self.broker_url}/enqueue",
                {"function": func, "data": args},
            )
            return response["task_id"]
        except (HttpRequestError, KeyError):
            raise BrokerError("Failed to enqueue task to broker")

    async def get_task(self, func: str) -> Task | None:
        try:
            resp = await self.http.get_json(
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
        payload = {"task_id": task_id, "result": result}
        try:
            await self.http.post_json(
                f"{self.broker_url}/submit_result",
                payload,
            )
        except HttpRequestError as exc:
            logger.warning(
                "broker_result_rejected",
                status=exc.status,
                payload_bytes=len(json.dumps(payload).encode("utf-8")),
            )
            if exc.status == 413:
                raise BrokerResultTooLarge("Broker rejected result size") from exc
            raise BrokerError("Failed to submit result to broker") from exc

    async def submit_error(self, task_id: str, error_message: str) -> None:
        try:
            await self.http.post_json(
                f"{self.broker_url}/submit_error",
                json={"task_id": task_id, "error_message": error_message},
            )
        except HttpRequestError:
            raise BrokerError("Failed to submit error to broker")

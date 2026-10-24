import asyncio
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

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
    def __init__(
        self,
        broker_url: str,
        http: type[HttpService] = HttpService,
        *,
        poll_initial_interval: float = 1,
        poll_max_interval: float = 5,
    ):
        if not 0 < poll_initial_interval <= poll_max_interval:
            raise ValueError("Polling intervals must satisfy 0 < initial <= maximum")
        if not math.isfinite(poll_max_interval):
            raise ValueError("Polling intervals must be finite")
        self.broker_url = broker_url.rstrip("/")
        self.http = http
        self._poll_initial_interval = poll_initial_interval
        self._poll_max_interval = poll_max_interval
        self._active_tasks: dict[str, str] = {}

    async def put_and_wait_for_result(
        self,
        func: str,
        args: Sequence[Any],
        timeout: float,
        task_key: str | None = None,
    ) -> Any:
        task_id = self._active_tasks.get(task_key) if task_key else None
        if task_id is None:
            task_id = await self.enqueue(func, args)
            if task_key:
                self._active_tasks[task_key] = task_id

        with bound_contextvars(task_id=task_id):
            logger.info("broker_task_queued")
            return await self._wait_for_result(task_id, timeout, task_key)

    async def _wait_for_result(
        self, task_id: str, timeout: float, task_key: str | None
    ) -> Any:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        interval = self._poll_initial_interval
        status = "pending"
        while True:
            if loop.time() >= deadline:
                await self._expire_task(task_id, status, task_key)
            try:
                result_data = await self._poll_before_deadline(task_id, deadline)
            except TimeoutError:
                await self._expire_task(task_id, status, task_key)
            next_status = result_data.get("status")
            if not isinstance(next_status, str) or not next_status:
                raise BrokerError(f"Missing task status: task_id={task_id}")
            status = next_status
            if status in {"completed", "failed"}:
                self._forget_task(task_key)
                return self._resolve_result(task_id, status, result_data.get("result"))
            remaining = deadline - loop.time()
            await asyncio.sleep(min(interval, max(0, remaining)))
            interval = min(interval * 2, self._poll_max_interval)

    async def _poll_before_deadline(self, task_id: str, deadline: float) -> dict:
        timeout = asyncio.timeout_at(deadline)
        try:
            async with timeout:
                return await self.get_task_data(task_id)
        except TimeoutError as exc:
            if timeout.expired():
                raise
            raise BrokerError("Failed to get task data from broker") from exc

    async def _expire_task(
        self, task_id: str, status: str, task_key: str | None
    ) -> NoReturn:
        if status == "pending":
            raise BrokerNoWorker(task_id)
        await self.cancel_task(task_id)
        self._forget_task(task_key)
        raise BrokerError(f"Timeout waiting for result: task_id={task_id}")

    def _forget_task(self, task_key: str | None) -> None:
        if task_key:
            self._active_tasks.pop(task_key, None)

    @staticmethod
    def _resolve_result(task_id: str, status: str, result: Any) -> Any:
        if status == "completed":
            return result
        failure = None
        if isinstance(result, str):
            try:
                failure = FeedFailure.model_validate_json(result)
            except ValidationError:
                # Workers may submit a plain error string rather than FeedFailure.
                pass
        if failure is not None:
            raise BrokerFeedUnavailable(failure.reason, failure.retry_at)
        raise BrokerError(f"Task failed: task_id={task_id}")

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

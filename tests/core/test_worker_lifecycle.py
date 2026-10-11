import pytest
from aiohttp import web

from app.core.worker import recover_worker_task
from app.services.broker import BrokerError, BrokerService

pytestmark = pytest.mark.integration


@pytest.fixture
async def broker_server(unused_tcp_port):
    tasks = {}

    async def result(request):
        return web.json_response(tasks[request.match_info["task_id"]])

    async def submit_error(request):
        data = await request.json()
        task = tasks[data["task_id"]]
        if task.get("reject_error"):
            raise web.HTTPServiceUnavailable()
        task.update(status="failed", result=data["error_message"])
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/result/{task_id}", result)
    app.router.add_post("/submit_error", submit_error)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        yield BrokerService(f"http://127.0.0.1:{unused_tcp_port}"), tasks
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("status", ["processing", "completed", "failed"])
async def test_restart_closes_only_an_unfinished_task(broker_server, tmp_path, status):
    broker, tasks = broker_server
    tasks["interrupted"] = {"status": status, "result": "original"}
    task_path = tmp_path / "active-task"
    task_path.write_text("interrupted")

    await recover_worker_task(broker, task_path)

    expected = (
        {"status": "failed", "result": "worker_interrupted"}
        if status == "processing"
        else {"status": status, "result": "original"}
    )
    assert await broker.get_task_data("interrupted") == expected
    assert not task_path.exists()


async def test_restart_retains_task_until_broker_accepts_error(broker_server, tmp_path):
    broker, tasks = broker_server
    tasks["interrupted"] = {"status": "processing", "reject_error": True}
    task_path = tmp_path / "active-task"
    task_path.write_text("interrupted")

    with pytest.raises(BrokerError):
        await recover_worker_task(broker, task_path)
    assert task_path.read_text() == "interrupted"
    assert (await broker.get_task_data("interrupted"))["status"] == "processing"

    tasks["interrupted"]["reject_error"] = False
    await recover_worker_task(broker, task_path)
    assert (await broker.get_task_data("interrupted"))["status"] == "failed"
    assert not task_path.exists()

from app.services.http import HttpService
from . import worker


@worker
async def get_html(url: str) -> bytes:
    return await HttpService.get(url)

from app.services.http import HttpService


async def get_html(url: str) -> bytes:
    return await HttpService.get(url)

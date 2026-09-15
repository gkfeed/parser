from app.services.http import HttpClient


async def get_html(http: HttpClient, url: str) -> bytes:
    return (await http.request_bytes("GET", url)).data

from app.services.http import HttpService


class CatboxUploader:
    host_url = "https://catbox.moe/user/api.php"

    @classmethod
    async def upload_with_url(cls, url: str) -> str:
        params = {
            "reqtype": "urlupload",
            "userhash": "",
            "url": url,
        }
        response = await HttpService.post(cls.host_url, body=params)
        return response.decode("utf-8")

from app.services.http import HttpService


class CatboxUploadError(Exception):
    """Catbox did not return an uploaded file URL."""


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
        uploaded_url = response.decode("utf-8").strip()
        if not uploaded_url.startswith("https://files.catbox.moe/"):
            raise CatboxUploadError(uploaded_url)
        return uploaded_url

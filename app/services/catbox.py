from http import HTTPMethod

from app.services.http import HttpClient


class CatboxUploadError(Exception):
    """Catbox did not return an uploaded file URL."""


class CatboxUploader:
    host_url = "https://catbox.moe/user/api.php"

    @classmethod
    async def upload_with_url(cls, http: HttpClient, url: str) -> str:
        params = {
            "reqtype": "urlupload",
            "userhash": "",
            "url": url,
        }
        response = await http.request_bytes(HTTPMethod.POST, cls.host_url, data=params)
        uploaded_url = response.data.decode("utf-8").strip()
        if not uploaded_url.startswith("https://files.catbox.moe/"):
            raise CatboxUploadError(uploaded_url)
        return uploaded_url

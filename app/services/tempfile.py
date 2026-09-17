from http import HTTPMethod

from app.services.http import HttpClient


class TempFileUploadError(Exception):
    """TempFile did not return an uploaded file URL."""


class TempFileUploader:
    host_url = "https://tempfile.org/api/upload/url"
    download_url_template = "https://tempfile.org/{file_id}/download"

    @classmethod
    async def upload_with_url(cls, http: HttpClient, url: str) -> str:
        response = await http.request_json(
            HTTPMethod.POST,
            cls.host_url,
            json={
                "url": url,
                "expiryHours": 48,
            },
        )
        file = response.data.get("file")
        file_id = file.get("id") if isinstance(file, dict) else None
        if response.data.get("success") is not True or not isinstance(file_id, str):
            raise TempFileUploadError(str(response.data.get("error", response.data)))
        return cls.download_url_template.format(file_id=file_id)

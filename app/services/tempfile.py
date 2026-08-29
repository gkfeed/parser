from app.services.http import HttpService


class TempFileUploadError(Exception):
    """TempFile did not return an uploaded file URL."""


class TempFileUploader:
    host_url = "https://tempfile.org/api/upload/url"
    download_url_template = "https://tempfile.org/{file_id}/download"

    @classmethod
    async def upload_with_url(cls, url: str) -> str:
        response = await HttpService.post_json(
            cls.host_url,
            {
                "url": url,
                "expiryHours": 48,
            },
        )
        file = response.get("file")
        file_id = file.get("id") if isinstance(file, dict) else None
        if response.get("success") is not True or not isinstance(file_id, str):
            raise TempFileUploadError(str(response.get("error", response)))
        return cls.download_url_template.format(file_id=file_id)

from pathlib import Path

import aiohttp
import pytest

from app.services.catbox import CatboxUploader
from app.services.http import HttpService


@pytest.mark.integration
async def test_catbox_file_upload(tmp_path: Path):
    file_path = tmp_path / "catbox-live-test.txt"
    file_path.write_text("Catbox live upload test\n", encoding="utf-8")

    form = aiohttp.FormData()
    form.add_field("reqtype", "fileupload")
    form.add_field("userhash", "")

    with file_path.open("rb") as file:
        form.add_field(
            "fileToUpload",
            file,
            filename=file_path.name,
            content_type="text/plain",
        )

        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.post(
                CatboxUploader.host_url,
                data=form,
                headers=HttpService.headers,
            ) as response,
        ):
            response_body = (await response.content.read()).decode().strip()

    assert response.status == 200, response_body
    assert response_body.startswith("https://files.catbox.moe/"), response_body

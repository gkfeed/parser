from typing import Optional
from dateutil.parser import parse

import aiohttp

from app.settings import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from .types import Stream
from .auth import TwitchAuthenticator


class Twitch:
    __client_id = TWITCH_CLIENT_ID
    __client_secret = TWITCH_CLIENT_SECRET
    __base_url = 'https://api.twitch.tv/helix/streams?user_login='

    @classmethod
    def __get_headers(cls, client_id: str, access_token: str) -> dict:
        return {
            'Client-ID': client_id,
            'Authorization': 'Bearer ' + access_token
        }

    @classmethod
    async def get_stream(cls, streamer_name: str) -> Optional[Stream]:
        access_token = await TwitchAuthenticator.get_access_token(
            cls.__client_id, cls.__client_secret)
        headers = cls.__get_headers(cls.__client_id, access_token)

        url = cls.__base_url + streamer_name
        response = await cls.get_html(url, headers)

        if 'data' not in response:
            return None

        stream_data = response['data']

        if len(stream_data) != 1:
            return None

        current_stream_data = response['data'][0]

        return Stream(
            channel_name=streamer_name,
            title=current_stream_data['title'],
            started_at=parse(current_stream_data['started_at'])
        )

    @classmethod
    async def get_html(cls, url: str, headers: dict) -> dict:
        async with aiohttp.ClientSession(conn_timeout=None) as session:
            async with session.get(url, headers=headers) as response:
                return await response.json()

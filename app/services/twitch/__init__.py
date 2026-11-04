import json

from dateutil.parser import parse

from app.configs.env import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpRequestError, HttpService

from .auth import TwitchAuthenticator
from .exceptions import TwitchAuthenticationFailed, TwitchResponseError
from .types import Stream


class Twitch:
    __client_id = TWITCH_CLIENT_ID
    __client_secret = TWITCH_CLIENT_SECRET
    __base_url = "https://api.twitch.tv/helix/streams?user_login="

    @classmethod
    def __get_headers(cls, client_id: str, access_token: str) -> dict:
        return {"Client-ID": client_id, "Authorization": "Bearer " + access_token}

    @classmethod
    async def get_stream(cls, streamer_name: str) -> Stream | None:
        try:
            access_token = await TwitchAuthenticator.get_access_token(
                cls.__client_id, cls.__client_secret
            )
        except TwitchAuthenticationFailed as exc:
            raise FeedUnavailable(
                f"https://twitch.tv/{streamer_name}", "twitch_authentication_failed"
            ) from exc
        headers = cls.__get_headers(cls.__client_id, access_token)

        url = cls.__base_url + streamer_name
        response = await cls.get_html(url, headers)

        stream_data = response.get("data")
        if not isinstance(stream_data, list):
            raise TwitchResponseError(
                "Invalid Twitch API response: data must be a list"
            )
        if not stream_data:
            return None
        if len(stream_data) != 1:
            raise TwitchResponseError(
                "Invalid Twitch API response: expected at most one stream"
            )

        current_stream_data = stream_data[0]
        if not isinstance(current_stream_data, dict):
            raise TwitchResponseError(
                "Invalid Twitch API response: stream must be an object"
            )
        title = current_stream_data.get("title")
        started_at = current_stream_data.get("started_at")
        if not isinstance(title, str):
            raise TwitchResponseError(
                "Invalid Twitch API response: title must be a string"
            )
        if not isinstance(started_at, str):
            raise TwitchResponseError(
                "Invalid Twitch API response: started_at must be a string"
            )
        try:
            stream_started_at = parse(started_at)
        except (ValueError, OverflowError) as exc:
            raise TwitchResponseError(
                "Invalid Twitch API response: invalid started_at"
            ) from exc

        return Stream(
            channel_name=streamer_name,
            title=title,
            started_at=stream_started_at,
        )

    @classmethod
    async def get_html(cls, url: str, headers: dict) -> dict:
        try:
            response = await HttpService.get_response(url, headers=headers)
        except HttpRequestError as exc:
            raise FeedUnavailable(url, "twitch_request_failed") from exc
        if response.status != 200:
            raise FeedUnavailable(url, f"twitch_http_{response.status}")
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TwitchResponseError(
                "Invalid Twitch API response: invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise TwitchResponseError("Invalid Twitch API response: expected an object")
        return payload

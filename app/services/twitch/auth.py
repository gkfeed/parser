from app.services.http import HttpClient, HttpRequestError

from .exceptions import TwitchAuthenticationFailed


class TwitchAuthenticator:
    __base_url = "https://id.twitch.tv/oauth2/token"

    @classmethod
    async def get_access_token(
        cls, http: HttpClient, client_id: str, client_secret: str
    ) -> str:
        body = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }

        try:
            response = await http.request_json("POST", cls.__base_url, data=body)
            return response.data["access_token"]
        except HttpRequestError as error:
            raise TwitchAuthenticationFailed from error

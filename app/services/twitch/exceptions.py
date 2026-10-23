class TwitchAuthenticationFailed(Exception):
    """Failed twitch auth"""


class TwitchResponseError(ValueError):
    """Twitch returned malformed response data."""

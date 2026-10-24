import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Self

import aiohttp


@dataclass(frozen=True)
class _SessionState:
    session: aiohttp.ClientSession
    loop: asyncio.AbstractEventLoop


_session: ContextVar[_SessionState | None] = ContextVar("http_session", default=None)


class HttpSessionScope:
    """Share a bounded, stateless HTTP pool within one event-loop scope."""

    def __init__(self, connection_limit: int = 100, per_host_limit: int = 10):
        if connection_limit < 1 or per_host_limit < 1:
            raise ValueError("HTTP connection limits must be positive")
        self._connection_limit = connection_limit
        self._per_host_limit = per_host_limit
        self._owned_session: aiohttp.ClientSession | None = None
        self._token: Token[_SessionState | None] | None = None
        self._entered = False

    async def __aenter__(self) -> Self:
        if self._entered:
            raise RuntimeError("HTTP scope is already entered")
        current = _session.get()
        if current is not None:
            self._validate_session(current)
        else:
            self._owned_session = self._new_session(
                self._connection_limit, self._per_host_limit
            )
            self._token = _session.set(
                _SessionState(self._owned_session, asyncio.get_running_loop())
            )
        self._entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self._entered = False
        if self._token is None:
            return
        _session.reset(self._token)
        self._token = None
        session = self._owned_session
        self._owned_session = None
        if session is not None:
            await session.close()

    @staticmethod
    def _new_session(
        connection_limit: int, per_host_limit: int
    ) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=connection_limit, limit_per_host=per_host_limit
            ),
            cookie_jar=aiohttp.DummyCookieJar(),
        )

    @staticmethod
    def _validate_session(state: _SessionState) -> None:
        if state.session.closed:
            raise RuntimeError("HTTP scope has already closed")
        if state.loop is not asyncio.get_running_loop():
            raise RuntimeError("HTTP scope belongs to a different event loop")

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncGenerator[aiohttp.ClientSession]:
        current = _session.get()
        if current is not None:
            cls._validate_session(current)
            yield current.session
            return
        async with cls._new_session(100, 10) as temporary:
            yield temporary

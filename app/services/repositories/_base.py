from sqlalchemy.ext.asyncio import AsyncSession

from app.configs import Data
from app.services.container import Container


class BaseRepository:
    @classmethod
    def _session_factory(cls) -> AsyncSession:
        data: Data = Container.get_data()
        if data is None:
            raise ValueError("Container data is not initialized")

        if not hasattr(data, "db_session"):
            raise ValueError("Container data does not contain 'db_session'")

        return data.db_session()

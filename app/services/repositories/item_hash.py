from app.models.item_hash import ItemHash


class ItemsHashRepository:
    @classmethod
    async def contains(cls, hash: str) -> bool:
        return await ItemHash.filter(hash=hash).exists()

    @classmethod
    async def save(cls, hash: str):
        await ItemHash.create(hash=hash)

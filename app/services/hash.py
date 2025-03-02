import hashlib
import json

from app.serializers.feed import Item


class HashService:
    @staticmethod
    def hash_item(item: Item) -> str:
        model_dict = item.json()
        data_str = json.dumps(model_dict, sort_keys=True)
        data_str = item.title + item.text
        hash_value = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        return hash_value

    @staticmethod
    def hash_str(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

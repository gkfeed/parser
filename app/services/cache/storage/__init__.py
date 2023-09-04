from typing import TypeVar

from ._base import BaseStorage as _BaseStorage


TStorage = TypeVar("TStorage", bound=_BaseStorage)

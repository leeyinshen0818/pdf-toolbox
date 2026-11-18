from __future__ import annotations

from collections import OrderedDict
from typing import Generic, Hashable, Iterator, TypeVar


K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class LruCache(Generic[K, V]):
    """Small least-recently-used cache with a fixed maximum number of entries."""

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1.")
        self.max_entries = max_entries
        self._items: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K, default: V | None = None) -> V | None:
        if key not in self._items:
            return default
        self._items.move_to_end(key)
        return self._items[key]

    def __setitem__(self, key: K, value: V) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def __getitem__(self, key: K) -> V:
        value = self._items[key]
        self._items.move_to_end(key)
        return value

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[K]:
        return iter(self._items)

    def values(self):
        return self._items.values()

    def pop(self, key: K, default: V | None = None) -> V | None:
        return self._items.pop(key, default)

    def clear(self) -> None:
        self._items.clear()

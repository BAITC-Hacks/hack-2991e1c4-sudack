"""Small process-local response cache keyed by the complete request context."""

from collections import OrderedDict
from hashlib import sha1

from app.models import RecommendRequest, RecommendResponse


class ResponseCache:
    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._items: OrderedDict[str, RecommendResponse] = OrderedDict()

    @staticmethod
    def key(request: RecommendRequest) -> str:
        data = request.model_dump_json(exclude_none=True)
        return sha1(data.encode("utf-8")).hexdigest()

    def get(self, key: str) -> RecommendResponse | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
            return value.model_copy(deep=True)
        return None

    def set(self, key: str, value: RecommendResponse) -> None:
        if self._capacity <= 0:
            return
        self._items[key] = value.model_copy(deep=True)
        self._items.move_to_end(key)
        if len(self._items) > self._capacity:
            self._items.popitem(last=False)

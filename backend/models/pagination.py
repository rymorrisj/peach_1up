from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope for paginated list responses.

    ``total`` is the number of rows matching the *current filtered* query
    (after every WHERE clause, before limit/offset) — i.e. how many rows the
    caller is paging through, not the whole-table count. ``limit``/``offset``
    echo the effective values used so the client can compute page count and
    the next offset without guessing.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

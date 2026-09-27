from contextlib import contextmanager
from collections.abc import Iterator
from uuid import uuid4

from structlog.contextvars import bound_contextvars, get_contextvars


@contextmanager
def request_log_context(*, new: bool = False) -> Iterator[None]:
    request_id = None if new else get_contextvars().get("request_id")
    with bound_contextvars(request_id=request_id or uuid4().hex):
        yield

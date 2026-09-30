from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any
from .pii import scrub_value

try:
    from langfuse import Langfuse, get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
    # Configure the shared SDK client before decorators create observations.
    # This also sanitizes SDK-generated error status messages.
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        _configured_client = Langfuse(mask=lambda *, data, **kwargs: scrub_value(data))
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )

"""Decorators for easy tracing of sync and async functions."""

from __future__ import annotations

import functools
import inspect
import typing
from typing import Callable, TypeVar, ParamSpec

from .tracer import get_tracer
from .span import SpanStatus

P = ParamSpec("P")
T = TypeVar("T")


def traced(
    name: str | None = None,
    attributes: dict | None = None,
):
    """
    Decorator to trace a synchronous function.

    Usage:
        @traced("process_image")
        def process_image(url: str) -> bytes:
            ...

        @traced()  # uses function name
        async def fetch_data(query: str):
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs):
            tracer = get_tracer()
            trace = tracer.current_trace()
            span_name = name or func.__name__
            span = tracer.start_span(span_name, attributes=dict(attributes or {}), trace=trace)
            try:
                result = func(*args, **kwargs)
                tracer.end_span(span, SpanStatus.OK)
                return result
            except Exception as e:
                tracer.end_span(span, SpanStatus.ERROR, error=str(e))
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs):
            tracer = get_tracer()
            trace = tracer.current_trace()
            span_name = name or func.__name__
            span = tracer.start_span(span_name, attributes=dict(attributes or {}), trace=trace)
            try:
                result = await func(*args, **kwargs)
                tracer.end_span(span, SpanStatus.OK)
                return result
            except Exception as e:
                tracer.end_span(span, SpanStatus.ERROR, error=str(e))
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# Alias
trace_async = traced


class SpanContext:
    """
    Context manager for manual span creation.

    Usage:
        tracer = get_tracer()
        with SpanContext(tracer, "my_operation", {"key": "value"}) as span:
            # do work
            span.set_attribute("step", "done")
    """

    def __init__(
        self,
        tracer,
        name: str,
        attributes: dict | None = None,
    ):
        self._tracer = tracer
        self._name = name
        self._attributes = attributes
        self._span = None

    def __enter__(self):
        self._span = self._tracer.start_span(self._name, self._attributes)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span is None:
            return
        if exc_type is not None:
            self._tracer.end_span(self._span, SpanStatus.ERROR, error=str(exc_val))
        else:
            self._tracer.end_span(self._span, SpanStatus.OK)
        return False  # don't suppress exceptions

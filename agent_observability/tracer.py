"""Core tracer implementation."""

from __future__ import annotations

import threading
import contextvars
import time
from typing import Any, Callable, TypeVar
from collections import defaultdict

from .span import Span, Trace, SpanStatus, TokenUsage

# Thread-safe context for current span
_current_span: contextvars.ContextVar["Span | None"] = contextvars.ContextVar(
    "current_span", default=None
)
_current_trace: contextvars.ContextVar["Trace | None"] = contextvars.ContextVar(
    "current_trace", default=None
)

# Global tracer instance
_tracer: "AgentTracer | None" = None
_tracer_lock = threading.Lock()


class AgentTracer:
    """
    The main tracer. Manages active spans, token usage, and exports traces.

    Usage:
        tracer = AgentTracer()
        tracer.start_trace("my_agent_run")
        with tracer.start_span("llm_call"):
            result = await llm.chat("hello")
        tracer.set_token_usage("gpt-4o", input=100, output=200)
        trace = tracer.end_trace()

        # Or use the global tracer:
        from agent_observability import get_tracer
        get_tracer().start_trace("run1")
    """

    def __init__(self):
        self._exports: list["TraceExporter"] = []
        self._model_prices: dict[str, tuple[float, float]] = {}  # model -> (input_per_1k, output_per_1k)

    # ── Trace lifecycle ────────────────────────────────────────────────────────

    def start_trace(self, name: str = "agent_run", metadata: dict[str, Any] | None = None) -> Trace:
        """Begin a new trace."""
        trace = Trace(name)
        if metadata:
            for k, v in metadata.items():
                trace.set_metadata(k, v)
        _current_trace.set(trace)
        return trace

    def end_trace(self, trace: Trace | None = None) -> Trace:
        """Finalize and export a trace."""
        if trace is None:
            trace = _current_trace.get()
        if trace is None:
            raise ValueError("No active trace to end")

        # Close any open spans
        for span in trace.get_all_spans():
            if span.start_time is not None and span.end_time is None:
                span.end()

        _current_trace.set(None)
        _current_span.set(None)

        # Export to all exporters
        trace_dict = trace.to_dict()
        for exporter in self._exports:
            try:
                exporter.export(trace_dict)
            except Exception as e:
                print(f"[agent-observability] Exporter {exporter} failed: {e}")

        return trace

    # ── Span management ────────────────────────────────────────────────────────

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        trace: Trace | None = None,
    ) -> Span:
        """Start a new span, optionally as a child of the current span."""
        trace = trace or _current_trace.get()
        parent = _current_span.get()

        span = Span(
            name=name,
            trace_id=trace.id if trace else None,
            parent_id=parent.id if parent else None,
            attributes=attributes,
        )
        span.start()

        if parent:
            parent.children.append(span)
        elif trace:
            trace.add_root_span(span)

        token = _current_span.set(span)
        span._token = token  # type: ignore[attr-defined]

        return span

    def end_span(self, span: Span | None = None, status: SpanStatus = SpanStatus.OK, error: str | None = None):
        """End a span."""
        if span is None:
            span = _current_span.get()
        if span is None:
            return

        span.end(status=status, error=error)

        # Restore context to parent
        _current_span.reset(span._token)  # type: ignore[attr-defined]

    def current_span(self) -> Span | None:
        """Get the currently active span."""
        return _current_span.get()

    def current_trace(self) -> Trace | None:
        """Get the currently active trace."""
        return _current_trace.get()

    # ── Token tracking ─────────────────────────────────────────────────────────

    def set_token_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        span_id: str | None = None,
    ):
        """Record LLM token usage for the current trace."""
        trace = _current_trace.get()
        if trace is None:
            return

        # Auto-calculate cost if price is known
        cost = None
        if model in self._model_prices:
            in_price, out_price = self._model_prices[model]
            cost = (input_tokens / 1000 * in_price) + (output_tokens / 1000 * out_price)

        trace.token_usage.record(model, input_tokens, output_tokens, cost, span_id)

    def set_model_price(self, model: str, input_per_1k: float, output_per_1k: float):
        """Set pricing for a model (dollars per 1M tokens)."""
        self._model_prices[model] = (input_per_1k, output_per_1k)

    # ── Exporters ─────────────────────────────────────────────────────────────

    def add_exporter(self, exporter: "TraceExporter"):
        self._exports.append(exporter)

    def remove_exporter(self, exporter: "TraceExporter"):
        if exporter in self._exports:
            self._exports.remove(exporter)

    def clear_exporters(self):
        self._exports.clear()

    # ── Global tracer access ───────────────────────────────────────────────────

    @staticmethod
    def get_instance() -> "AgentTracer":
        global _tracer
        with _tracer_lock:
            if _tracer is None:
                _tracer = AgentTracer()
            return _tracer


def get_tracer() -> AgentTracer:
    """Get the global tracer instance."""
    return AgentTracer.get_instance()


def set_tracer(t: AgentTracer):
    """Replace the global tracer instance."""
    global _tracer
    with _tracer_lock:
        _tracer = t


# ── Protocol for exporters ────────────────────────────────────────────────────


class TraceExporter:
    """Base class for trace exporters."""

    def export(self, trace: dict) -> None:
        raise NotImplementedError


# ── Global tracer shortcut ────────────────────────────────────────────────────


# Convenience: expose the global tracer's methods
def start_trace(name: str = "agent_run", metadata: dict[str, Any] | None = None) -> Trace:
    return get_tracer().start_trace(name, metadata)


def end_trace(trace: Trace | None = None) -> Trace:
    return get_tracer().end_trace(trace)


def start_span(name: str, attributes: dict[str, Any] | None = None) -> Span:
    return get_tracer().start_span(name, attributes)


def end_span(span: Span | None = None, status: SpanStatus = SpanStatus.OK, error: str | None = None):
    get_tracer().end_span(span, status, error)


def current_span() -> Span | None:
    return get_tracer().current_span()


def current_trace() -> Trace | None:
    return get_tracer().current_trace()


def set_token_usage(model: str, input_tokens: int, output_tokens: int):
    get_tracer().set_token_usage(model, input_tokens, output_tokens)

"""Span and Trace data models."""

from __future__ import annotations
import time
import uuid
from enum import Enum
from typing import Any


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class Span:
    """A single unit of work in an agent trace."""

    def __init__(
        self,
        name: str,
        trace_id: str | None = None,
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        self.id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id or uuid.uuid4().hex
        self.parent_id = parent_id
        self.name = name
        self.attributes: dict[str, Any] = attributes or {}
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.status: SpanStatus = SpanStatus.UNSET
        self.error_message: str | None = None
        self.children: list[Span] = []

    def start(self) -> "Span":
        self.start_time = time.perf_counter()
        return self

    def end(self, status: SpanStatus = SpanStatus.OK, error: str | None = None) -> "Span":
        self.end_time = time.perf_counter()
        self.status = status
        if error:
            self.error_message = error
            self.status = SpanStatus.ERROR
        return self

    @property
    def duration_ms(self) -> float | None:
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> "Span":
        """Add a named event (for debugging sub-steps)."""
        if not hasattr(self, "_events"):
            self._events = []
        self._events.append({"name": name, "attributes": attributes or {}})
        return self

    def to_dict(self) -> dict:
        return {
            "span_id": self.id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "attributes": self.attributes,
            "start_time_ms": int(self.start_time * 1000) if self.start_time else None,
            "duration_ms": round(self.duration_ms, 3) if self.duration_ms else None,
            "status": self.status.value,
            "error": self.error_message,
            "events": getattr(self, "_events", []),
        }


class TokenUsage:
    """Records LLM token consumption for a trace."""

    def __init__(self):
        self.records: list[dict] = []

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float | None = None,
        span_id: str | None = None,
    ):
        self.records.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": cost,
            "span_id": span_id,
        })

    @property
    def total_input_tokens(self) -> int:
        return sum(r["input_tokens"] for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r["output_tokens"] for r in self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r["total_tokens"] for r in self.records)

    @property
    def total_cost(self) -> float | None:
        costs = [r["cost_usd"] for r in self.records if r["cost_usd"] is not None]
        return sum(costs) if costs else None

    def to_dict(self) -> dict:
        return {
            "records": self.records,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost,
        }


class Trace:
    """The complete execution trace for one agent run."""

    def __init__(self, name: str = "agent_run"):
        self.id = uuid.uuid4().hex
        self.name = name
        self.root_spans: list[Span] = []
        self.token_usage = TokenUsage()
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.metadata: dict[str, Any] = {}

    def add_root_span(self, span: Span):
        self.root_spans.append(span)

    def set_metadata(self, key: str, value: Any):
        self.metadata[key] = value

    @property
    def duration_ms(self) -> float | None:
        if not self.root_spans:
            return None
        starts = [s.start_time for s in self.root_spans if s.start_time is not None]
        ends = [s.end_time for s in self.root_spans if s.end_time is not None]
        if not starts or not ends:
            return None
        return (max(ends) - min(starts)) * 1000

    def get_all_spans(self) -> list[Span]:
        """Flatten all spans (root + children recursively)."""
        result = []
        for span in self.root_spans:
            result.append(span)
            result.extend(self._collect_children(span))
        return result

    def _collect_children(self, span: Span) -> list[Span]:
        result = []
        for child in span.children:
            result.append(child)
            result.extend(self._collect_children(child))
        return result

    def to_dict(self) -> dict:
        return {
            "trace_id": self.id,
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3) if self.duration_ms else None,
            "metadata": self.metadata,
            "token_usage": self.token_usage.to_dict(),
            "spans": [s.to_dict() for s in self.get_all_spans()],
        }

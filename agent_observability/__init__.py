"""
agent-observability - Lightweight observability for AI agents.
"""

from .tracer import AgentTracer, get_tracer, set_tracer
from .span import Span, Trace, SpanStatus, TokenUsage
from .decorators import traced, trace_async

__version__ = "0.1.0"
__all__ = [
    "AgentTracer",
    "get_tracer",
    "set_tracer",
    "Span",
    "Trace",
    "SpanStatus",
    "TokenUsage",
    "traced",
    "trace_async",
]

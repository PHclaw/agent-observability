"""Console exporter - pretty-prints traces for development debugging."""

from __future__ import annotations

import sys
import json
from typing import Any


class ConsoleExporter:
    """
    Pretty-prints traces to stdout/stderr.

    Features:
    - Colored output (SPAN boundaries)
    - Duration formatting
    - Token usage summary
    - Error highlighting
    - Collapsible span tree

    Usage:
        tracer = AgentTracer()
        tracer.add_exporter(ConsoleExporter())
    """

    INDENT = "  "
    OK_COLOR = "\033[92m"   # green
    ERR_COLOR = "\033[91m"  # red
    DIM_COLOR = "\033[2m"   # grey
    BOLD_COLOR = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, stream: Any | None = None, color: bool = True):
        self.stream = stream or sys.stdout
        self.color = color

    def _p(self, *args, **kwargs):
        kwargs["file"] = self.stream
        kwargs["flush"] = True
        print(*args, **kwargs)

    def _span_tree(self, spans: list[dict], trace_start_ms: int | None = None, depth: int = 0):
        """Render a flat list of spans as a tree (by parent_id)."""
        # Build lookup
        by_id = {s["span_id"]: s for s in spans}
        roots = [s for s in spans if s["parent_id"] is None]

        def render(span: dict, depth: int):
            indent = self.INDENT * depth
            dur = span.get("duration_ms")
            dur_str = f"{dur:.1f}ms" if dur is not None else "?"
            status = span.get("status", "unset")
            err = span.get("error")

            if status == "error":
                flag = f"{self._c(self.ERR_COLOR)}✗{self._c()}"
            elif status == "ok":
                flag = f"{self._c(self.OK_COLOR)}✓{self._c()}"
            else:
                flag = "○"

            name = span.get("name", "?")
            attrs = span.get("attributes", {})
            attr_str = ""
            if attrs:
                short_attrs = {k: v for k, v in attrs.items() if k not in ("duration_ms", "status")}
                if short_attrs:
                    attr_preview = ", ".join(f"{k}={self._truncate(repr(v), 40)}" for k, v in short_attrs.items())
                    attr_str = f" {self._c(self.DIM_COLOR)}{attr_preview}{self._c()}"

            self._p(f"{indent}{flag} {self._c(self.BOLD_COLOR)}{name}{self._c()} [{dur_str}]{attr_str}")

            if err:
                self._p(f"{indent}  {self._c(self.ERR_COLOR)}error: {err}{self._c()}")

            # Render children
            children = [s for s in spans if s.get("parent_id") == span["span_id"]]
            for child in children:
                render(child, depth + 1)

        for root in roots:
            render(root, depth)

    def _truncate(self, s: str, max_len: int) -> str:
        if len(s) <= max_len:
            return s
        return s[:max_len - 2] + ".."

    def _c(self, code: str = "") -> str:
        return code if self.color else ""

    def export(self, trace: dict):
        self._p(f"\n{self._c(self.BOLD_COLOR)}══ {trace.get('name', 'agent_run')} ══{self._c()}")
        trace_id = trace.get("trace_id", "?")
        dur = trace.get("duration_ms")
        dur_str = f"{dur:.1f}ms" if dur is not None else "N/A"
        self._p(f"  trace_id={trace_id[:8]}...  duration={dur_str}")

        # Token usage
        tu = trace.get("token_usage", {})
        if tu.get("records"):
            self._p(f"  {self._c(self.BOLD_COLOR)}Token Usage:{self._c()}")
            for rec in tu["records"]:
                cost_str = f" (${rec['cost_usd']:.4f})" if rec.get("cost_usd") else ""
                self._p(
                    f"    {rec['model']}: "
                    f"in={rec['input_tokens']} out={rec['output_tokens']} "
                    f"total={rec['total_tokens']}{cost_str}"
                )
            total_cost = tu.get("total_cost_usd")
            if total_cost is not None:
                self._p(f"    {self._c(self.BOLD_COLOR)}TOTAL{self._c()}: "
                        f"{tu['total_tokens']} tokens  ${total_cost:.4f}")

        # Spans
        spans = trace.get("spans", [])
        if spans:
            self._p(f"  {self._c(self.BOLD_COLOR)}Spans ({len(spans)}):{self._c()}")
            self._span_tree(spans)

        self._p()

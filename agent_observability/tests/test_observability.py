"""Tests for agent-observability."""

import pytest
import asyncio
import time
import json
import tempfile
from pathlib import Path

from agent_observability import (
    AgentTracer,
    get_tracer,
    set_tracer,
    traced,
    Span,
    Trace,
    SpanStatus,
    TokenUsage,
)
from agent_observability.exporters import ConsoleExporter, JsonFileExporter


@pytest.fixture(autouse=True)
def fresh_tracer():
    """Each test gets a fresh tracer."""
    tracer = AgentTracer()
    set_tracer(tracer)
    yield tracer
    tracer.clear_exporters()


class TestSpan:
    def test_span_lifecycle(self):
        span = Span("test_span")
        assert span.id is not None
        assert span.name == "test_span"
        assert span.status == SpanStatus.UNSET

        span.start()
        assert span.start_time is not None
        time.sleep(0.01)
        span.end()
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 10

    def test_span_attributes(self):
        span = Span("test")
        span.set_attribute("key", "value")
        span.set_attribute("count", 42)
        assert span.attributes["key"] == "value"
        assert span.attributes["count"] == 42

    def test_span_error(self):
        span = Span("fail")
        span.start()
        span.end(status=SpanStatus.ERROR, error="something broke")
        assert span.status == SpanStatus.ERROR
        assert span.error_message == "something broke"

    def test_span_to_dict(self):
        span = Span("s1", attributes={"foo": "bar"})
        span.start()
        span.end()
        d = span.to_dict()
        assert d["name"] == "s1"
        assert d["attributes"]["foo"] == "bar"
        assert d["duration_ms"] is not None
        assert d["status"] == "ok"


class TestTokenUsage:
    def test_record_and_aggregate(self):
        tu = TokenUsage()
        tu.record("gpt-4o", 100, 200, cost=0.003)
        tu.record("gpt-4o", 150, 300, cost=0.005)

        assert tu.total_input_tokens == 250
        assert tu.total_output_tokens == 500
        assert tu.total_tokens == 750
        assert tu.total_cost == 0.008


class TestTracer:
    def test_trace_lifecycle(self):
        tracer = get_tracer()
        trace = tracer.start_trace("my_run")
        assert trace.name == "my_run"

        span = tracer.start_span("step1")
        span.end()
        result = tracer.end_trace()

        assert len(result.get_all_spans()) == 1
        assert result.get_all_spans()[0].name == "step1"

    def test_nested_spans(self):
        tracer = get_tracer()
        tracer.start_trace("nested")

        parent = tracer.start_span("parent")
        child = tracer.start_span("child")
        tracer.end_span(child)
        tracer.end_span(parent)
        trace = tracer.end_trace()

        spans = trace.get_all_spans()
        assert len(spans) == 2
        assert spans[0].name == "parent"
        assert spans[1].name == "child"
        assert spans[1].parent_id == spans[0].id

    def test_token_tracking(self):
        tracer = get_tracer()
        tracer.start_trace("token_test")
        tracer.set_token_usage("gpt-4o", 100, 200)

        trace = tracer.end_trace()
        assert trace.token_usage.total_input_tokens == 100
        assert trace.token_usage.total_output_tokens == 200

    def test_model_pricing(self):
        tracer = get_tracer()
        tracer.set_model_price("gpt-4o", input_per_1k=2.5, output_per_1k=10.0)
        tracer.start_trace("cost_test")

        # Cost = (100/1000*2.5) + (200/1000*10.0) = 0.25 + 2.0 = 2.25
        tracer.set_token_usage("gpt-4o", 100, 200)
        trace = tracer.end_trace()

        assert trace.token_usage.total_cost == pytest.approx(2.25)


class TestTracedDecorator:
    def test_sync_traced(self):
        tracer = get_tracer()
        tracer.start_trace("decorator_test")

        @traced("my_func")
        def my_func(x: int) -> int:
            return x * 2

        result = my_func(21)
        trace = tracer.end_trace()

        assert result == 42
        spans = trace.get_all_spans()
        assert any(s.name == "my_func" for s in spans)

    def test_async_traced(self):
        tracer = get_tracer()
        tracer.start_trace("async_test")

        @traced("async_add")
        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0.01)
            return a + b

        async def run():
            return await async_add(3, 4)

        result = asyncio.run(run())
        trace = tracer.end_trace()

        assert result == 7
        spans = trace.get_all_spans()
        assert any(s.name == "async_add" for s in spans)

    def test_traced_error(self):
        tracer = get_tracer()
        tracer.start_trace("error_test")

        @traced("failing_func")
        def failing_func():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            failing_func()

        trace = tracer.end_trace()
        error_spans = [s for s in trace.get_all_spans() if s.status == SpanStatus.ERROR]
        assert len(error_spans) == 1
        assert "oops" in error_spans[0].error_message


class TestConsoleExporter:
    def test_export_renders(self):
        tracer = get_tracer()
        exporter = ConsoleExporter(color=False)
        tracer.add_exporter(exporter)

        tracer.start_trace("console_test")
        tracer.start_span("step1", {"key": "val"}).end()
        trace = tracer.end_trace()

        # If it doesn't raise, it worked
        assert trace is not None


class TestJsonFileExporter:
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "traces.jsonl"

            tracer = AgentTracer()
            set_tracer(tracer)
            tracer.add_exporter(JsonFileExporter(path))

            tracer.start_trace("file_test")
            tracer.start_span("s1").end()
            trace = tracer.end_trace()

            # Load and verify
            traces = JsonFileExporter.load(path)
            assert len(traces) == 1
            assert traces[0]["name"] == "file_test"
            assert len(traces[0]["spans"]) == 1

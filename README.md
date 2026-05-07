# agent-observability

> 🔍 Lightweight observability for AI agents — know what's happening inside your agents.

`pip install agent-observability` · [GitHub](https://github.com/PHclaw/agent-observability)

---

## Why

LLM calls are expensive and often opaque. When your agent fails or is slow, you need to know:

- Which step took how long
- How many tokens each call consumed
- What error caused a failure
- Which tool call returned what

`agent-observability` gives you that without locking you into LangSmith, LangFuse, or other SaaS.

---

## Quick Start

```python
from agent_observability import traced, get_tracer
from agent_observability.exporters import ConsoleExporter

tracer = get_tracer()
tracer.add_exporter(ConsoleExporter())

# Set pricing for automatic cost tracking
tracer.set_model_price("gpt-4o", input_per_1k=2.5, output_per_1k=10.0)

tracer.start_trace("weather_agent")

@traced("fetch_data")
def fetch_data(city: str) -> dict:
    return {"temp": 22, "city": city}

tracer.set_token_usage("gpt-4o", input_tokens=120, output_tokens=340)
result = fetch_data("Tokyo")

trace = tracer.end_trace()
print(f"Duration: {trace.duration_ms:.1f}ms")
print(f"Tokens:   {trace.token_usage.total_tokens}")
print(f"Cost:     ${trace.token_usage.total_cost:.4f}")
```

Console output:

```
══ weather_agent ══
  trace_id=a1b2c3d4...  duration=4.2ms
  Token Usage:
    gpt-4o: in=120 out=340 total=460 ($3.65)
    TOTAL: 460 tokens  $3.65
  Spans (1):
  ✓ fetch_data [4.2ms]
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Span tracing** | Wrap any function with `@traced` to capture duration, attributes, errors |
| **Nested spans** | Parent/child relationships mirror your agent's call hierarchy |
| **Token tracking** | Record input/output tokens per LLM call |
| **Cost calculation** | Set model prices once, get cost breakdown automatically |
| **Console exporter** | Pretty-printed debug output with color, tree view |
| **JSON Lines exporter** | Append-only file format — great for streaming + replay |
| **Zero deps** | Pure stdlib, no external lock-in |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Your Agent                           │
│  @traced("step1")    start_span()    set_token_usage()     │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                      AgentTracer                            │
│  Span tree  ·  TokenUsage  ·  Model pricing                 │
└──────────────┬───────────────────────────────────────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
┌─────────┐ ┌────────┐ ┌───────┐
│Console  │ │JSONL   │ │(OTLP  │
│Exporter │ │Exporter│ │future)│
└─────────┘ └────────┘ └───────┘
```

---

## Integrations

### With LangChain
```python
from langchain.callbacks import CallbackManager
from agent_observability import get_tracer

# Works as a drop-in observability layer
```

### With OpenAI / Anthropic clients
```python
from openai import OpenAI
from agent_observability import get_tracer

client = OpenAI()
tracer = get_tracer()
tracer.start_trace("llm_call")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hi"}]
)

tracer.set_token_usage("gpt-4o",
    input_tokens=response.usage.prompt_tokens,
    output_tokens=response.usage.completion_tokens)
trace = tracer.end_trace()
```

### JSONL + Replay
```python
from agent_observability import get_tracer
from agent_observability.exporters import JsonFileExporter

tracer = get_tracer()
tracer.add_exporter(JsonFileExporter("traces.jsonl"))
# ... run agent ...

# Load and replay
traces = JsonFileExporter.load("traces.jsonl")
for trace in traces:
    print(trace["name"], trace["duration_ms"])
```

---

## API Reference

### `tracer.start_trace(name, metadata?)` → `Trace`
Start a new trace for one agent run.

### `tracer.start_span(name, attributes?)` → `Span`
Begin a named span. Automatically parented to the current span.

### `span.set_attribute(key, value)` → `Span`
Attach structured data to a span.

### `tracer.set_token_usage(model, input_tokens, output_tokens)`
Record LLM consumption for the current trace.

### `tracer.set_model_price(model, input_per_1k, output_per_1k)`
Set pricing in USD per 1M tokens.

### `@traced(name?)` decorator
Wrap any sync or async function. Uses the function name if `name` is omitted.

---

## License

MIT

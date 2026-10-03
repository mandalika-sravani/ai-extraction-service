# AI Extraction Service

Turns unstructured text (emails, notes, messages) into validated Pydantic objects
using Claude's tool calling, with input checks, API error handling and
self-correcting retries.

## Task decomposition

| Step | Function | Responsibility | Failure handled |
|------|----------|----------------|-----------------|
| 1 | `validate_input` | Clean and check the raw text | Empty or oversized input |
| 2 | `build_tool` | Convert Pydantic model to a Claude tool (JSON Schema) | — |
| 3 | `call_claude` | Call the API with the tool available (`tool_choice: auto`) | Bad key, rate limit, network, 4xx/5xx |
| 4 | `get_tool_input` | Extract the `tool_use` block | Truncated output; no tool call → nudge and retry |
| 5 | `validate_output` | Run the data through Pydantic validators | Wrong types, bad email/phone |
| 6 | `extract` | Orchestrate steps; on validation failure, return errors to Claude as a `tool_result` with `is_error: true` and retry | Gives up after `max_retries` |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then paste your key into .env
python main.py              # runs on the built-in sample
python main.py "Call Anil at anil@acme.com, he's our CTO"
pytest -q                   # tests use a fake client, no key needed
```

## Reusing for another schema

Define a new Pydantic model in `schemas.py` and pass it in:
`Extractor(Invoice).extract(text)`. Nothing else changes.

## Files

- `schemas.py` – target models and field validators
- `extractor.py` – the service (steps 1–6)
- `main.py` – CLI demo
- `tests/test_extractor.py` – unit tests with a mocked client

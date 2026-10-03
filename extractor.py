"""
AI extraction service: unstructured text -> validated Pydantic object.

Task decomposition (one function per step):
  1. validate_input   - reject empty / oversized text before spending tokens
  2. build_tool       - turn the Pydantic model into a Claude tool definition
  3. call_claude      - send the request with the tool available
  4. get_tool_input   - pull the tool_use block out of the response
                        (None if Claude answered in plain text instead)
  5. validate_output  - run the tool input through Pydantic
  6. retry loop       - if validation fails, send the errors back to Claude
                        as a tool_result and let it correct itself
"""
import logging
import os
from importlib import import_module
from typing import Generic, TypeVar

try:
    import anthropic  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:
    class _AnthropicFallback:
        class AuthenticationError(Exception):
            pass

        class RateLimitError(Exception):
            pass

        class APIConnectionError(Exception):
            pass

        class APIStatusError(Exception):
            def __init__(self, status_code=None, message=""):
                self.status_code = status_code
                self.message = message

    anthropic = _AnthropicFallback()

# Resolve Pydantic dynamically so static analyzers don't require its stubs
# while preserving the existing runtime dependency.
_pydantic = import_module("pydantic")
BaseModel = _pydantic.BaseModel
ValidationError = _pydantic.ValidationError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_INPUT_CHARS = 20_000
SYSTEM_PROMPT = (
    "You extract structured data from text. Use only information that is "
    "explicitly in the text. Never invent values; use null when a field is missing. "
    "Always respond by calling the provided tool exactly once. Do not reply in plain text."
)


class ExtractionError(Exception):
    """Raised when extraction cannot produce a valid object."""


class Extractor(Generic[T]):
    def __init__(self, schema: type[T], client=None, model: str = DEFAULT_MODEL,
                 max_retries: int = 2):
        self.schema = schema
        self.model = model
        self.max_retries = max_retries
        self.tool = self.build_tool(schema)
        # SDK reads ANTHROPIC_API_KEY from the environment and retries
        # transient network/429/5xx errors on its own.
        self.client = client or anthropic.Anthropic()

    # ---- Step 1 ---------------------------------------------------------
    @staticmethod
    def validate_input(text: str) -> str:
        if not text or not text.strip():
            raise ExtractionError("Input text is empty.")
        if len(text) > MAX_INPUT_CHARS:
            raise ExtractionError(f"Input is {len(text)} chars; limit is {MAX_INPUT_CHARS}.")
        return text.strip()

    # ---- Step 2 ---------------------------------------------------------
    @staticmethod
    def build_tool(schema: type[BaseModel]) -> dict:
        return {
            "name": f"save_{schema.__name__.lower()}",
            "description": schema.__doc__ or f"Save a {schema.__name__}.",
            "input_schema": schema.model_json_schema(),
        }

    # ---- Step 3 ---------------------------------------------------------
    def call_claude(self, messages: list[dict]):
        try:
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[self.tool],
                # Some models reject forced tool_choice ("tool"/"any"), so use "auto"
                # and handle the no-tool-call case in the retry loop instead.
                tool_choice={"type": "auto"},
                messages=messages,
            )
        except anthropic.AuthenticationError as e:
            raise ExtractionError("Invalid API key. Check ANTHROPIC_API_KEY.") from e
        except anthropic.RateLimitError as e:
            raise ExtractionError("Rate limited after retries. Try again later.") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError("Could not reach the Claude API.") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"Claude API error {e.status_code}: {e.message}") from e

    # ---- Step 4 ---------------------------------------------------------
    def get_tool_input(self, response) -> tuple[str, dict] | None:
        if response.stop_reason == "max_tokens":
            raise ExtractionError("Response was cut off (max_tokens). Shorten the input.")
        for block in response.content:
            if block.type == "tool_use" and block.name == self.tool["name"]:
                return block.id, block.input
        return None  # Claude answered in text; the caller will nudge and retry

    # ---- Step 5 ---------------------------------------------------------
    def validate_output(self, data: dict) -> T:
        return self.schema.model_validate(data)  # raises ValidationError

    # ---- Step 6: orchestration + self-correction ------------------------
    def extract(self, text: str) -> T:
        text = self.validate_input(text)
        messages = [{"role": "user", "content": f"Extract the data from this text:\n\n{text}"}]

        for attempt in range(1, self.max_retries + 2):
            response = self.call_claude(messages)
            tool_call = self.get_tool_input(response)

            if tool_call is None:
                log.warning("Attempt %d: Claude did not call the tool", attempt)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content":
                    f"You must call the {self.tool['name']} tool with the extracted data."})
                continue

            tool_id, data = tool_call
            try:
                result = self.validate_output(data)
                log.info("Extraction succeeded on attempt %d", attempt)
                return result
            except ValidationError as e:
                log.warning("Attempt %d failed validation: %s", attempt, e.errors())
                # Feed the errors back so Claude can fix them on the next turn.
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "is_error": True,
                    "content": f"Validation failed, fix these and call the tool again:\n{e}",
                }]})

        raise ExtractionError(f"Output still invalid after {self.max_retries + 1} attempts.")

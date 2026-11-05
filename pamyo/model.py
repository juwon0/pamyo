"""Asks a local Ollama model to pick the quotes that answer the question.

The request handling (JSON Schema output, the schema moved into the prompt when the runtime refuses structured output,
code-fence trimming, one warmer retry) is adapted from my earlier Hacktoberfest projects, Chumsak
(https://github.com/juwon0/chumsak) and Jeongsan (https://github.com/juwon0/jeongsan), both MIT.
"""

import json
from typing import Protocol

import httpx

from .prompts import SCHEMA_HINT
from .schemas import Answer

SCHEMA = Answer.model_json_schema()


class ModelError(RuntimeError):
    """The local model was unreachable or answered with something unusable."""


class Medium(Protocol):
    model: str

    def ask(self, prompt: str) -> Answer: ...


class OllamaMedium:
    """Calls a local Ollama server. The code and its history go to localhost and nowhere else."""

    def __init__(self, client: httpx.Client, model: str, num_ctx: int = 16384) -> None:
        self._client = client
        self.model = model
        self._num_ctx = num_ctx  # eight commits with their changes, the code around the line, and the schema
        self.schema_in_prompt = False  # set once the runtime has refused structured output
        self.retries = 0  # answers that were unusable the first time and asked again

    def ask(self, prompt: str) -> Answer:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": SCHEMA,  # constrained decoding to this JSON Schema where the runtime supports it
            "stream": False,
            "think": False,  # Gemma 4 thinks by default; picking quotes doesn't need it and it triples the wait
            # An answer is a few quotes; the cap ends a runaway loop long before the timeout.
            "options": {"temperature": 0, "num_ctx": self._num_ctx, "num_predict": 1024},
        }
        if self.schema_in_prompt:
            _schema_into_prompt(payload)
        # One retry for an unusable answer, a little warmer: at temperature 0 it would come back the same.
        for temperature in (0, 0.2):
            payload["options"]["temperature"] = temperature
            if temperature:
                self.retries += 1
            try:
                resp = self._client.post("/api/chat", json=payload)
                if resp.status_code == 501 and "format" in payload:
                    # Homebrew's Ollama runs Gemma 4 on MLX without structured output and answers 501. Put the
                    # schema in the prompt instead, for this question and the ones after it; validation below
                    # still rejects anything that doesn't fit.
                    self.schema_in_prompt = True
                    _schema_into_prompt(payload)
                    resp = self._client.post("/api/chat", json=payload)
            except httpx.HTTPError as exc:
                raise ModelError(f"{self.model}: {exc!r}") from exc
            if resp.is_error:
                raise ModelError(f"{self.model}: HTTP {resp.status_code} {resp.text[:300]}")
            try:
                content = resp.json()["message"]["content"]
                # Without constrained decoding the model sometimes wraps its JSON in a ```json fence.
                start, end = content.find("{"), content.rfind("}")
                if start != -1 and end > start:
                    content = content[start : end + 1]
                data = json.loads(content)
                if not isinstance(data, dict) or "silent" not in data and "words" not in data:
                    raise ValueError(f"not an answer: {content[:100]!r}")
                data.setdefault("silent", not data.get("words"))
                return Answer.model_validate(data)
            except (KeyError, TypeError, ValueError) as exc:
                unusable = exc
        raise ModelError(f"{self.model}: unusable answer: {unusable}") from unusable


def _schema_into_prompt(payload: dict) -> None:
    schema_json = json.dumps(payload.pop("format"), ensure_ascii=False)
    payload["messages"][0]["content"] += SCHEMA_HINT.format(schema=schema_json)

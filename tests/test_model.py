import json

import httpx
import pytest

from pamyo.model import SCHEMA, ModelError, OllamaMedium

ANSWER = {"silent": False, "words": [{"quote": "바꾸지 마세요.", "source": "c8a38ee"}]}


class FakeOllama:
    """Plays Ollama's /api/chat: replies in order (the last repeats) and keeps every request body."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def medium(ollama: FakeOllama) -> OllamaMedium:
    client = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(ollama))
    return OllamaMedium(client, "gemma4:e4b")


def test_it_asks_for_the_answer_schema_without_thinking():
    ollama = FakeOllama(ANSWER)
    answer = medium(ollama).ask("PROMPT")
    assert answer.words[0].quote == "바꾸지 마세요." and answer.silent is False
    [sent] = ollama.requests
    assert sent["model"] == "gemma4:e4b"
    assert sent["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert sent["format"] == SCHEMA and sent["stream"] is False and sent["think"] is False
    assert sent["options"] == {"temperature": 0, "num_ctx": 16384, "num_predict": 1024}


def test_a_fenced_answer_is_unwrapped():
    ollama = FakeOllama('```json\n{"silent": true, "words": []}\n```')
    assert medium(ollama).ask("P").silent is True


def test_without_structured_output_the_schema_moves_into_the_prompt_for_good():
    ollama = FakeOllama(httpx.Response(501, text="structured output is unavailable"), ANSWER)
    m = medium(ollama)
    m.ask("FIRST")
    m.ask("SECOND")
    refused, retried, second = ollama.requests
    assert "format" in refused
    assert "format" not in retried and retried["messages"][0]["content"].startswith("FIRST")
    assert '"silent"' in retried["messages"][0]["content"] and "JSON Schema" in retried["messages"][0]["content"]
    assert "format" not in second and second["messages"][0]["content"].startswith("SECOND\n\nAnswer with only a JSON")
    assert m.schema_in_prompt and m.retries == 0


def test_an_unusable_answer_is_asked_again_a_little_warmer():
    ollama = FakeOllama("I think the developer was tired.", ANSWER)
    m = medium(ollama)
    assert m.ask("P").words
    assert [r["options"]["temperature"] for r in ollama.requests] == [0, 0.2]
    assert m.retries == 1 and not m.schema_in_prompt


@pytest.mark.parametrize("reply", ["not json", '["a list"]', '{"quotes": []}', '{"silent": "maybe", "words": 3}'])
def test_two_unusable_answers_are_an_error(reply):
    ollama = FakeOllama(reply)
    with pytest.raises(ModelError, match="unusable answer"):
        medium(ollama).ask("P")
    assert len(ollama.requests) == 2


def test_silent_is_filled_in_when_left_out():
    assert medium(FakeOllama({"words": []})).ask("P").silent is True
    assert medium(FakeOllama({"words": ANSWER["words"]})).ask("P").silent is False


def test_a_missing_model_is_an_error():
    ollama = FakeOllama(httpx.Response(404, json={"error": "model 'gemma4:e4b' not found"}))
    with pytest.raises(ModelError, match="HTTP 404.*not found"):
        medium(ollama).ask("P")


def test_ollama_not_running_is_an_error():
    ollama = FakeOllama(httpx.ConnectError("connection refused"))
    with pytest.raises(ModelError, match="ConnectError"):
        medium(ollama).ask("P")

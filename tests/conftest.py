from pathlib import Path

import pytest
from make_haunted_repo import build

from pamyo.history import Record, gather
from pamyo.schemas import Answer, Word

GHOST = ("Old Developer", "old.developer@example.com")


class FakeMedium:
    """Answers in order (the last answer repeats) and remembers every prompt it was given.

    An answer can be an Answer, a function of the prompt that returns one, or an exception to raise.
    """

    def __init__(self, *answers, model: str = "fake-medium") -> None:
        self.answers = list(answers) or [said(silent=True)]
        self.model = model
        self.prompts: list[str] = []

    def ask(self, prompt: str) -> Answer:
        self.prompts.append(prompt)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer(prompt) if callable(answer) else answer


def said(*quotes: tuple[str, str], silent: bool | None = None) -> Answer:
    """An answer from (quote, source) pairs; silent unless told otherwise when there are none."""
    words = [Word(quote=q, source=s) for q, s in quotes]
    return Answer(silent=not words if silent is None else silent, words=words)


def line_of(repo: Path, path: str, text: str) -> int:
    hits = [n for n, line in enumerate((repo / path).read_text(encoding="utf-8").splitlines(), 1) if text in line]
    assert len(hits) == 1, f"{text!r} is on lines {hits} of {path}"
    return hits[0]


def at(repo: Path, path: str, text: str) -> Record:
    """The record for the one line of `path` that contains `text`."""
    n = line_of(repo, path, text)
    return gather(repo, path, n, n)


def commits(*steps: tuple[str, dict[str, str]], author=GHOST) -> list:
    """A history for build(): (message, {path: whole new text}) per commit, a day apart."""
    return [(author, f"2024-01-{i:02d}T10:00:00+09:00", message, files, []) for i, (message, files) in enumerate(steps, 1)]


@pytest.fixture(scope="session")
def haunted(tmp_path_factory) -> Path:
    return build(tmp_path_factory.mktemp("haunted") / "dalbit-orders")


@pytest.fixture
def make_repo(tmp_path):
    def make(*steps: tuple[str, dict[str, str]], author=GHOST) -> Path:
        return build(tmp_path / "repo", commits(*steps, author=author))

    return make

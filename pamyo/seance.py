"""One question: read the record, let the model pick quotes, keep only the quotes the record contains."""

import time
from dataclasses import dataclass
from pathlib import Path

from .history import Record, gather
from .model import Medium
from .prompts import DEFAULT_QUESTION, seance_prompt
from .verify import ECHO, NOT_FOUND, THIN, Checked, check


@dataclass(frozen=True)
class Seance:
    record: Record
    question: str
    model: str
    checked: list[Checked]
    model_said_silent: bool
    seconds: float

    @property
    def kept(self) -> list[Checked]:
        return [c for c in self.checked if c.kept]

    @property
    def struck(self) -> list[Checked]:
        return [c for c in self.checked if c.verdict == NOT_FOUND]

    @property
    def set_aside(self) -> list[Checked]:
        return [c for c in self.checked if c.verdict in (ECHO, THIN)]

    @property
    def silent(self) -> bool:
        """Nothing in the record says why. The model's own opinion on that doesn't decide it; the kept quotes do."""
        return not self.kept


def summon(medium: Medium, repo: Path, path: str, start: int, end: int, question: str = "") -> Seance:
    record = gather(repo, path, start, end)
    question = question.strip() or DEFAULT_QUESTION
    started = time.perf_counter()
    answer = medium.ask(seance_prompt(record, question))
    seconds = time.perf_counter() - started
    return Seance(record, question, medium.model, check(answer, record), answer.silent, seconds)


def to_json(seance: Seance) -> dict:
    r = seance.record
    return {
        "path": r.path,
        "lines": [r.start, r.end],
        "question": seance.question,
        "model": seance.model,
        "seconds": round(seance.seconds, 2),
        "silent": seance.silent,
        "model_said_silent": seance.model_said_silent,
        "commits_seen": r.total_commits,
        "quotes": [
            {
                "quote": c.quote,
                "source_named": c.source,
                "verdict": c.verdict,
                "commit": c.commit.short if c.commit else None,
                "commit_subject": c.commit.subject if c.commit else None,
                "line": c.line,
                "author": c.author or None,
                "date": (c.commit.day if c.commit else c.blame.day if c.blame else None),
            }
            for c in seance.checked
        ],
    }

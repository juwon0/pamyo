"""Checks every quote against the record. A quote the record doesn't contain is struck, however plausible it sounds.

A quote counts as found when its text appears in a source after normalizing whitespace, quote marks and letter
case, and without punctuation at either end. A commit's words are its message and the lines it added; lines it
removed or only showed as context were somebody else's. "..." in a quote may stand for a gap, as long as the pieces
appear in order. A quote that is found
but is only code, not anyone's message, comment or docstring, is set aside: code says what, not why.
"""

import unicodedata
from dataclasses import dataclass

from .history import Blame, Commit, Record
from .schemas import Answer
from .syntax import code_parts, unmark

KEPT = "kept"  # found, and says something beyond the code itself
NOT_FOUND = "not_found"  # in no source: the model made it up or changed it
ECHO = "echo"  # found, but only as code: the lines being asked about or the code around them
THIN = "thin"  # found, but too short to explain anything ("fix", "급함")

_MARKS = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "`": None})


@dataclass(frozen=True)
class Checked:
    quote: str
    source: str  # the source the model named
    verdict: str
    commit: Commit | None = None  # where the quote was found, for a quote from a commit
    line: int | None = None  # where the quote starts, for a quote from the code
    blame: Blame | None = None  # who last touched that line, for a quote from the code

    @property
    def kept(self) -> bool:
        return self.verdict == KEPT

    @property
    def author(self) -> str:
        if self.commit:
            return self.commit.author
        return self.blame.author if self.blame else ""


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(_MARKS).split()).casefold()


def check(answer: Answer, record: Record) -> list[Checked]:
    seen: set[str] = set()
    checked = []
    for word in answer.words:
        quote = word.quote.strip().strip("\"'“”‘’`").strip()
        if not quote or norm(quote) in seen:
            continue
        seen.add(norm(quote))
        checked.append(_check(quote, word.source.strip(), record))
    return checked


def _check(quote: str, source: str, record: Record) -> Checked:
    q = norm(quote)
    found = _find(q, source, record)
    if found is None:
        return Checked(quote, source, NOT_FOUND)
    commit, line = found
    blame = record.blame.get(line) if line is not None else None
    if _only_code(q, commit, record):
        verdict = ECHO
    elif _thin(q):
        verdict = THIN
    else:
        verdict = KEPT
    return Checked(quote, source, verdict, commit=commit, line=line, blame=blame)


def _find(q: str, source: str, record: Record) -> tuple[Commit | None, int | None] | None:
    """Where the quote is: the named source first, then any other. A misnamed source is corrected, not trusted."""
    named = source.lower().removeprefix("commit").strip(" []#:")
    candidates: list[Commit | None] = []
    if named == "code":
        candidates.append(None)
    candidates += [c for c in record.commits if len(named) >= 4 and c.sha.startswith(named)]
    candidates += [c for c in reversed(record.commits) if c not in candidates]  # oldest first: the original author
    if None not in candidates:
        candidates.append(None)
    for candidate in candidates:
        if candidate is None:
            line = _find_in_code(q, record)
            if line is not None:
                return None, line
        elif _in_commit(q, candidate):
            return candidate, None
    return None


def _in_commit(q: str, commit: Commit) -> bool:
    added = _added(commit.diff)
    return any(
        _contained(norm(commit.message + "\n" + "\n".join(lines)), q) for lines in (added, [unmark(a) for a in added])
    )


def _find_in_code(q: str, record: Record) -> int | None:
    """The line the quote starts on. Tried once as written and once without comment markers at line starts."""
    for clean in (str, unmark):
        starts, parts = [], []
        offset = 0
        for n, text in record.lines.items():
            t = norm(clean(text))
            if t:
                starts.append((offset, n))
                parts.append(t)
                offset += len(t) + 1
        joined = " ".join(parts)
        if _contained(joined, q):
            at = joined.find(_pieces(q)[0])
            return max(n for start, n in starts if start <= at)
    return None


def _only_code(q: str, commit: Commit | None, record: Record) -> bool:
    """The quote is code: the asked lines (wherever it was found), the code around them, or code a commit added."""
    if _contained(norm(" ".join(record.code[n] for n in range(record.start, record.end + 1))), q):
        return True
    if commit is None:
        return _contained(norm(" ".join(record.code.values())), q)
    if _contained(norm(commit.message), q):
        return False
    return _contained(norm(" ".join(code_parts(_added(commit.diff), record.path))), q)


_EDGE_PUNCTUATION = " .,;:!?。、"


def _pieces(q: str) -> list[str]:
    """The parts of a quote between "..." gaps, each without the punctuation at its ends."""
    pieces = (p.strip(_EDGE_PUNCTUATION) for p in q.split("..."))
    return [p for p in pieces if p]


def _contained(haystack: str, q: str) -> bool:
    pieces = _pieces(q)
    if not pieces:
        return False
    pos = 0
    for piece in pieces:
        at = haystack.find(piece, pos)
        if at < 0:
            return False
        pos = at + len(piece)
    return True


def _added(diff: str) -> list[str]:
    return [line[1:] for line in diff.splitlines() if line.startswith("+")]


def _thin(q: str) -> bool:
    weight = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in q if not ch.isspace())
    return len(q.split()) < 2 or weight < 8

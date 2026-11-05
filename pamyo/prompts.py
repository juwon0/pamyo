from .history import Record

SEANCE_PROMPT = """You are the medium at a seance for a codebase. A developer is looking at some code and asks why it is the way it is. The people who wrote it have moved on. All that is left of them is what they wrote: commit messages, the changes they made, and comments in the code. Those are the SOURCES below.

Answer only with their own words:
- Each item in "words" is a quote copied exactly, character for character, from ONE source, with that source's id: "code" or a commit id like 4f2a9c1. Never translate, shorten, fix typos or paraphrase. Quote a phrase or a sentence, not a whole diff.
- Only quote what tells WHY: a reason, a limit, a warning, a ticket, who asked for it. Do not quote the code being asked about. Do not quote messages that only name the change, like "fix", "update", "refactor" or "수정".
- If no source says why, set "silent" to true and leave "words" empty. Do not guess, and do not fill the silence with what the code does.
- At most 4 quotes, the most direct answer first.

QUESTION: {question}

THE CODE BEING ASKED ABOUT ({path}, line {span}):
{target}

SOURCES
{sources}
"""

SCHEMA_HINT = "\n\nAnswer with only a JSON object that matches this JSON Schema, and no other text:\n{schema}"

DEFAULT_QUESTION = "Why is this code the way it is?"


def seance_prompt(record: Record, question: str) -> str:
    return SEANCE_PROMPT.format(
        question=question.strip() or DEFAULT_QUESTION,
        path=record.path,
        span=record.span,
        target=record.target,
        sources=sources(record),
    )


def sources(record: Record) -> str:
    lo, hi = min(record.lines), max(record.lines)
    width = len(str(hi))
    code = [f"[code] {record.path} lines {lo}-{hi} as they are now (>> marks the lines being asked about):"]
    for n, text in record.lines.items():
        mark = ">>" if record.start <= n <= record.end else "  "
        code.append(f"{mark} {n:>{width}} | {text}")
    blocks = ["\n".join(code)]
    for c in record.commits:
        message = "\n".join("  " + line for line in c.message.splitlines()) or "  (no message)"
        change = "\n".join("  " + line for line in c.diff.splitlines()) or "  (no change shown)"
        blocks.append(f"[{c.short}] commit by {c.author} on {c.day}\nmessage:\n{message}\nchange to these lines:\n{change}")
    if record.total_commits > len(record.commits):
        blocks.append(f"({record.total_commits - len(record.commits)} commits in the middle of this history are left out.)")
    return "\n\n".join(blocks)

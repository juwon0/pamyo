"""Turns a seance into lines of styled text, for the terminal (ANSI) or a page (HTML, used for the demo GIF).

Only the quotes come from the model, and only after they were found in git. Every other word on screen is this
file's own text or a fact read straight from git.
"""

import html as html_lib

from .seance import Seance
from .verify import ECHO, Checked

Line = list[tuple[str, str]]  # (style, text) pieces

ANSI = {
    "": "",
    "dim": "\x1b[2m",
    "code": "\x1b[36m",
    "ghost": "\x1b[1;35m",
    "quote": "\x1b[1m",
    "warn": "\x1b[33m",
    "struck": "\x1b[2;9m",
    "silent": "\x1b[1;34m",
}


def lines(s: Seance) -> list[Line]:
    r = s.record
    out: list[Line] = [[("dim", f"{r.path}:{r.span}  ·  {s.question}")]]
    width = len(str(r.end))
    for n in range(r.start, r.end + 1):
        out.append([("dim", f"  {n:>{width}} │ "), ("code", r.lines[n].rstrip())])
    last = r.blame.get(r.start)
    if last:
        out.append([("dim", f"  last touched by {last.author}, {last.day}, {last.short} “{last.subject}”")])
    out.append([])

    if s.silent:
        out.append([("silent", "  The record is silent. Nobody wrote down why.")])
        if r.commits:
            said = ", ".join(f"“{c.subject}”" for c in r.commits[:4])
            more = " and more" if r.total_commits > 4 else ""
            plural = "commit" if r.total_commits == 1 else "commits"
            out.append([("dim", f"  {r.total_commits} {plural} touched these lines, saying {said}{more}.")])
    else:
        author = None
        for c in s.kept:
            if c.author != author:
                author = c.author
                out.append([("ghost", f"  {author or 'Someone'} left these words:")])
            out.append([("quote", f"    “{c.quote}”")])
            out.append([("dim", f"        {_where(c)}")])

    if s.struck:
        out.append([])
        n = len(s.struck)
        out.append([("warn", f"  ✗ {n} {'quote' if n == 1 else 'quotes'} struck: not in the record")])
        for c in s.struck:
            out.append([("", "    "), ("struck", f"“{c.quote}”"), ("dim", f"  said to be from {c.source or '?'}")])
    if s.set_aside:
        echo = sum(c.verdict == ECHO for c in s.set_aside)
        thin = len(s.set_aside) - echo
        notes = []
        if echo:
            notes.append(f"{echo} only repeating the code")
        if thin:
            notes.append(f"{thin} too short to explain anything")
        out.append([("dim", f"  (set aside: {', '.join(notes)})")])
    out.append([])
    out.append([("dim", f"  {s.model} · {s.seconds:.1f} s · quotes are checked against git; struck ones weren't there")])
    return out


def _where(c: Checked) -> str:
    if c.commit:
        return f"commit {c.commit.short}, {c.commit.day} · “{c.commit.subject}”"
    if c.blame:
        return f"comment at line {c.line} · {c.blame.day}, {c.blame.short} “{c.blame.subject}”"
    return f"line {c.line}"


def ansi(s: Seance, color: bool = True) -> str:
    rows = []
    for line in lines(s):
        if color:
            rows.append("".join(f"{ANSI[style]}{text}\x1b[0m" if style else text for style, text in line))
        else:
            rows.append("".join(text for _, text in line))
    return "\n".join(rows)


def html(s: Seance) -> str:
    """One <div> per line; a long line wraps under its own indent. The page around it styles the classes."""
    rows = []
    for line in lines(s):
        text = "".join(t for _, t in line)
        hang = len(text) - len(text.lstrip(" ")) + 1
        parts = "".join(f'<span class="{style}">{html_lib.escape(t)}</span>' if style else html_lib.escape(t) for style, t in line)
        rows.append(f'<div style="padding-left:{hang}ch;text-indent:-{hang}ch">{parts or "&nbsp;"}</div>')
    return "\n".join(rows)

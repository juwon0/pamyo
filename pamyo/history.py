"""Collects what the people who wrote some lines left behind: commit messages, their changes, the comments nearby.

Everything comes from the local git repository. Nothing here talks to the network.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .syntax import code_parts

WINDOW = 12  # lines shown around the asked lines, so comments above and below count as sources
MAX_COMMITS = 8  # a long history keeps its newest and oldest commits; the middle is mostly churn
MAX_DIFF_LINES = 40
MAX_MESSAGE_CHARS = 1500


class HistoryError(RuntimeError):
    """The repository, file or line range can't be read."""


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    date: str  # author date, ISO 8601
    message: str
    diff: str  # the change to the asked lines, as `git log -L` shows it

    @property
    def short(self) -> str:
        return self.sha[:7]

    @property
    def subject(self) -> str:
        lines = self.message.strip().splitlines()
        return lines[0] if lines else ""

    @property
    def day(self) -> str:
        return self.date[:10]


@dataclass(frozen=True)
class Blame:
    sha: str
    author: str
    date: str
    subject: str

    @property
    def short(self) -> str:
        return self.sha[:7]

    @property
    def day(self) -> str:
        return self.date[:10]


@dataclass(frozen=True)
class Record:
    repo: Path
    path: str  # relative to the repository root
    start: int
    end: int
    lines: dict[int, str]  # the asked lines and the window around them, as committed at HEAD
    code: dict[int, str]  # the same lines with comments and docstrings taken out: only what runs
    commits: list[Commit]  # newest first, possibly trimmed to MAX_COMMITS
    blame: dict[int, Blame]  # every line in `lines` -> the commit that last touched it
    total_commits: int  # how many commits touched the asked lines before trimming

    @property
    def target(self) -> str:
        return "\n".join(self.lines[n] for n in range(self.start, self.end + 1))

    @property
    def span(self) -> str:
        return str(self.start) if self.start == self.end else f"{self.start}-{self.end}"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise HistoryError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def find_repo(path: Path) -> Path:
    start = path if path.is_dir() else path.parent
    if not start.exists():
        raise HistoryError(f"{path} does not exist")
    return Path(git(start, "rev-parse", "--show-toplevel").strip())


def gather(repo: Path, path: str, start: int, end: int) -> Record:
    """Reads the asked lines at HEAD, the commits that shaped them, and who last touched the lines around them."""
    text = git(repo, "show", f"HEAD:{path}")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not 1 <= start <= end <= len(lines):
        raise HistoryError(f"{path} has {len(lines)} lines at HEAD; there is no line {start if start > end else end}")
    lo, hi = max(1, start - WINDOW), min(len(lines), end + WINDOW)
    code = code_parts(lines, path)  # from the top of the file, so a docstring above the window is known
    commits = _log(repo, path, start, end)
    total = len(commits)
    if total > MAX_COMMITS:
        half = MAX_COMMITS // 2
        commits = commits[:half] + commits[-half:]
    return Record(
        repo=repo,
        path=path,
        start=start,
        end=end,
        lines={n: lines[n - 1] for n in range(lo, hi + 1)},
        code={n: code[n - 1] for n in range(lo, hi + 1)},
        commits=commits,
        blame=_blame(repo, path, lo, hi),
        total_commits=total,
    )


def _log(repo: Path, path: str, start: int, end: int) -> list[Commit]:
    out = git(repo, "log", "--no-color", "--no-ext-diff", "--format=%x1e%H%x1f%an%x1f%aI%x1f%B%x1f", f"-L{start},{end}:{path}")
    commits = []
    for record in out.split("\x1e")[1:]:
        sha, author, date, message, diff = record.split("\x1f", 4)
        hunk = diff.split("\n@@", 1)
        diff = "@@" + hunk[1] if len(hunk) == 2 else ""
        diff_lines = diff.rstrip("\n").split("\n")
        if len(diff_lines) > MAX_DIFF_LINES:
            diff_lines = diff_lines[:MAX_DIFF_LINES] + ["(rest of the change cut)"]
        message = message.strip()
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[:MAX_MESSAGE_CHARS] + " (rest of the message cut)"
        commits.append(Commit(sha=sha, author=author, date=date, message=message, diff="\n".join(diff_lines)))
    return commits


def _blame(repo: Path, path: str, lo: int, hi: int) -> dict[int, Blame]:
    out = git(repo, "blame", "--porcelain", f"-L{lo},{hi}", "HEAD", "--", path)
    info: dict[str, dict[str, str]] = {}
    result: dict[int, Blame] = {}
    sha, line_no = "", 0
    for row in out.split("\n"):
        head = row.split(" ")
        if len(head[0]) == 40 and len(head) >= 3 and all(c in "0123456789abcdef" for c in head[0]):
            sha, line_no = head[0], int(head[2])
            info.setdefault(sha, {})
        elif row.startswith("\t"):
            meta = info[sha]
            result[line_no] = Blame(
                sha=sha,
                author=meta.get("author", ""),
                date=_iso(meta.get("author-time", "0"), meta.get("author-tz", "+0000")),
                subject=meta.get("summary", ""),
            )
        elif sha and " " in row:
            key, value = row.split(" ", 1)
            info[sha].setdefault(key, value)
    return result


def _iso(epoch: str, tz: str) -> str:
    sign = -1 if tz.startswith("-") else 1
    offset = timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sign
    return datetime.fromtimestamp(int(epoch), timezone(offset)).isoformat()

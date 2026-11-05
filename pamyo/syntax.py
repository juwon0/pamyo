"""Tells the code on a line from the words written for people: comments and docstrings.

verify.py uses it to set aside quotes that are only code. A guess from the file extension is enough for that.
"""

import re
from pathlib import PurePosixPath

_HASH = {".py", ".pyi", ".rb", ".sh", ".bash", ".zsh", ".pl", ".r", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".tf"}
_SLASH = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".scala", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".dart", ".php"}
_DASH = {".sql", ".lua", ".hs"}
_DOCSTRINGS = (('"""', '"""'), ("'''", "'''"))
_BLOCK_COMMENTS = (("/*", "*/"),)

# A comment marker at the start of a line, so a comment spread over several lines can be quoted as one sentence.
_LEADING_MARK = re.compile(r"^\s*(?:#+|//+|/\*+|\*+/?|--)\s?")


def _syntax(path: str) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Line comment markers and (open, close) pairs for the file's language."""
    p = PurePosixPath(path)
    suffix = p.suffix.lower()
    if suffix in (".py", ".pyi"):
        return ("#",), _DOCSTRINGS  # not "//": that's floor division
    if suffix in _HASH or p.name in ("Makefile", "Dockerfile"):
        return ("#",), ()
    if suffix in _SLASH:
        return ("//",), _BLOCK_COMMENTS
    if suffix in _DASH:
        return ("--",), _BLOCK_COMMENTS
    return ("#", "//"), _BLOCK_COMMENTS


def code_parts(lines: list[str], path: str) -> list[str]:
    """Each line with its comments and docstrings taken out and string literals kept: only what runs.

    Pass the lines from the top of the file, so a docstring that started above is known to be one.
    """
    marks, blocks = _syntax(path)
    out, closing = [], ""
    for line in lines:
        code, i, quote = [], 0, ""
        while i < len(line):
            if closing:
                end = line.find(closing, i)
                if end < 0:
                    break
                i, closing = end + len(closing), ""
                continue
            ch = line[i]
            if quote:
                if ch == quote and line[i - 1] != "\\":
                    quote = ""
            else:
                block = next((b for b in blocks if line.startswith(b[0], i)), None)
                if block:
                    i, closing = i + len(block[0]), block[1]
                    continue
                if any(line.startswith(m, i) for m in marks):
                    break
                if ch in "'\"":
                    quote = ch
            code.append(ch)
            i += 1
        out.append("".join(code))
    return out


def unmark(line: str) -> str:
    return _LEADING_MARK.sub("", line)

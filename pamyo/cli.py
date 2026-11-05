"""pamyo why PATH:LINE[-END] [QUESTION]

    pamyo why orders/payment.py:42
    pamyo why orders/payment.py:40-44 "왜 0.4초를 쉬어?"
    pamyo why orders/payment.py:42 --json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx

from . import config, render
from .history import HistoryError, find_repo
from .model import ModelError, OllamaMedium
from .seance import summon, to_json

TARGET = re.compile(r"^(?P<path>.+):(?P<start>\d+)(?:-(?P<end>\d+))?$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pamyo", description="Ask the developer who left why the code is like that.")
    sub = parser.add_subparsers(dest="command", required=True)
    why = sub.add_parser("why", help="ask why some lines are the way they are")
    why.add_argument("target", help="PATH:LINE or PATH:START-END")
    why.add_argument("question", nargs="*", help="your question, in any language (default: why is this here?)")
    why.add_argument("--repo", type=Path, help="the git repository (default: the one PATH is in)")
    why.add_argument("--model", default=config.MODEL, help=f"Ollama model (default {config.MODEL}, or PAMYO_MODEL)")
    why.add_argument("--ollama", default=config.OLLAMA_URL, help=f"Ollama address (default {config.OLLAMA_URL})")
    why.add_argument("--json", action="store_true", help="print the result as JSON")
    why.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)

    match = TARGET.match(args.target)
    if not match:
        parser.error(f"expected PATH:LINE or PATH:START-END, got {args.target!r}")
    start = int(match["start"])
    end = int(match["end"] or start)
    file = Path(match["path"])
    try:
        repo = (args.repo or find_repo(file.resolve())).resolve()
        if not file.is_absolute():
            file = (repo / file) if args.repo else file.resolve()
        path = file.resolve().relative_to(repo).as_posix()
    except (HistoryError, ValueError) as exc:
        print(f"pamyo: {exc}", file=sys.stderr)
        return 1

    with httpx.Client(base_url=args.ollama, timeout=httpx.Timeout(600, connect=5)) as client:
        try:
            seance = summon(OllamaMedium(client, args.model), repo, path, start, end, " ".join(args.question))
        except HistoryError as exc:
            print(f"pamyo: {exc}", file=sys.stderr)
            return 1
        except ModelError as exc:
            print(f"pamyo: {config.MODEL_DOWN}\n  {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(to_json(seance), ensure_ascii=False, indent=2))
    else:
        color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
        print(render.ansi(seance, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())

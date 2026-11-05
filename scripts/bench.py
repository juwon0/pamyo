"""Asks every question in bench/questions.json about the haunted repository, a few times over, and scores the answers.

    uv run python scripts/bench.py                                   # PAMYO_MODEL, or gemma4:e4b
    uv run python scripts/bench.py --model gemma4:12b --runs 3 --readme

An answerable question is right when a kept quote comes from the commit (or comment) that holds the reason and
contains the reason. An unanswerable one is right when Pamyo stays silent. Writes docs/bench-<model>.json and, with
--readme, the table between the bench markers in README.md. The model is loaded before the first question, so the
timings are answering alone.
"""

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from make_haunted_repo import build  # noqa: E402

from pamyo import config  # noqa: E402
from pamyo.model import Medium, OllamaMedium  # noqa: E402
from pamyo.seance import summon, to_json  # noqa: E402
from pamyo.verify import norm  # noqa: E402

QUESTIONS = ROOT / "bench" / "questions.json"
START, END = "<!-- bench:start -->", "<!-- bench:end -->"


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["questions"]


def locate(repo: Path, question: dict) -> int:
    lines = (repo / question["file"]).read_text(encoding="utf-8").splitlines()
    hits = [n for n, text in enumerate(lines, 1) if question["line"] in text]
    if len(hits) != 1:
        raise ValueError(f"{question['id']}: {question['line']!r} is on {len(hits)} lines of {question['file']}")
    return hits[0]


def score(question: dict, result: dict) -> dict:
    kept = [q for q in result["quotes"] if q["verdict"] == "kept"]
    if question.get("silent"):
        right = result["silent"]
    else:
        right = any(_from_the_reason(question, q) for q in kept)
    return {
        "id": question["id"],
        "answerable": not question.get("silent"),
        "right": right,
        "silent": result["silent"],
        "model_said_silent": result["model_said_silent"],
        "kept": len(kept),
        "struck": sum(q["verdict"] == "not_found" for q in result["quotes"]),
        "set_aside": sum(q["verdict"] in ("echo", "thin") for q in result["quotes"]),
        "seconds": result["seconds"],
    }


def _from_the_reason(question: dict, quote: dict) -> bool:
    source_ok = quote["commit_subject"] in question["from"] or (quote["commit"] is None and "code" in question["from"])
    return source_ok and any(norm(says) in norm(quote["quote"]) for says in question["says"])


def run(medium: Medium, repo: Path, questions: list[dict], runs: int, log=print) -> list[dict]:
    results = []
    for n in range(1, runs + 1):
        for question in questions:
            line = locate(repo, question)
            seance = summon(medium, repo, question["file"], line, line, question["ask"])
            result = to_json(seance) | {"id": question["id"], "run": n}
            scored = score(question, result)
            results.append(result | {"score": scored})
            mark = "right" if scored["right"] else "WRONG"
            log(f"  run {n} {question['id']:<14} {mark:<5} kept {scored['kept']} struck {scored['struck']} {seance.seconds:5.1f} s")
    return results


def summarize(results: list[dict], runs: int, load_seconds: float | None) -> dict:
    scores = [r["score"] for r in results]
    answerable = [s for s in scores if s["answerable"]]
    unanswerable = [s for s in scores if not s["answerable"]]
    per_question: dict[str, int] = {}
    for s in scores:
        per_question[s["id"]] = per_question.get(s["id"], 0) + s["right"]
    return {
        "runs": runs,
        "questions": len(scores) // runs if runs else 0,
        "answered_right": [sum(s["right"] for s in answerable), len(answerable)],
        "silent_right": [sum(s["right"] for s in unanswerable), len(unanswerable)],
        "silent_when_answer_existed": sum(s["silent"] for s in answerable),
        "wrong_quote_kept": sum(not s["right"] and not s["silent"] for s in answerable),
        "spoke_when_nothing_was_written": sum(not s["silent"] for s in unanswerable),
        "quotes_struck": sum(s["struck"] for s in scores),
        "asks_with_a_struck_quote": sum(s["struck"] > 0 for s in scores),
        "asks_made_silent_by_checks": sum(s["silent"] and not s["model_said_silent"] for s in scores),
        "quotes_set_aside": sum(s["set_aside"] for s in scores),
        "load_seconds": round(load_seconds, 1) if load_seconds is not None else None,
        "ask_seconds": _spread([s["seconds"] for s in scores]),
        "per_question": per_question,
    }


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"mean": round(statistics.mean(values), 1), "min": round(min(values), 1), "max": round(max(values), 1)}


def table(summary: dict, model: str, machine: str, ollama: str = "") -> str:
    a, s = summary["answered_right"], summary["silent_right"]
    ask = summary["ask_seconds"]
    rows = [
        f"| {model} via Ollama{' ' + ollama if ollama else ''} | {machine} |",
        "|---|---|",
        f"| Questions asked | {summary['questions']} × {summary['runs']} runs |",
        f"| Reason found and quoted, when it was written down | {a[0]}/{a[1]} |",
        f"| Stayed silent, when nobody wrote it down | {s[0]}/{s[1]} |",
        f"| Spoke anyway when nobody wrote it down | {summary['spoke_when_nothing_was_written']} |",
        f"| Silent although the reason was there | {summary['silent_when_answer_existed']} |",
        f"| Quoted real words that aren't the reason | {summary['wrong_quote_kept']} |",
        f"| Quotes struck because git doesn't contain them | {summary['quotes_struck']} (in {summary['asks_with_a_struck_quote']} answers) |",
        f"| Quotes set aside: only code, or too short to explain | {summary['quotes_set_aside']} |",
        f"| Answers the checks turned silent | {summary['asks_made_silent_by_checks']} |",
    ]
    if summary["load_seconds"] is not None:
        rows.append(f"| Loading the model, once | {summary['load_seconds']} s |")
    if ask:
        rows.append(f"| Seconds per question | {ask['mean']} ({ask['min']}–{ask['max']}) |")
    per = ", ".join(f"{k} {v}/{summary['runs']}" for k, v in summary["per_question"].items())
    return "\n".join(rows) + f"\n\nPer question: {per}."


def write_readme(block: str, readme: Path = ROOT / "README.md") -> None:
    text = readme.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{START}\n{block}\n{END}{tail}", encoding="utf-8")


def ollama_version(client: httpx.Client) -> str:
    try:
        return client.get("/api/version").json().get("version", "")
    except (httpx.HTTPError, ValueError):
        return ""


def load_model(client: httpx.Client, model: str) -> float:
    started = time.perf_counter()
    resp = client.post("/api/generate", json={"model": model, "keep_alive": "30m"})
    resp.raise_for_status()
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=config.MODEL)
    parser.add_argument("--ollama", default=config.OLLAMA_URL)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--machine", default="", help='for the table, e.g. "Apple M4 Pro, 48 GB, 2026-10-28"')
    parser.add_argument("--readme", action="store_true", help="write the table into README.md")
    parser.add_argument("--only", nargs="*", help="question ids to ask (default: all)")
    parser.add_argument("--out", type=Path, help="where the results go (default: docs/bench-MODEL.json)")
    args = parser.parse_args()

    questions = [q for q in load_questions() if not args.only or q["id"] in args.only]
    with tempfile.TemporaryDirectory(prefix="pamyo-haunted-") as tmp, httpx.Client(
        base_url=args.ollama, timeout=httpx.Timeout(600, connect=5)
    ) as client:
        repo = build(Path(tmp) / "dalbit-orders")
        version = ollama_version(client)
        print(f"Loading {args.model} on Ollama {version or '(version unknown)'} ...", flush=True)
        load_seconds = load_model(client, args.model)
        print(f"  loaded in {load_seconds:.1f} s", flush=True)
        medium = OllamaMedium(client, args.model)
        results = run(medium, repo, questions, args.runs, log=lambda m: print(m, flush=True))

    summary = summarize(results, args.runs, load_seconds)
    summary["structured_output"] = not medium.schema_in_prompt  # False: the runtime refused it (HTTP 501)
    summary["unusable_answers_asked_again"] = medium.retries
    out = args.out or ROOT / "docs" / f"bench-{args.model.replace(':', '-').replace('/', '-')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"model": args.model, "ollama": version, "machine": args.machine, "summary": summary, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    block = table(summary, args.model, args.machine or "this machine", version)
    print("\n" + json.dumps(summary, ensure_ascii=False))
    print("\n" + block)
    print(f"\nWrote {out}")
    if args.readme:
        write_readme(block)
        print("Wrote the table into README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

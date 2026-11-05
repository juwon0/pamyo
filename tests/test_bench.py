import bench
import pytest
from conftest import FakeMedium, said

from pamyo.history import gather
from pamyo.syntax import code_parts
from pamyo.verify import norm

QUESTIONS = bench.load_questions()


def test_the_questions_are_well_formed():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids)) == 18
    for q in QUESTIONS:
        assert q["ask"].strip()
        if q.get("silent"):
            assert "from" not in q and "says" not in q
        else:
            assert q["from"] and q["says"]
    assert sum(bool(q.get("silent")) for q in QUESTIONS) == 6


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q["id"])
def test_each_question_points_at_one_line(haunted, question):
    assert bench.locate(haunted, question) >= 1


@pytest.mark.parametrize("question", [q for q in QUESTIONS if not q.get("silent")], ids=lambda q: q["id"])
def test_every_answerable_question_has_its_answer_in_the_record(haunted, question):
    """What a right answer would quote is really there, in a source the scoring accepts."""
    n = bench.locate(haunted, question)
    record = gather(haunted, question["file"], n, n)
    texts = []
    for source in question["from"]:
        if source == "code":
            prose = [line for line, code in zip(record.lines.values(), record.code.values(), strict=True) if line.strip() != code.strip()]
            texts.append(norm(" ".join(prose)))
        else:
            [commit] = [c for c in record.commits if c.subject == source]
            texts.append(norm(commit.message + "\n" + commit.diff))
    for says in question["says"]:
        assert any(norm(says) in text for text in texts), says


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q.get("silent")], ids=lambda q: q["id"])
def test_unanswerable_questions_have_no_comment_on_their_line(haunted, question):
    n = bench.locate(haunted, question)
    line = (haunted / question["file"]).read_text(encoding="utf-8").splitlines()[n - 1]
    assert code_parts([line], question["file"]) == [line]


def oracle(prompt: str):
    """Answers every question perfectly: the longest phrase a right answer must contain, or silence."""
    question = next(q for q in QUESTIONS if f"QUESTION: {q['ask']}\n" in prompt)
    if question.get("silent"):
        return said(silent=True)
    return said((max(question["says"], key=len), question["from"][0]))


def liar(prompt: str):
    return said(("The PG asked us to, in a meeting.", "code"))


def test_a_perfect_medium_scores_full_marks(haunted):
    results = bench.run(FakeMedium(oracle), haunted, QUESTIONS, runs=2, log=lambda m: None)
    summary = bench.summarize(results, runs=2, load_seconds=3.21)
    assert summary["answered_right"] == [24, 24] and summary["silent_right"] == [12, 12]
    assert summary["spoke_when_nothing_was_written"] == 0 and summary["silent_when_answer_existed"] == 0
    assert summary["quotes_struck"] == 0 and summary["asks_made_silent_by_checks"] == 0
    assert summary["questions"] == 18 and summary["load_seconds"] == 3.2
    assert set(summary["per_question"].values()) == {2}
    assert summary["ask_seconds"]["mean"] >= 0


def test_a_lying_medium_is_struck_every_time(haunted):
    results = bench.run(FakeMedium(liar), haunted, QUESTIONS, runs=1, log=lambda m: None)
    summary = bench.summarize(results, runs=1, load_seconds=None)
    assert summary["answered_right"] == [0, 12]
    assert summary["silent_right"] == [6, 6]  # silent only because every quote was struck
    assert summary["quotes_struck"] == 18 and summary["asks_with_a_struck_quote"] == 18
    assert summary["asks_made_silent_by_checks"] == 18
    assert summary["silent_when_answer_existed"] == 12


def test_scoring():
    q = {"id": "x", "from": ["Settle on the 25th"], "says": ["pays sellers on the 25th"]}
    quote = {"quote": "The company pays sellers on the 25th", "verdict": "kept", "commit": "d8ae0f8", "commit_subject": "Settle on the 25th"}
    result = {"quotes": [quote], "silent": False, "model_said_silent": False, "seconds": 1.0}
    assert bench.score(q, result)["right"]
    assert not bench.score(q, result | {"quotes": [quote | {"commit_subject": "wip"}]})["right"]  # the wrong commit
    assert not bench.score(q, result | {"quotes": [quote | {"verdict": "not_found"}]})["right"]
    assert not bench.score(q, result | {"quotes": [quote | {"quote": "The company pays sellers"}]})["right"]
    silent_q = {"id": "y", "silent": True}
    assert not bench.score(silent_q, result)["right"]
    assert bench.score(silent_q, result | {"silent": True, "quotes": []})["right"]


def test_a_comment_counts_as_code(haunted):
    q = next(q for q in QUESTIONS if q["id"] == "round-10-won")
    quote = {"quote": "a multiple of 10 won", "verdict": "kept", "commit": None, "commit_subject": None}
    assert bench.score(q, {"quotes": [quote], "silent": False, "model_said_silent": False, "seconds": 1.0})["right"]


def test_the_table_and_the_readme(haunted, tmp_path):
    results = bench.run(FakeMedium(oracle), haunted, QUESTIONS[:3] + QUESTIONS[-2:], runs=1, log=lambda m: None)
    block = bench.table(bench.summarize(results, 1, 9.87), "gemma4:12b", "Apple M4 Pro, 48 GB", "0.12.6")
    assert block.startswith("| gemma4:12b via Ollama 0.12.6 | Apple M4 Pro, 48 GB |\n|---|---|")
    assert "| Reason found and quoted, when it was written down | 3/3 |" in block
    assert "| Stayed silent, when nobody wrote it down | 2/2 |" in block
    assert "| Loading the model, once | 9.9 s |" in block
    assert block.endswith("Per question: rate-limit 1/1, retries 1/1, round-10-won 1/1, pg-timeout 1/1, vat-round 1/1.")
    readme = tmp_path / "README.md"
    readme.write_text(f"# Pamyo\n\nbefore\n{bench.START}\nold table\n{bench.END}\nafter\n", encoding="utf-8")
    bench.write_readme(block, readme)
    assert readme.read_text(encoding="utf-8") == f"# Pamyo\n\nbefore\n{bench.START}\n{block}\n{bench.END}\nafter\n"

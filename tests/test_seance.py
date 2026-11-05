import pytest
from conftest import FakeMedium, line_of, said

from pamyo import render
from pamyo.model import ModelError
from pamyo.prompts import DEFAULT_QUESTION, seance_prompt
from pamyo.seance import summon, to_json
from pamyo.verify import ECHO, KEPT, NOT_FOUND, THIN

PAYMENT = "orders/payment.py"


def ask(haunted, medium, path, text, question=""):
    n = line_of(haunted, path, text)
    return summon(medium, haunted, path, n, n, question)


def test_the_prompt_holds_the_question_the_code_and_every_commit(haunted):
    medium = FakeMedium(said(silent=True))
    s = ask(haunted, medium, PAYMENT, "MAX_RETRIES = 7", "Why 7 retries?")
    [prompt] = medium.prompts
    assert "QUESTION: Why 7 retries?" in prompt
    assert f"THE CODE BEING ASKED ABOUT (orders/payment.py, line {s.record.start}):\nMAX_RETRIES = 7\n" in prompt
    assert f">> {s.record.start:>2} | MAX_RETRIES = 7" in prompt
    assert f"   {s.record.start + 5:>2} | " in prompt  # the lines around it, unmarked
    for c in s.record.commits:
        assert f"[{c.short}] commit by {c.author} on {c.day}" in prompt
    assert "블프 당일 PG가 504를 계속 줘서" in prompt
    assert "+MAX_RETRIES = 7" in prompt


def test_trimmed_history_is_mentioned_in_the_prompt(make_repo):
    repo = make_repo(*[(f"step {i}", {"knob.py": f"KNOB = {i}\n"}) for i in range(1, 12)])
    medium = FakeMedium()
    summon(medium, repo, "knob.py", 1, 1)
    assert "(3 commits in the middle of this history are left out.)" in medium.prompts[0]


def test_no_question_asks_the_default_one(haunted):
    medium = FakeMedium()
    s = ask(haunted, medium, PAYMENT, "MAX_RETRIES = 7", "   ")
    assert s.question == DEFAULT_QUESTION
    assert f"QUESTION: {DEFAULT_QUESTION}" in medium.prompts[0]
    assert seance_prompt(s.record, "") == medium.prompts[0]


def test_kept_quotes_answer(haunted):
    medium = FakeMedium(said(("블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림.", "ca93d07")))
    s = ask(haunted, medium, PAYMENT, "MAX_RETRIES = 7")
    assert not s.silent and not s.model_said_silent
    assert [c.verdict for c in s.checked] == [KEPT]
    assert s.kept[0].commit.subject == "Black Friday: PG times out under load"
    assert s.model == "fake-medium" and s.seconds >= 0


def test_made_up_words_leave_the_record_silent(haunted):
    s = ask(haunted, FakeMedium(said(("Finance asked for seven.", "ca93d07"))), PAYMENT, "MAX_RETRIES = 7")
    assert s.silent and not s.model_said_silent
    assert [c.verdict for c in s.struck] == [NOT_FOUND]


def test_the_kept_quotes_decide_not_the_model(haunted):
    s = ask(haunted, FakeMedium(said(("PG times out under load", "ca93d07"), silent=True)), PAYMENT, "MAX_RETRIES = 7")
    assert s.model_said_silent and not s.silent


def test_set_aside_quotes_dont_answer(haunted):
    s = ask(haunted, FakeMedium(said(("MAX_RETRIES = 7", "code"), ("fix", "be6e64e"))), PAYMENT, "MAX_RETRIES = 7")
    assert s.silent and [c.verdict for c in s.set_aside] == [ECHO, THIN]


def test_a_model_error_comes_through(haunted):
    with pytest.raises(ModelError):
        ask(haunted, FakeMedium(ModelError("down")), PAYMENT, "MAX_RETRIES = 7")


def test_to_json(haunted):
    medium = FakeMedium(
        said(("PG allows 3 calls a second per merchant key.", "code"), ("block the key for an hour", "de1f835"), ("Ask Kim.", "code"))
    )
    s = ask(haunted, medium, PAYMENT, "time.sleep(0.4)", "Why sleep?")
    out = to_json(s)
    assert out["path"] == PAYMENT and out["lines"] == [s.record.start, s.record.end]
    assert out["question"] == "Why sleep?" and out["model"] == "fake-medium"
    assert out["silent"] is False and out["model_said_silent"] is False and out["commits_seen"] == 1
    comment, message, made_up = out["quotes"]
    assert comment == {
        "quote": "PG allows 3 calls a second per merchant key.",
        "source_named": "code",
        "verdict": "kept",
        "commit": None,
        "commit_subject": None,
        "line": s.record.start - 1,
        "author": "Minsu Park",
        "date": "2019-06-17",
    }
    assert message["commit"] == "de1f835" and message["commit_subject"] == "Stay under the PG rate limit"
    assert made_up["verdict"] == "not_found" and made_up["author"] is None and made_up["date"] is None


def test_render_a_kept_answer(haunted):
    medium = FakeMedium(said(("블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림.", "ca93d07"), ("PG allows 3 calls a second per merchant key.", "code")))
    s = ask(haunted, medium, PAYMENT, "MAX_RETRIES = 7", "Why 7?")
    text = render.ansi(s, color=False)
    assert "\x1b" not in text
    assert text.splitlines()[0] == f"orders/payment.py:{s.record.start}  ·  Why 7?"
    assert f"  {s.record.start} │ MAX_RETRIES = 7" in text
    assert "last touched by Jiyoung Lee, 2020-11-27, ca93d07 “Black Friday: PG times out under load”" in text
    assert "  Jiyoung Lee left these words:\n    “블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림.”" in text
    assert "commit ca93d07, 2020-11-27 · “Black Friday: PG times out under load”" in text
    assert "  Minsu Park left these words:\n    “PG allows 3 calls a second per merchant key.”" in text
    assert "comment at line 13 · 2019-06-17, de1f835 “Stay under the PG rate limit”" in text
    assert "fake-medium" in text and "struck" in text.splitlines()[-1]
    assert "\x1b[1;35m" in render.ansi(s, color=True)


def test_render_silence(haunted):
    s = ask(haunted, FakeMedium(said(("ㅇㅇ", "016c5ae"))), "orders/coupons.py", "FRIENDS = {", "왜 반값이야?")
    text = render.ansi(s, color=False)
    assert "The record is silent. Nobody wrote down why." in text
    assert "1 commit touched these lines, saying “ㅇㅇ”." in text
    assert "(set aside: 1 too short to explain anything)" in text
    assert "left these words" not in text


def test_render_struck_quotes(haunted):
    s = ask(haunted, FakeMedium(said(("Finance asked for seven.", "ca93d07"))), PAYMENT, "MAX_RETRIES = 7")
    text = render.ansi(s, color=False)
    assert "✗ 1 quote struck: not in the record" in text
    assert "    “Finance asked for seven.”  said to be from ca93d07" in text
    assert "3 commits touched these lines, saying “Black Friday: PG times out under load”, “fix”, “Add PG approval”." in text


def test_render_html_escapes(make_repo):
    repo = make_repo(("Guard the PLC", {"plc.py": "LIMIT = 9  # keep it < 10 & the PLC won't overflow\n"}))
    s = summon(FakeMedium(said(("keep it < 10 & the PLC won't overflow", "code"))), repo, "plc.py", 1, 1)
    page = render.html(s)
    assert '<div style="padding-left:5ch;text-indent:-5ch"><span class="quote">    “keep it &lt; 10 &amp; the PLC won&#x27;t overflow”</span></div>' in page
    assert "<script" not in page

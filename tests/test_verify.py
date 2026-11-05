import pytest
from conftest import at, said

from pamyo.history import gather
from pamyo.verify import ECHO, KEPT, NOT_FOUND, THIN, check, norm


@pytest.fixture(scope="module")
def retries(haunted):
    return at(haunted, "orders/payment.py", "MAX_RETRIES = 7")


@pytest.fixture(scope="module")
def sleep(haunted):
    return at(haunted, "orders/payment.py", "time.sleep(0.4)")


def one(record, quote, source="code"):
    [checked] = check(said((quote, source)), record)
    return checked


def test_a_quote_from_a_commit_message_is_kept_and_credited(retries):
    black_friday = retries.commits[0]
    c = one(retries, "블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림.", black_friday.short)
    assert c.verdict == KEPT
    assert c.commit == black_friday and c.author == "Jiyoung Lee"


def test_quote_marks_case_and_spacing_dont_matter(retries):
    c = one(retries, "  “BLACK FRIDAY:   pg times out\nunder load”  ", retries.commits[0].short)
    assert c.verdict == KEPT
    assert c.quote == "BLACK FRIDAY:   pg times out\nunder load"


def test_a_period_more_or_less_doesnt_strike_a_real_quote(haunted, retries):
    r = at(haunted, "orders/payment.py", "timeout=10)")
    assert one(r, "Retry only on 504.", "commit").verdict == KEPT  # the subject has no period
    assert one(retries, "블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림", "commit").verdict == KEPT  # the message has one
    assert one(retries, "블프 당일 PG가 504를 계속 줘서 재시도를 8번으로 늘림", "commit").verdict == NOT_FOUND


def test_a_sentence_broken_over_two_lines_of_the_message_is_found(sleep):
    c = one(sleep, "Go over it and they block the key for an hour; that happened twice on launch day.", "commit")
    assert c.verdict == KEPT and c.commit.subject == "Stay under the PG rate limit"


@pytest.mark.parametrize(
    "made_up",
    [
        "The PG allows 5 calls a second per merchant key.",  # a changed number
        "We sleep to stay under the PG rate limit.",  # a paraphrase
        "On Black Friday the PG kept answering 504, so the retries went up to 7.",  # a translation
        "Legal asked for this.",  # pure invention
    ],
)
def test_anything_not_in_the_record_is_struck(retries, sleep, made_up):
    for record in (retries, sleep):
        c = one(record, made_up, record.commits[0].short)
        assert c.verdict == NOT_FOUND
        assert c.commit is None and c.line is None and c.author == ""


def test_dots_may_skip_words_but_not_reorder_them(retries):
    sha = retries.commits[0].short
    assert one(retries, "블프 당일 PG가 ... 7번으로 늘림", sha).verdict == KEPT
    assert one(retries, "블프 당일 PG가 … 7번으로 늘림", sha).verdict == KEPT  # one ellipsis character
    assert one(retries, "7번으로 늘림 ... 블프 당일 PG가", sha).verdict == NOT_FOUND
    assert one(retries, "...", sha).verdict == NOT_FOUND


def test_a_misnamed_source_is_corrected(retries):
    black_friday, fix, _ = retries.commits
    c = one(retries, "로그 보니 7번째 안에 거의 다 승인됨.", fix.short)
    assert c.verdict == KEPT and c.commit == black_friday


@pytest.mark.parametrize("named", ["commit {sha}", "[{sha}]", "#{sha}", "{long}"])
def test_ways_of_naming_a_commit(retries, named):
    black_friday = retries.commits[0]
    c = one(retries, "PG times out under load", named.format(sha=black_friday.short, long=black_friday.sha))
    assert c.commit == black_friday


def test_a_comment_is_kept_with_its_line_and_who_wrote_it(sleep):
    c = one(sleep, "PG allows 3 calls a second per merchant key.")
    assert c.verdict == KEPT
    assert c.commit is None and c.line == sleep.start - 1
    assert c.author == "Minsu Park" and c.blame.subject == "Stay under the PG rate limit"


def test_a_comment_said_to_be_from_a_commit_is_found_in_the_code(retries):
    c = one(retries, "PG allows 3 calls a second per merchant key.", retries.commits[0].short)
    assert c.verdict == KEPT and c.commit is None
    assert retries.lines[c.line].strip() == "# PG allows 3 calls a second per merchant key."


def test_words_in_both_a_message_and_a_comment_go_where_the_model_said(sleep):
    assert one(sleep, "PG allows 3 calls a second per merchant key.", sleep.commits[0].short).commit == sleep.commits[0]


def test_a_comment_on_the_asked_line_is_not_an_echo(haunted):
    r = at(haunted, "orders/payment.py", "amount = amount // 10 * 10")
    c = one(r, "the PG rejects amounts that aren't a multiple of 10 won")
    assert c.verdict == KEPT and c.line == r.start
    by_commit = one(r, "the PG rejects amounts that aren't a multiple of 10 won", r.commits[0].short)
    assert by_commit.verdict == KEPT and by_commit.commit.subject == "fix"


def test_repeating_the_asked_code_is_set_aside(retries, sleep):
    assert one(retries, "MAX_RETRIES = 7").verdict == ECHO
    assert one(sleep, "time.sleep(0.4)", sleep.commits[0].short).verdict == ECHO


def test_quoting_other_code_is_set_aside(haunted, retries):
    timeout = at(haunted, "orders/payment.py", "timeout=10)")
    assert one(timeout, "if resp.status_code != 504:").verdict == ECHO
    assert one(timeout, 'raise RuntimeError("PG did not answer")').verdict == ECHO
    assert one(retries, "MAX_RETRIES = 5", retries.commits[1].short).verdict == ECHO  # code a commit added


def test_a_docstring_is_words(haunted):
    r = at(haunted, "orders/tax.py", "return round(amount * TAX_RATE)")
    c = one(r, "VAT on orders.")
    assert c.verdict == KEPT and c.line == 1


@pytest.mark.parametrize("label", ["fix", "급함", "ㅇㅇ", "add tax", "wip"])
def test_labels_too_short_to_explain_anything_are_set_aside(haunted, label):
    where = {
        "fix": ("orders/payment.py", "MAX_RETRIES = 7"),
        "급함": ("orders/export.py", 'encoding="cp949"'),
        "ㅇㅇ": ("orders/coupons.py", "FRIENDS = {"),
        "add tax": ("orders/tax.py", "TAX_RATE = 0.1"),
        "wip": ("jobs/settle.py", "time.sleep(1)"),
    }[label]
    c = one(at(haunted, *where), label, "commit")
    assert c.verdict == THIN and c.commit is not None


def test_a_short_korean_warning_is_enough(haunted):
    r = at(haunted, "orders/export.py", 'encoding="cp949"')
    c = one(r, "바꾸지 마세요.", r.commits[0].short)
    assert c.verdict == KEPT and c.author == "Jiyoung Lee"


def test_a_comment_over_several_lines_can_be_quoted_as_one(make_repo):
    repo = make_repo(
        ("Cap retries", {"pay.py": "# Retries are capped at 3 because\n# the bank locks cards after 4 tries.\nRETRIES = 3\n"})
    )
    line = gather(repo, "pay.py", 3, 3)
    c = one(line, "Retries are capped at 3 because the bank locks cards after 4 tries.")
    assert c.verdict == KEPT and c.line == 1
    block = gather(repo, "pay.py", 1, 3)  # now the comment is in the commit's change too
    by_commit = one(block, "Retries are capped at 3 because the bank locks cards", block.commits[0].short)
    assert by_commit.verdict == KEPT and by_commit.commit == block.commits[0]


def test_a_removed_comment_is_credited_to_whoever_wrote_it(make_repo):
    repo = make_repo(
        ("Add the cap", {"cap.py": "CAP = 3  # temporary until the vendor fixes their queue\n"}),
        ("Clean up", {"cap.py": "CAP = 3\n"}),
    )
    r = gather(repo, "cap.py", 1, 1)
    clean_up, add = r.commits
    assert "-CAP = 3  # temporary" in clean_up.diff
    c = one(r, "temporary until the vendor fixes their queue", clean_up.short)
    assert c.verdict == KEPT and c.commit == add  # the lines a commit removed aren't its words


def test_the_same_quote_twice_counts_once(retries):
    sha = retries.commits[0].short
    checked = check(said(("PG times out under load", sha), ("“PG times out under load”", "code"), ("", sha)), retries)
    assert len(checked) == 1


def test_norm():
    assert norm("  “Ｈｅｌｌｏ”\n `World`  ") == '"hello" world'
    assert norm("A … B") == "a ... b"

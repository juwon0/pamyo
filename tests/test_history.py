import subprocess

import pytest
from conftest import at, line_of
from make_haunted_repo import build

from pamyo import history
from pamyo.history import HistoryError, find_repo, gather, git

HAUNTED_HEAD = "e752ac2ac8a6542f8a0e479c5d651e4ac5d579f8"


def test_the_haunted_repository_is_the_same_everywhere(haunted, tmp_path):
    assert git(haunted, "rev-parse", "HEAD").strip() == HAUNTED_HEAD
    assert git(build(tmp_path / "again"), "rev-parse", "HEAD").strip() == HAUNTED_HEAD
    assert len(git(haunted, "log", "--format=%H").split()) == 26


def test_the_haunted_repository_wont_build_over_files(tmp_path):
    (tmp_path / "taken.txt").write_text("mine")
    with pytest.raises(SystemExit):
        build(tmp_path)


def test_gather_reads_every_commit_that_shaped_the_line_newest_first(haunted):
    r = at(haunted, "orders/payment.py", "MAX_RETRIES = 7")
    assert [c.subject for c in r.commits] == ["Black Friday: PG times out under load", "fix", "Add PG approval"]
    assert [c.author for c in r.commits] == ["Jiyoung Lee", "Minsu Park", "Minsu Park"]
    assert r.commits[0].day == "2020-11-27"
    assert r.total_commits == 3
    assert r.target == "MAX_RETRIES = 7"
    assert r.span == str(r.start)


def test_each_commit_shows_its_change_to_the_line(haunted):
    black_friday, fix, _ = at(haunted, "orders/payment.py", "MAX_RETRIES = 7").commits
    assert "-MAX_RETRIES = 5" in black_friday.diff and "+MAX_RETRIES = 7" in black_friday.diff
    assert "+MAX_RETRIES = 5" in fix.diff
    assert "diff --git" not in black_friday.diff  # the hunk only, not git's headers


def test_messages_keep_their_body_and_their_language(haunted):
    r = at(haunted, "orders/export.py", 'encoding="cp949"')
    on_purpose = r.commits[0]
    assert on_purpose.subject == "cp949 is on purpose"
    assert "바꾸지 마세요." in on_purpose.message
    assert on_purpose.message.startswith("cp949 is on purpose\n\n회계팀")


def test_the_window_brings_the_comments_around_the_line(haunted):
    r = at(haunted, "orders/payment.py", "time.sleep(0.4)")
    above = r.start - 1
    assert r.lines[above].strip() == "# PG allows 3 calls a second per merchant key."
    assert r.code[above].strip() == ""  # a comment, so nothing on it runs
    assert r.code[r.start].strip() == "time.sleep(0.4)"
    assert min(r.lines) == r.start - history.WINDOW
    assert max(r.lines) == 19  # the end of the file comes before the end of the window
    top = at(haunted, "orders/payment.py", "MAX_RETRIES = 7")
    assert min(top.lines) == 1  # the window stops at the top of the file
    assert top.lines[1].startswith('"""') and top.code[1] == ""  # the module docstring is words, not code


def test_blame_says_who_last_touched_each_line(haunted):
    r = at(haunted, "orders/payment.py", "MAX_RETRIES = 7")
    last = r.blame[r.start]
    assert (last.author, last.subject, last.day) == ("Jiyoung Lee", "Black Friday: PG times out under load", "2020-11-27")
    assert last.date == "2020-11-27T23:58:00+09:00"
    assert set(r.blame) == set(r.lines)


def test_a_range_of_lines(haunted):
    start = line_of(haunted, "orders/users.py", "if user_id == 1043:")
    r = gather(haunted, "orders/users.py", start, start + 1)
    assert r.span == f"{start}-{start + 1}"
    assert r.target.splitlines() == ["    if user_id == 1043:", "        return False"]
    assert r.commits[0].subject == "CS-882: never block customer 1043"


def test_it_reads_what_was_committed_not_the_working_tree(make_repo):
    repo = make_repo(("Add limit", {"limits.py": "LIMIT = 3  # the vendor's cap\n"}))
    (repo / "limits.py").write_text("LIMIT = 99\n")
    r = gather(repo, "limits.py", 1, 1)
    assert r.target == "LIMIT = 3  # the vendor's cap"


def test_a_line_past_the_end(haunted):
    with pytest.raises(HistoryError, match="has 7 lines at HEAD; there is no line 10"):
        gather(haunted, "orders/tax.py", 10, 10)
    with pytest.raises(HistoryError):
        gather(haunted, "orders/tax.py", 0, 1)
    with pytest.raises(HistoryError):
        gather(haunted, "orders/tax.py", 5, 4)


def test_a_file_that_isnt_there(haunted):
    with pytest.raises(HistoryError):
        gather(haunted, "orders/ghost.py", 1, 1)


def test_find_repo(haunted, tmp_path):
    assert find_repo(haunted / "orders" / "payment.py") == haunted.resolve()
    assert find_repo(haunted / "orders") == haunted.resolve()
    with pytest.raises(HistoryError):
        find_repo(tmp_path / "nowhere" / "x.py")
    lonely = tmp_path / "not-a-repo"
    lonely.mkdir()
    if subprocess.run(["git", "-C", str(lonely), "rev-parse"], capture_output=True).returncode != 0:
        with pytest.raises(HistoryError):
            find_repo(lonely)


def test_a_long_history_keeps_its_newest_and_oldest_commits(make_repo):
    repo = make_repo(*[(f"step {i}", {"knob.py": f"KNOB = {i}\n"}) for i in range(1, 12)])
    r = gather(repo, "knob.py", 1, 1)
    assert r.total_commits == 11
    assert [c.subject for c in r.commits] == ["step 11", "step 10", "step 9", "step 8", "step 4", "step 3", "step 2", "step 1"]


def test_long_messages_and_changes_are_cut(make_repo):
    essay = "Why this is the way it is. " * 100
    repo = make_repo(("start", {"big.py": "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"}),
                     (essay, {"big.py": "\n".join(f"x{i} = {i + 1}" for i in range(60)) + "\n"}))
    newest = gather(repo, "big.py", 1, 60).commits[0]
    assert len(newest.message) < len(essay)
    assert newest.message.endswith("(rest of the message cut)")
    assert newest.diff.splitlines()[-1] == "(rest of the change cut)"
    assert len(newest.diff.splitlines()) == history.MAX_DIFF_LINES + 1

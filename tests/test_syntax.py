from pamyo.syntax import code_parts, unmark


def test_python_comments_go_and_floor_division_stays():
    assert code_parts(["amount = amount // 10 * 10  # the PG wants tens"], "a.py") == ["amount = amount // 10 * 10  "]


def test_a_hash_inside_a_string_is_not_a_comment():
    assert code_parts(['tag = "#launch"  # campaign tag', "s = 'it''s'  # x"], "a.py") == ['tag = "#launch"  ', "s = 'it''s'  "]


def test_python_docstrings_are_words_not_code():
    lines = ['"""Card payments.', "", "Talks to the PG.", '"""', "", "def f():", '    """VAT on orders."""', "    return 1"]
    assert code_parts(lines, "pay.py") == ["", "", "", "", "", "def f():", "    ", "    return 1"]


def test_a_docstring_opened_above_is_followed_down():
    lines = ["'''", "Retry 7 times: the bank locks cards after 8.", "'''", "RETRIES = 7"]
    assert code_parts(lines, "a.py")[1:] == ["", "", "RETRIES = 7"]


def test_c_like_comments():
    assert code_parts(["let n = 3; // vendor cap", "/* old", "   note */ go();", 'url("http://x")'], "a.ts") == [
        "let n = 3; ",
        "",
        " go();",
        'url("http://x")',
    ]


def test_sql_and_shell():
    assert code_parts(["SELECT 1 -- warm the cache"], "q.sql") == ["SELECT 1 "]
    assert code_parts(["sleep 5  # let the disk settle"], "run.sh") == ["sleep 5  "]
    assert code_parts(["FROM python:3.12  # 3.13 breaks the driver"], "Dockerfile") == ["FROM python:3.12  "]


def test_an_unknown_language_takes_both_kinds_of_comment():
    assert code_parts(["x # one", "y // two"], "weird.xyz") == ["x ", "y "]


def test_unmark():
    assert unmark("    # PG allows 3 calls") == "PG allows 3 calls"
    assert unmark("  // vendor cap") == "vendor cap"
    assert unmark("   * keep it") == "keep it"
    assert unmark("-- warm") == "warm"
    assert unmark("x = 1  # not at the start") == "x = 1  # not at the start"

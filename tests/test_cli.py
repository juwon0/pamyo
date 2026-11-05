import json

import pytest
from conftest import FakeMedium, line_of, said

from pamyo import cli, config
from pamyo.model import ModelError


@pytest.fixture
def medium(monkeypatch):
    fake = FakeMedium(said(("블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림.", "ca93d07")))
    made = []

    def ollama_medium(client, model):
        made.append((str(client.base_url).rstrip("/"), model))
        return fake

    monkeypatch.setattr(cli, "OllamaMedium", ollama_medium)
    fake.made = made
    return fake


def test_json_out(haunted, medium, capsys):
    n = line_of(haunted, "orders/payment.py", "MAX_RETRIES = 7")
    assert cli.main(["why", f"{haunted}/orders/payment.py:{n}", "Why", "7", "retries?", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["path"] == "orders/payment.py" and out["lines"] == [n, n]
    assert out["question"] == "Why 7 retries?"
    assert out["quotes"][0]["verdict"] == "kept" and out["silent"] is False
    assert medium.made == [(config.OLLAMA_URL.rstrip("/"), config.MODEL)]


def test_model_and_address_flags(haunted, medium, capsys):
    cli.main(["why", f"{haunted}/orders/payment.py:8", "--model", "gemma4:12b", "--ollama", "http://10.0.0.5:11434", "--json"])
    assert medium.made == [("http://10.0.0.5:11434", "gemma4:12b")]


def test_paths_relative_to_the_repo_or_to_where_you_are(haunted, medium, capsys, monkeypatch):
    assert cli.main(["why", "orders/payment.py:8", "--repo", str(haunted), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == "orders/payment.py"
    monkeypatch.chdir(haunted / "orders")
    assert cli.main(["why", "payment.py:8-9", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["path"] == "orders/payment.py" and out["lines"] == [8, 9]


def test_plain_text_when_not_a_terminal(haunted, medium, capsys):
    assert cli.main(["why", f"{haunted}/orders/payment.py:8"]) == 0
    out = capsys.readouterr().out
    assert "Jiyoung Lee left these words:" in out and "\x1b[" not in out


def test_a_target_without_a_line(medium, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["why", "orders/payment.py"])
    assert exc.value.code == 2
    assert "expected PATH:LINE or PATH:START-END" in capsys.readouterr().err


def test_history_problems_exit_1(haunted, tmp_path, medium, capsys):
    assert cli.main(["why", f"{haunted}/orders/payment.py:400"]) == 1
    assert "pamyo: orders/payment.py has 19 lines at HEAD" in capsys.readouterr().err
    assert cli.main(["why", f"{tmp_path}/nowhere/x.py:1"]) == 1
    assert "does not exist" in capsys.readouterr().err
    assert medium.prompts == []


def test_a_silent_model_exits_2_and_says_what_to_check(haunted, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaMedium", lambda client, model: FakeMedium(ModelError("gemma4:e4b: ConnectError")))
    assert cli.main(["why", f"{haunted}/orders/payment.py:8"]) == 2
    err = capsys.readouterr().err
    assert config.MODEL_DOWN in err and "ConnectError" in err

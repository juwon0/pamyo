# 🪦 Pamyo (파묘)

**Ask the developer who left why the code is like that.**

Every codebase has a line nobody dares to touch: `MAX_RETRIES = 7`, `encoding="cp949"`, `if user_id == 1043: return
False`. Whoever knew why left years ago. Pamyo digs up what they left behind in git (commit messages, the lines they
changed, the comments nearby) and lets an open-weight model on your own computer answer *in their own words only*.
Every quote is looked up in git again before it is shown. Words the model made up are struck out, and when nobody ever
wrote down why, Pamyo says so instead of guessing.

*파묘* (pamyo) means exhuming a grave. Koreans also say it for digging up something long buried, like a post from
years ago, and it is the title of a 2024 Korean horror film. Built for the
[Hacktoberfest 2026 "Ghost in the Machine" challenge](https://dev.to/challenges/hacktoberfest-week4-2026-10-26):
something spooky, or something that honors the past. Pamyo is a séance for a codebase, and the dead may only say what
they really said.

## Why it exists

- `git blame` tells you who and when. The why is often in git too, but scattered over commits from years ago, in
  someone else's shorthand and sometimes someone else's language. Reading thirty commits to find it takes an afternoon.
- A model can read them for you, but models fill a silence with a plausible story, and a plausible wrong reason for
  "can I delete this?" is worse than none. So the model only picks quotes, and Pamyo checks them.
- It is company code. It should not go to a cloud API. The model runs on your machine through Ollama, and the code and
  its history go to `localhost` and nowhere else.

## What it looks like

<!-- demo:start -->
Not recorded yet. With Ollama running, this records `docs/demo.gif` and writes the answers here:
`uv run --with playwright --with pillow python scripts/record_demo.py --model gemma4:12b --readme`
<!-- demo:end -->

## How it works

```
pamyo why orders/export.py:10 "Can I switch this to UTF-8?"
 ├─ git log -L   every commit that changed those lines: its message and its change (newest 4 and oldest 4 at most)
 ├─ git blame    who last touched each line, and the 12 lines around for comments
 ├─ Gemma 4 on Ollama: quote the sources exactly, name each quote's source, or say the record is silent
 └─ every quote is looked up in git again
      in a commit message, the lines a commit added, or a comment or docstring  → kept, credited to who wrote it
      nowhere (changed, translated, paraphrased, invented)                      → struck, shown crossed out
      only code, the asked lines or the code around them                        → set aside: code says what, not why
      too short to explain anything ("fix", "wip", "ㅇㅇ", "급함")                → set aside
   no quote kept → "The record is silent. Nobody wrote down why."
```

- Found means found after evening out whitespace, quote marks and letter case. "..." may skip words if the pieces stay
  in order. A commit's words are its message and the lines it added: lines it deleted were somebody else's.
- A quote credited to the wrong commit is credited to the right one. The model doesn't decide silence either: a real
  quote counts even if the model said "silent", and talking doesn't count unless a quote survives.
- `pamyo/model.py` asks Ollama for JSON that must match a schema (`/api/chat`, thinking off, temperature 0). Where the
  runtime refuses structured output (Homebrew's Ollama runs Gemma 4 on MLX and answers 501), the schema moves into the
  prompt and validation still applies.
- `pamyo/history.py` reads git, `pamyo/verify.py` checks the quotes, `pamyo/syntax.py` tells comments from code by
  the file extension (`#`, `//`, `/* */`, `--` and Python docstrings), `pamyo/render.py` prints the answer.

## Try it

macOS or Linux with about 10 GB free:

```bash
git clone https://github.com/juwon0/pamyo && cd pamyo
bash scripts/first_run.sh
```

It installs Ollama if needed (Homebrew on a Mac), pulls `gemma4:12b` (or `gemma4:e4b` under 16 GB of memory), builds
the haunted repository and asks it three questions.

On your own code:

```bash
uv tool install .                                   # once: puts `pamyo` on your PATH
cd ~/work/billing
export PAMYO_MODEL=gemma4:12b                       # default gemma4:e4b
pamyo why src/invoice.py:120
pamyo why src/invoice.py:118-124 "왜 여기서 반올림해?"   # any language
pamyo why src/invoice.py:120 --json                 # for scripts
```

Options: `--model`, `--ollama` (default `http://127.0.0.1:11434`, or `OLLAMA_URL`), `--repo`, `--json`,
`--no-color`. Line numbers are those of the file as committed at `HEAD`.

## The haunted repository

`scripts/make_haunted_repo.py` builds `dalbit-orders`, the order service of 달빛상회 (Moonlight Trading), a made-up
Korean online shop: 26 commits from 2019 to 2023 by three developers who have all left, in English and Korean. Some
lines have their reason written down: a payment gateway's rate limit, Black Friday timeouts, Excel 2003's 65,536 rows,
a customer's order for her mother's memorial rite (제사). Others were committed as "fix", "ㅇㅇ", "asdf" or "wip", and
nobody will ever know. Every person, ticket and number in it is made up, and it builds the same commits, hashes
included, on every machine (`HEAD` e752ac2).

## Accuracy and speed

`bench/questions.json` asks 18 questions about the haunted repository: 12 whose reason is written down somewhere and 6
where nobody wrote it down. Two of the six are traps: the commit that last changed a 10-second timeout talks only about
504 retries, and the VAT function's docstring says what it is but not why it rounds.

<!-- bench:start -->
Not measured yet. With Ollama running, this writes the table here:
`uv run python scripts/bench.py --model gemma4:12b --readme`
<!-- bench:end -->

`scripts/bench.py` asks every question three times. An answerable question counts as right when a kept quote comes
from the commit or comment that holds the reason and contains the reason (`says` in the questions file); an
unanswerable one, when Pamyo stays silent. The repository and the questions come from the same project and the
repository is small and tidy, so read the numbers as a check of the pipeline on known ground, not as a benchmark of
the model. `scripts/record_demo.py` records `docs/demo.gif` with the real model and keeps its exact answers in
`docs/demo-answers.json`; `--replay` draws the GIF again from them.

## Tests

```bash
uv run pytest
```

The tests use a fake model, so they run without Ollama: reading git history, telling comments from code, every rule in
`verify.py`, the request sent to Ollama and the 501 fallback, the CLI, and the bench's scoring (a perfect fake model
scores full marks; a lying one gets every quote struck).

## Limits

- It only finds reasons that someone wrote down in git. A Slack thread or a ticket stays out of reach; a ticket number
  in a message is shown, not followed.
- A kept quote is real, but it can still be beside the point. That is the model's judgment, and the bench counts how
  often it goes wrong.
- For a line with a long history, the model sees the 4 newest and 4 oldest commits; the prompt says how many were
  left out.

## Credits

- The Ollama request handling (schema fallback, code-fence trimming, the warmer retry) is adapted from my earlier
  Hacktoberfest projects [Chumsak](https://github.com/juwon0/chumsak) and [Jeongsan](https://github.com/juwon0/jeongsan), MIT.
- [Gemma 4](https://ai.google.dev/gemma) by Google DeepMind, served by [Ollama](https://ollama.com).

MIT License.

"""Records docs/demo.gif: three questions about the haunted repository, answered by the real model.

    uv run --with playwright --with pillow python scripts/record_demo.py --model gemma4:12b   # Ollama running
    uv run --with playwright --with pillow python scripts/record_demo.py --replay docs/demo-answers.json --readme

Live, it builds the haunted repository, asks the model through Ollama, and keeps exactly what the model answered,
and how long that took, in docs/demo-answers.json. Each screen is the CLI's own output (pamyo/render.py) drawn as a
terminal page in the installed Google Chrome, or Playwright's Chromium, and kept as one GIF frame: the GIF shows
every step rather than every second, and the real timings are on screen. --replay draws the GIF again from that
file without a model. The saved answers go through the same checks again, so nothing on screen is made up.
--readme also writes the three answers as plain text between the demo markers in README.md.
"""

import argparse
import dataclasses
import html
import io
import json
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from bench import load_model, load_questions, locate, ollama_version  # noqa: E402
from make_haunted_repo import build  # noqa: E402

from pamyo import config, render  # noqa: E402
from pamyo.history import git  # noqa: E402
from pamyo.model import OllamaMedium  # noqa: E402
from pamyo.schemas import Answer  # noqa: E402
from pamyo.seance import Seance, summon  # noqa: E402

DEMO_START, DEMO_END = "<!-- demo:start -->", "<!-- demo:end -->"

WIDTH, HEIGHT = 1000, 600
# (question id in bench/questions.json, what the viewer is told before the answer)
DEMO = [
    ("cp949", "Someone wants to switch the accounting export to UTF-8. Ask first."),
    ("customer-1043", "One customer can never be blocked. A bug, or a promise?"),
    ("welcome2020", "A 2020 coupon still takes half off. Asked in Korean this time."),
]

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; width: %dpx; height: %dpx; display: flex; flex-direction: column; background: #16141f; color: #e8e4f2;
  font: 15px/1.55 Menlo, "SF Mono", "DejaVu Sans Mono", "Apple SD Gothic Neo", "Noto Sans Mono CJK KR", "WenQuanYi Zen Hei Mono", monospace; }
.bar { flex: none; height: 34px; display: flex; align-items: center; gap: 8px; padding: 0 14px; background: #25222f; color: #8f8aa3; font-size: 13px; }
.bar i { width: 12px; height: 12px; border-radius: 50%%; display: inline-block; }
.bar span { margin-left: 10px; }
.term { flex: 1; min-height: 0; padding: 14px 22px; overflow: hidden; } .term div { white-space: pre-wrap; }
.caption { flex: none; padding: 13px 22px; background: #3a2d5c; color: #fff; font: 600 17px/1.4 -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif; }
.prompt { color: #7ee787; } .cmd { color: #ffffff; } .cursor { background: #e8e4f2; }
.dim { color: #8f8aa3; } .code { color: #79c0ff; } .ghost { color: #d2a8ff; font-weight: 700; }
.quote { color: #ffffff; font-weight: 700; } .warn { color: #e3b341; } .struck { color: #8f8aa3; text-decoration: line-through; }
.silent { color: #a5d6ff; font-weight: 700; } .wait { color: #e3b341; }
.title { flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 0 70px; font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, "Apple SD Gothic Neo", "WenQuanYi Zen Hei", sans-serif; }
.title h1 { margin: 0 0 18px; font-size: 54px; color: #fff; } .title h1 em { font-style: normal; color: #d2a8ff; }
.title p { margin: 0 0 14px; font-size: 23px; color: #e8e4f2; } .title .small { font-size: 18px; color: #8f8aa3; }
.title ul { margin: 6px 0 0; padding-left: 22px; font-size: 20px; color: #e8e4f2; } .title li { margin-bottom: 8px; }
""" % (WIDTH, HEIGHT)

BAR = '<div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span>{}</span></div>'


def page(body: str, caption: str, title: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
        f"{BAR.format(html.escape(title))}{body}<div class=\"caption\">{html.escape(caption)}</div></body></html>"
    )


def terminal(command: str, output: str = "", typed: int | None = None, waiting: str = "") -> str:
    shown = command if typed is None else command[:typed]
    line = f'<div><span class="prompt">~/dalbit-orders $</span> <span class="cmd">{html.escape(shown)}</span>'
    line += '<span class="cursor"> </span></div>' if typed is not None else "</div>"
    if waiting:
        line += f'<div class="wait">{html.escape(waiting)}</div>'
    return f'<div class="term">{line}{output}</div>'


def command_for(s: Seance) -> str:
    return f'pamyo why {s.record.path}:{s.record.span} "{s.question}"'


def caption_after(s: Seance) -> str:
    """What the screen shows, in one line, from the result itself."""
    struck = f" {len(s.struck)} made-up {'quote' if len(s.struck) == 1 else 'quotes'} struck." if s.struck else ""
    if s.silent:
        if s.model_said_silent:
            return "Nobody wrote down why, so Pamyo says so instead of guessing." + struck
        return "The model offered words, but none was a reason found in git, so the record stays silent." + struck
    who = sorted({c.author for c in s.kept if c.author})
    years = sorted({(c.commit.day if c.commit else c.blame.day if c.blame else "")[:4] for c in s.kept} - {""})
    shown = " and ".join(who) or "the developers"
    return f"{shown}'s own words from {', '.join(years) or 'git'}, each found in git before it was shown." + struck


class Keeping:
    """Passes the question to the real model and keeps exactly what it answered."""

    def __init__(self, medium: OllamaMedium) -> None:
        self.medium = medium
        self.model = medium.model
        self.answers: list[Answer] = []

    def ask(self, prompt: str) -> Answer:
        self.answers.append(self.medium.ask(prompt))
        return self.answers[-1]


@dataclasses.dataclass
class Replaying:
    model: str
    answer: Answer

    def ask(self, prompt: str) -> Answer:
        return self.answer


def ask_live(repo: Path, model: str, ollama: str) -> tuple[list[Seance], dict]:
    questions = {q["id"]: q for q in load_questions()}
    with httpx.Client(base_url=ollama, timeout=httpx.Timeout(600, connect=5)) as client:
        version = ollama_version(client)
        print(f"Loading {model} on Ollama {version or '(version unknown)'} ...", flush=True)
        load_seconds = load_model(client, model)
        keeping = Keeping(OllamaMedium(client, model))
        seances, asks = [], []
        for qid, _ in DEMO:
            q = questions[qid]
            n = locate(repo, q)
            s = summon(keeping, repo, q["file"], n, n, q["ask"])
            print(f"  {qid}: {s.seconds:.1f} s, kept {len(s.kept)}, struck {len(s.struck)}, silent {s.silent}", flush=True)
            seances.append(s)
            asks.append({"id": qid, "path": q["file"], "line": n, "question": q["ask"], "seconds": round(s.seconds, 2),
                         "answer": keeping.answers[-1].model_dump()})
    saved = {
        "model": model,
        "ollama": version,
        "structured_output": not keeping.medium.schema_in_prompt,
        "load_seconds": round(load_seconds, 1),
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "asks": asks,
    }
    return seances, saved


def replay(repo: Path, saved: dict) -> list[Seance]:
    head = git(repo, "rev-parse", "HEAD").strip()
    if head != saved["head"]:
        raise SystemExit(f"The haunted repository is at {head}, the answers were given at {saved['head']}")
    seances = []
    for a in saved["asks"]:
        medium = Replaying(saved["model"], Answer.model_validate(a["answer"]))
        s = summon(medium, repo, a["path"], a["line"], a["line"], a["question"])
        seances.append(dataclasses.replace(s, seconds=a["seconds"]))
    return seances


def screens(seances: list[Seance], saved: dict) -> list[tuple[str, int]]:
    """(html, milliseconds) for every frame."""
    model = saved["model"]
    bar = f"~/dalbit-orders · PAMYO_MODEL={model}"
    intro = (
        '<div class="title"><h1>Pamyo <em>파묘</em></h1>'
        "<p>Ask the developer who left why the code is like that.</p>"
        f'<p class="small">{html.escape(model)} runs on this machine through Ollama. It may answer only with words the '
        "developers left in git: commit messages, the lines they added, comments. Pamyo checks every quote against git "
        "before showing it.</p></div>"
    )
    frames = [(page(intro, "A haunted repository: a shop's order service, five years of commits, everyone gone.", bar), 4200)]
    captions = dict(DEMO)
    for s, a in zip(seances, saved["asks"], strict=True):
        command = command_for(s)
        frames.append((page(terminal(command, typed=len(command) * 2 // 5), captions[a["id"]], bar), 900))
        frames.append((page(terminal(command, typed=len(command)), captions[a["id"]], bar), 1500))
        waiting = f"asking {model} on this machine…"
        frames.append((page(terminal(command, waiting=waiting), "The code and its history go to Ollama on localhost and nowhere else. The wait is cut short here.", bar), 1300))
        frames.append((page(terminal(command, render.html(s)), caption_after(s), bar), 6500))
    outro = (
        '<div class="title"><h1>Pamyo <em>파묘</em></h1><ul>'
        "<li>Quotes the model made up are struck, not shown as answers.</li>"
        "<li>When nobody wrote down why, it says the record is silent.</li>"
        "<li>Your code never leaves your machine.</li></ul></div>"
    )
    frames.append((page(outro, "github.com/juwon0/pamyo · MIT", bar), 4500))
    return frames


def as_text(seances: list[Seance]) -> str:
    """The three answers as the CLI prints them without color, each under its command."""
    blocks = [f"$ {command_for(s)}\n{render.ansi(s, color=False)}" for s in seances]
    return "```text\n" + "\n\n".join(blocks) + "\n```"


def write_readme(block: str, readme: Path = ROOT / "README.md") -> None:
    text = readme.read_text(encoding="utf-8")
    head, rest = text.split(DEMO_START, 1)
    _, tail = rest.split(DEMO_END, 1)
    readme.write_text(f"{head}{DEMO_START}\n{block}\n{DEMO_END}{tail}", encoding="utf-8")


def launch(p, browser: str | None):
    if browser:
        return p.chromium.launch(executable_path=browser)
    try:
        return p.chromium.launch(channel="chrome")
    except PlaywrightError:
        return p.chromium.launch()  # Playwright's Chromium, if `playwright install chromium` was run


def draw(frames: list[tuple[str, int]], out: Path, browser: str | None, keep_frames: Path | None) -> None:
    images = []
    with sync_playwright() as p:
        b = launch(p, browser)
        tab = b.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        for i, (markup, _) in enumerate(frames, 1):
            tab.set_content(markup)
            tab.evaluate("document.fonts.ready")
            # A long answer shrinks the type until it fits, rather than being cut off at the bottom.
            size = tab.evaluate("""() => {
                const term = document.querySelector('.term');
                let size = 15;
                while (term && term.scrollHeight > term.clientHeight && size > 10) {
                    size -= 0.5;
                    term.style.fontSize = size + 'px';
                }
                return size;
            }""")
            if size < 15:
                print(f"  frame {i}: type shrunk to {size}px to fit", flush=True)
            shot = Image.open(io.BytesIO(tab.screenshot())).convert("RGB")
            if keep_frames:
                keep_frames.mkdir(parents=True, exist_ok=True)
                shot.save(keep_frames / f"frame-{i:02d}.png")
            images.append(shot)
        b.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    gif = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in images]
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=config.MODEL)
    parser.add_argument("--ollama", default=config.OLLAMA_URL)
    parser.add_argument("--replay", type=Path, help="draw from saved answers instead of asking the model")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "demo.gif")
    parser.add_argument("--answers", type=Path, default=ROOT / "docs" / "demo-answers.json", help="where live answers are kept")
    parser.add_argument("--browser", help="path to a Chrome or Chromium binary (default: the installed Google Chrome)")
    parser.add_argument("--frames", type=Path, help="also save every frame as a PNG in this folder")
    parser.add_argument("--readme", action="store_true", help="write the answers as text into README.md")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="pamyo-demo-") as tmp:
        repo = build(Path(tmp) / "dalbit-orders")
        if args.replay:
            saved = json.loads(args.replay.read_text(encoding="utf-8"))
            seances = replay(repo, saved)
        else:
            seances, saved = ask_live(repo, args.model, args.ollama)
            args.answers.parent.mkdir(parents=True, exist_ok=True)
            args.answers.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        frames = screens(seances, saved)
        draw(frames, args.out, args.browser, args.frames)
        if args.readme:
            write_readme(as_text(seances))

    print(json.dumps({
        "gif": str(args.out),
        "bytes": args.out.stat().st_size,
        "frames": len(frames),
        "model": saved["model"],
        "asks": [
            {"id": a["id"], "seconds": a["seconds"], "silent": s.silent, "kept": [c.quote for c in s.kept],
             "struck": [c.quote for c in s.struck], "set_aside": [c.quote for c in s.set_aside]}
            for s, a in zip(seances, saved["asks"], strict=True)
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

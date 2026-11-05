"""Builds the haunted repository: five years of a small Korean online shop's order service, written by people who
have all left.

    python scripts/make_haunted_repo.py /tmp/haunted

Everyone and everything in it is made up: the shop (달빛상회, "Moonlight Trading"), the three developers, the
tickets. Some lines have their reason written down in a commit message or a comment, in English or Korean. Others
were committed with "fix", "ㅇㅇ" or "wip" and nobody will ever know. bench/questions.json asks about both kinds.
The same script always builds the same commits, hashes included.
"""

import os
import subprocess
import sys
from pathlib import Path

MINSU = ("Minsu Park", "minsu.park@dalbit.example")  # 2019-06 to 2022-02
JIYOUNG = ("Jiyoung Lee", "jiyoung.lee@dalbit.example")  # 2020-03 to 2023-08
HANA = ("Hana Choi", "hana.choi@dalbit.example")  # contractor, 2023

README = """# dalbit-orders

Orders, payments, shipping and the monthly export for 달빛상회 (Moonlight Trading).

Everyone who built this has left. Good luck.
"""

PAYMENT_V1 = '''"""Card payments through the PG (payment gateway)."""

import requests

PG_URL = "https://pg.example.com/v1/approve"
MAX_RETRIES = 3


def approve(order_id: str, amount: int) -> dict:
    for _ in range(MAX_RETRIES):
        resp = requests.post(PG_URL, json={"order": order_id, "amount": amount}, timeout=30)
        if resp.ok:
            return resp.json()
    raise RuntimeError("PG did not answer")
'''

EXPORT_V1 = '''"""Monthly order export for the accounting team."""

import csv


def export(orders: list[dict], path: str) -> int:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["주문번호", "날짜", "금액"])
        for order in orders:
            writer.writerow([order["id"], order["date"], order["amount"]])
    return len(orders)
'''

SHIPPING_V1 = '''"""Shipping fees and dispatch days."""

from datetime import datetime, time, timedelta

CUTOFF = time(15, 0)
BASE_FEE = 3000


def fee(postal_code: str) -> int:
    total = BASE_FEE
    return total


def dispatch_day(ordered_at: datetime) -> datetime:
    day = ordered_at if ordered_at.time() < CUTOFF else ordered_at + timedelta(days=1)
    return day
'''

TIMEUTIL_V1 = '''"""Dates the business uses."""

from datetime import datetime


def business_day() -> str:
    return datetime.now().date().isoformat()
'''

TAX = '''"""VAT on orders."""

TAX_RATE = 0.1


def vat(amount: int) -> int:
    return round(amount * TAX_RATE)
'''

COUPONS_V1 = '''"""Coupon codes."""

FRIENDS = {"WELCOME2020"}


def discount(code: str, total: int) -> int:
    if code in FRIENDS:
        return total // 2
    return 0
'''

LUCKY_DRAW = '''

def lucky_draw(entries: list[str]) -> str:
    random.seed(42)
    return random.choice(entries)
'''

USERS_V1 = '''"""Fraud checks on accounts."""

BULK_LIMIT = 30


def is_blocked(user_id: int, items_today: int) -> bool:
    return items_today > BULK_LIMIT
'''

SETTLE_V1 = '''"""Nightly settlement for sellers."""

import time
from datetime import date


def should_settle(today: date) -> bool:
    return True


def run(today: date) -> None:
    time.sleep(1)
    if not should_settle(today):
        return
    print("settling", today.isoformat())
'''

# (author, author date, message, files to write, edits as (path, old, new))
HISTORY = [
    (MINSU, "2019-06-03T10:12:00+09:00", "Initial commit", {"README.md": README, "requirements.txt": "requests==2.22.0\n"}, []),
    (MINSU, "2019-06-03T15:40:00+09:00", "Add PG approval", {"orders/payment.py": PAYMENT_V1}, []),
    (MINSU, "2019-06-03T17:05:00+09:00", "Add timeutil", {"orders/timeutil.py": TIMEUTIL_V1}, []),
    (
        MINSU,
        "2019-06-17T11:20:00+09:00",
        "Stay under the PG rate limit\n\n"
        "The PG allows 3 calls a second per merchant key. Go over it and they block the key for an hour;\n"
        "that happened twice on launch day. 0.4 s keeps us under it with room for the retries.",
        {},
        [
            ("orders/payment.py", '"""\n\nimport requests', '"""\n\nimport time\n\nimport requests'),
            (
                "orders/payment.py",
                "    for _ in range(MAX_RETRIES):",
                "    # PG allows 3 calls a second per merchant key.\n    time.sleep(0.4)\n    for _ in range(MAX_RETRIES):",
            ),
        ],
    ),
    (MINSU, "2019-06-20T09:30:00+09:00", "add tax", {"orders/tax.py": TAX}, []),
    (MINSU, "2019-07-01T14:00:00+09:00", "Add shipping rules", {"orders/shipping.py": SHIPPING_V1}, []),
    (
        MINSU,
        "2019-07-08T16:45:00+09:00",
        "Jeju and island surcharge\n\n"
        "Jeju postal codes all start with 63 since the five-digit codes of 2015.\n"
        "Islands cost the courier extra and they pass it on to us.",
        {},
        [
            ("orders/shipping.py", "BASE_FEE = 3000\n", "BASE_FEE = 3000\nISLAND_FEE = 2500\n"),
            (
                "orders/shipping.py",
                "    total = BASE_FEE\n",
                '    total = BASE_FEE\n    if postal_code.startswith("63"):\n        total += ISLAND_FEE\n',
            ),
        ],
    ),
    (MINSU, "2019-08-01T13:10:00+09:00", "Add monthly export for accounting", {"orders/export.py": EXPORT_V1}, []),
    (MINSU, "2019-08-05T18:52:00+09:00", "급함", {}, [("orders/export.py", 'encoding="utf-8"', 'encoding="cp949"')]),
    (
        MINSU,
        "2019-08-21T10:03:00+09:00",
        "fix",
        {},
        [
            (
                "orders/payment.py",
                "def approve(order_id: str, amount: int) -> dict:\n",
                "def approve(order_id: str, amount: int) -> dict:\n"
                "    amount = amount // 10 * 10  # the PG rejects amounts that aren't a multiple of 10 won\n",
            )
        ],
    ),
    (
        MINSU,
        "2019-09-09T09:15:00+09:00",
        "Move the cutoff to 14:30\n\nCJ moved our pickup from 16:00 to 15:00, and packing takes about 30 minutes.",
        {},
        [("orders/shipping.py", "CUTOFF = time(15, 0)", "CUTOFF = time(14, 30)")],
    ),
    (MINSU, "2019-11-29T22:41:00+09:00", "fix", {}, [("orders/payment.py", "MAX_RETRIES = 3", "MAX_RETRIES = 5")]),
    (MINSU, "2020-01-02T11:11:00+09:00", "ㅇㅇ", {"orders/coupons.py": COUPONS_V1}, []),
    (
        MINSU,
        "2020-01-10T15:30:00+09:00",
        "Cap export rows\n\n"
        "Accounting still opens these in Excel 2003 (.xls), which stops at 65,536 rows. January had\n"
        "71,204 orders and the rows past the limit silently disappeared from the ledger.\n"
        "Split the month if this ever gets close.",
        {},
        [
            ("orders/export.py", "import csv\n", "import csv\n\nMAX_ROWS = 65000\n"),
            (
                "orders/export.py",
                "        for order in orders:\n",
                "        rows = orders[:MAX_ROWS]\n        for order in rows:\n",
            ),
            ("orders/export.py", "    return len(orders)", "    return len(rows)"),
        ],
    ),
    (
        MINSU,
        "2020-03-31T19:20:00+09:00",
        "Use KST for business dates\n\n"
        "The servers run in UTC, so every order placed between midnight and 9 a.m. KST landed on the\n"
        "previous day in the reports. Accounting found it at the end of the quarter.",
        {},
        [
            (
                "orders/timeutil.py",
                "from datetime import datetime\n",
                "from datetime import datetime, timedelta, timezone\n\nKST = timezone(timedelta(hours=9))\n",
            ),
            ("orders/timeutil.py", "datetime.now().date()", "datetime.now(KST).date()"),
        ],
    ),
    (
        JIYOUNG,
        "2020-04-02T14:25:00+09:00",
        "cp949 is on purpose\n\n"
        "회계팀 PC의 엑셀은 UTF-8 CSV를 열면 한글이 다 깨짐. utf-8-sig도 해봤는데 그 버전에선 안 됨.\n"
        "바꾸지 마세요.",
        {},
        [
            (
                "orders/export.py",
                '    with open(path, "w", newline="", encoding="cp949") as f:',
                "    # 회계팀 엑셀 때문에 cp949 (커밋 메시지 참고)\n"
                '    with open(path, "w", newline="", encoding="cp949", errors="replace") as f:',
            )
        ],
    ),
    (
        JIYOUNG,
        "2020-06-12T11:48:00+09:00",
        "Retry only on 504\n\n"
        "The PG answers 500 when the card is declined. Retrying a declined card five times got one\n"
        "customer's card locked by her bank.",
        {},
        [
            ("orders/payment.py", "timeout=30)", "timeout=10)"),
            ("orders/payment.py", "        if resp.ok:", "        if resp.status_code != 504:"),
        ],
    ),
    (
        JIYOUNG,
        "2020-11-27T23:58:00+09:00",
        "Black Friday: PG times out under load\n\n"
        "블프 당일 PG가 504를 계속 줘서 재시도를 7번으로 늘림. 로그 보니 7번째 안에 거의 다 승인됨.",
        {},
        [("orders/payment.py", "MAX_RETRIES = 5", "MAX_RETRIES = 7")],
    ),
    (JIYOUNG, "2021-02-01T10:00:00+09:00", "update", {}, [("orders/shipping.py", "ISLAND_FEE = 2500", "ISLAND_FEE = 3000")]),
    (
        JIYOUNG,
        "2021-03-02T16:30:00+09:00",
        "Block bulk buyers\n\nResellers buy 100+ items at launch and flip them. 30 a day is more than any real customer buys.",
        {"orders/users.py": USERS_V1},
        [],
    ),
    (
        JIYOUNG,
        "2021-06-11T13:37:00+09:00",
        "CS-882: never block customer 1043\n\n"
        "She bought 40 boxes of rice cakes for her mother's memorial rite (제사) and the bulk rule blocked\n"
        "her in the middle of the order. CS promised her it won't happen again. Don't remove without asking CS.",
        {},
        [
            (
                "orders/users.py",
                "    return items_today > BULK_LIMIT",
                "    if user_id == 1043:\n        return False\n    return items_today > BULK_LIMIT",
            )
        ],
    ),
    (
        MINSU,
        "2021-12-24T17:59:00+09:00",
        "asdf",
        {},
        [
            ("orders/coupons.py", '"""Coupon codes."""\n', '"""Coupon codes."""\n\nimport random\n'),
            ("orders/coupons.py", "    return 0\n", "    return 0\n" + LUCKY_DRAW),
        ],
    ),
    (HANA, "2023-01-10T09:00:00+09:00", "Bump requests", {"requirements.txt": "requests==2.31.0\n"}, []),
    (HANA, "2023-03-02T20:10:00+09:00", "wip", {"jobs/settle.py": SETTLE_V1}, []),
    (
        HANA,
        "2023-03-15T11:00:00+09:00",
        "Settle on the 25th\n\nThe company pays sellers on the 25th, and finance wants the settlement file that morning, not every night.",
        {},
        [("jobs/settle.py", "    return True", "    return today.day == 25")],
    ),
    (
        HANA,
        "2023-05-08T10:30:00+09:00",
        "No dispatch on Sundays\n\nThe warehouse is closed on Sundays from May 2023.",
        {},
        [
            (
                "orders/shipping.py",
                "    return day\n",
                "    while day.weekday() == 6:\n        day += timedelta(days=1)\n    return day\n",
            )
        ],
    ),
]


def build(out: Path, history: list = HISTORY) -> Path:
    """Replays `history` into a new repository at `out`. The tests build small ones the same way."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    base = ["git", "-C", str(out), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-c", "core.autocrlf=false"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_GLOBAL"] = os.devnull  # nobody's own git settings (templates, signing, hooks) in the history
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run([*base, "init", "-q", "-b", "main"], check=True, env=env)
    for (name, email), when, message, files, edits in history:
        for path, text in files.items():
            target = out / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for path, old, new in edits:
            target = out / path
            text = target.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise SystemExit(f"{path}: expected {old!r} once")
            target.write_text(text.replace(old, new), encoding="utf-8")
        who = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": when}
        who |= {"GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": when}
        subprocess.run([*base, "add", "-A"], check=True, env=env)
        subprocess.run([*base, "commit", "-q", "-F", "-"], input=message, text=True, check=True, env=env | who)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(build(Path(sys.argv[1])))

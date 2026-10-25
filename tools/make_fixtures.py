import argparse, json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

F = {}  # id -> (expected_label, window, source)
F["L01"] = ("date_bug", ["2028-02-29", "2028-02-29"], '''from datetime import date

def next_day(today):

    return date(today.year, today.month, today.day + 1)  # BUG: adding one to leap day raises

today = date.today()
if today.month == 2 and today.day == 29:
    assert next_day(today) == date(today.year, 3, 1)
''')
F["L02"] = ("date_bug", ["2028-01-01", "2028-12-31"], '''from datetime import date

def days_left(today):
    return 365 - today.timetuple().tm_yday  # BUG: assumes a 365-day year

t = date.today()
expect = (date(t.year, 12, 31) - t).days
got = days_left(t)
assert got == expect, f"{t}: got {got}, expected {expect}"
''')
F["L03"] = ("date_bug", ["2028-02-29", "2028-02-29"], '''from datetime import datetime

def same_day_last_year(t):
    return datetime.strptime(f"{t.year - 1}-{t.month}-{t.day}", "%Y-%m-%d").date()  # BUG: Feb 29 has no twin

t = datetime.now().date()
assert same_day_last_year(t).year == t.year - 1
''')
F["L04"] = ("date_bug", ["2100-01-01", "2100-12-31"], '''import calendar
from datetime import date

def is_leap(y):
    return y % 4 == 0  # BUG: ignores the century rule

t = date.today()
assert is_leap(t.year) == calendar.isleap(t.year), f"year {t.year}"
''')
F["M01"] = ("date_bug", ["2028-01-30", "2028-01-31"], '''from datetime import date

def add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, d.day)  # BUG: that day may not exist next month

t = date.today()
assert add_month(t) > t
''')
F["M02"] = ("date_bug", ["2027-12-01", "2027-12-31"], '''from datetime import date

def first_of_next_month(d):
    return date(d.year, d.month + 1, 1)  # BUG: month 13 in December

t = date.today()
assert first_of_next_month(t) > t
''')
F["M03"] = ("date_bug", ["2027-02-01", "2200-02-28"], '''import calendar
from datetime import date

def last_day(t):
    return 31 if t.month in (1, 3, 5, 7, 8, 10, 12) else 30  # BUG: February

t = date.today()
assert last_day(t) == calendar.monthrange(t.year, t.month)[1], str(t)
''')
F["M04"] = ("date_bug", ["2028-02-29", "2028-11-30"], '''import calendar
from datetime import date

def billing_due(t, billing_day=31):
    return t.day == billing_day  # BUG: short months never reach day 31

t = date.today()
if t.day == calendar.monthrange(t.year, t.month)[1]:
    assert billing_due(t), f"{t}: last day of month but not due"
''')
F["E01"] = ("date_bug", ["2028-06-01", "2028-06-01"], '''from datetime import datetime

EXPIRES = datetime(2028, 6, 1)
now = datetime.now()

def token_valid(n):
    return n.date() <= EXPIRES.date()  # BUG: token is already expired on its expiry day

assert token_valid(now) == (now < EXPIRES), f"{now:%Y-%m-%d}"
''')
F["E02"] = ("date_bug", ["2038-01-19", "2200-12-31"], '''import time

ts = int(time.time())
packed = ts if ts < 2**31 else None  # BUG: epoch seconds stored in a signed 32-bit field
assert packed is not None, f"timestamp {ts} overflows int32"
''')
F["E03"] = ("date_bug", ["2028-03-01", "2028-03-01"], '''from datetime import date

LICENSE_END = date(2028, 3, 1)

def expired(t):
    return t >= LICENSE_END  # BUG: license is valid through its end date

t = date.today()
assert expired(t) == (t > LICENSE_END), str(t)
''')
F["E04"] = ("date_bug", ["2069-01-01", "2200-12-31"], '''from datetime import date, datetime

t = date.today()
packed = t.strftime("%d/%m/%y")
back = datetime.strptime(packed, "%d/%m/%y").date()  # BUG: two-digit year pivots at 2069
assert back == t, f"{t} -> {packed} -> {back}"
''')
F["C02"] = ("clean", None, '''import calendar
from datetime import date

def add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

t = date.today()
n = add_month(t)
assert n > t and (n.year * 12 + n.month) - (t.year * 12 + t.month) == 1
''')
F["C03"] = ("clean", None, '''import calendar
from datetime import date

def days_left(today):
    return (date(today.year, 12, 31) - today).days

t = date.today()
total = 366 if calendar.isleap(t.year) else 365
assert days_left(t) + t.timetuple().tm_yday == total
assert 28 <= calendar.monthrange(t.year, t.month)[1] <= 31
''')
F["C04"] = ("clean", None, '''import time
from datetime import datetime, timezone

ts = int(time.time())
back = datetime.fromtimestamp(ts, tz=timezone.utc)
assert int(back.timestamp()) == ts
assert back.year >= 1970
''')
F["F01"] = ("not_date_bug", None, '''import random, sys

if random.random() < 0.3:
    sys.exit("random failure unrelated to the date")
''')
F["F02"] = ("not_date_bug", None, '''import os

print(os.environ["REQUIRED_API_URL"])
''')
F["F03"] = ("not_date_bug", None, '''import time

assert time.time_ns() % 3 != 0, "timing race, not a date bug"
''')
F["F04"] = ("not_date_bug", None, '''from datetime import date

assert date.today().year == 1999, "wrong assertion on every date"
''')
F["C01"] = ("clean", None, '''from datetime import date

def next_anniversary(today):
    try:
        return date(today.year + 1, today.month, today.day)
    except ValueError:
        return date(today.year + 1, 2, 28)

today = date.today()
if today.month == 2 and today.day == 29:
    assert next_anniversary(today) == date(today.year + 1, 2, 28)
''')

ORDER = ["L01","L02","L03","L04","M01","M02","M03","M04","E01","E02","E03","E04",
         "C01","C02","C03","C04","F01","F02","F03","F04"]


def render_oracle():
    records = []
    for sid in ORDER:
        label, window, source = F[sid]
        bug_line = next(
            (i for i, line in enumerate(source.splitlines(), start=1) if "# BUG:" in line),
            None,
        )
        records.append(
            {
                "scenario_id": sid,
                "expected_label": label,
                "window": window,
                "bug_file": "app.py" if bug_line else None,
                "bug_line": bug_line,
                **(
                    {"definition_source": "reconstructed from documented behavior"}
                    if sid in {"L01", "C01"}
                    else {}
                ),
            }
        )
    return records


def backup(path):
    backup_path = path.with_name(f"{path.name}.backup-{time.time_ns()}")
    shutil.copy2(path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description="Generate TimeFault fixture sources and oracle labels.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="back up and replace existing generated fixture/oracle files",
    )
    args = parser.parse_args()

    destinations = [ROOT / "fixtures" / sid / "app.py" for sid in ORDER]
    oracle_path = ROOT / "oracle" / "labels.jsonl"
    existing = [path for path in [*destinations, oracle_path] if path.exists()]
    if existing and not args.force:
        print(
            "refusing to overwrite existing fixture/oracle files; use --force to back them up first",
            file=sys.stderr,
        )
        return 2

    if args.force:
        for path in existing:
            backup(path)

    for sid in ORDER:
        path = ROOT / "fixtures" / sid / "app.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(F[sid][2], encoding="utf-8")

    oracle_path.parent.mkdir(parents=True, exist_ok=True)
    records = render_oracle()
    oracle_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    print(f"wrote {len(ORDER)} fixture sources and oracle records")
    print("C01 and L01 are reconstructed definitions, not restored original source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
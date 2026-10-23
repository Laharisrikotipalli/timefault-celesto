import calendar
from datetime import date

def is_leap(y):
    return y % 4 == 0  # BUG: ignores the century rule

t = date.today()
assert is_leap(t.year) == calendar.isleap(t.year), f"year {t.year}"

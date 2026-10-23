import calendar
from datetime import date

def last_day(t):
    return 31 if t.month in (1, 3, 5, 7, 8, 10, 12) else 30  # BUG: February

t = date.today()
assert last_day(t) == calendar.monthrange(t.year, t.month)[1], str(t)

import calendar
from datetime import date

def add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

t = date.today()
n = add_month(t)
assert n > t and (n.year * 12 + n.month) - (t.year * 12 + t.month) == 1

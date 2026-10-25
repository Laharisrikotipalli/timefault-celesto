import calendar
from datetime import date

def days_left(today):
    return (date(today.year, 12, 31) - today).days

t = date.today()
total = 366 if calendar.isleap(t.year) else 365
assert days_left(t) + t.timetuple().tm_yday == total
assert 28 <= calendar.monthrange(t.year, t.month)[1] <= 31

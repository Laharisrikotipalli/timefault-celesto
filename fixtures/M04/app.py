import calendar
from datetime import date

def billing_due(t, billing_day=31):
    return t.day == billing_day  # BUG: short months never reach day 31

t = date.today()
if t.day == calendar.monthrange(t.year, t.month)[1]:
    assert billing_due(t), f"{t}: last day of month but not due"

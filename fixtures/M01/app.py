from datetime import date

def add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, d.day)  # BUG: that day may not exist next month

t = date.today()
assert add_month(t) > t

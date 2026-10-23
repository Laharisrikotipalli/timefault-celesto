from datetime import date

def days_left(today):
    return 365 - today.timetuple().tm_yday  # BUG: assumes a 365-day year

t = date.today()
expect = (date(t.year, 12, 31) - t).days
got = days_left(t)
assert got == expect, f"{t}: got {got}, expected {expect}"

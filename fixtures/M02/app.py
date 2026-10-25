from datetime import date

def first_of_next_month(d):
    return date(d.year, d.month + 1, 1)  # BUG: month 13 in December

t = date.today()
assert first_of_next_month(t) > t

from datetime import date

def next_day(today):

    return date(today.year, today.month, today.day + 1)  # BUG: adding one to leap day raises

today = date.today()
if today.month == 2 and today.day == 29:
    assert next_day(today) == date(today.year, 3, 1)

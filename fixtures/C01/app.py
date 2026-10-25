from datetime import date

def next_anniversary(today):
    try:
        return date(today.year + 1, today.month, today.day)
    except ValueError:
        return date(today.year + 1, 2, 28)

today = date.today()
if today.month == 2 and today.day == 29:
    assert next_anniversary(today) == date(today.year + 1, 2, 28)

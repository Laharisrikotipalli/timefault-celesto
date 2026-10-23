from datetime import datetime

def same_day_last_year(t):
    return datetime.strptime(f"{t.year - 1}-{t.month}-{t.day}", "%Y-%m-%d").date()  # BUG: Feb 29 has no twin

t = datetime.now().date()
assert same_day_last_year(t).year == t.year - 1

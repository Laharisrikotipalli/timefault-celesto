from datetime import date, datetime

t = date.today()
packed = t.strftime("%d/%m/%y")
back = datetime.strptime(packed, "%d/%m/%y").date()  # BUG: two-digit year pivots at 2069
assert back == t, f"{t} -> {packed} -> {back}"

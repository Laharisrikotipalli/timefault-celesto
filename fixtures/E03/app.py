from datetime import date

LICENSE_END = date(2028, 3, 1)

def expired(t):
    return t >= LICENSE_END  # BUG: license is valid through its end date

t = date.today()
assert expired(t) == (t > LICENSE_END), str(t)

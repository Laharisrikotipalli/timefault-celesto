from datetime import datetime

EXPIRES = datetime(2028, 6, 1)
now = datetime.now()

def token_valid(n):
    return n.date() <= EXPIRES.date()  # BUG: token is already expired on its expiry day

assert token_valid(now) == (now < EXPIRES), f"{now:%Y-%m-%d}"

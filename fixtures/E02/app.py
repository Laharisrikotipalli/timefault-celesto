import time

ts = int(time.time())
packed = ts if ts < 2**31 else None  # BUG: epoch seconds stored in a signed 32-bit field
assert packed is not None, f"timestamp {ts} overflows int32"

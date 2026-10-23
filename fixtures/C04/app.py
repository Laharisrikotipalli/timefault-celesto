import time
from datetime import datetime, timezone

ts = int(time.time())
back = datetime.fromtimestamp(ts, tz=timezone.utc)
assert int(back.timestamp()) == ts
assert back.year >= 1970

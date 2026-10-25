import time

assert time.time_ns() % 3 != 0, "timing race, not a date bug"
